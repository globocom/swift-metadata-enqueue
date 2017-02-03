import json
import unittest

from mock import patch, Mock
from swift.common import swob
from swift_metadata_indexer import middleware as md


class FakeApp(object):

    def __call__(self, env, start_response):
        return swob.Response('Fake Test App')(env, start_response)


class TestConfigParsing(unittest.TestCase):
    def test_non_defaults(self):
        app = FakeApp()
        search_md = md.filter_factory({
            'queue_username': 'user',
            'queue_password': 'secret',
            'queue_url': 'host.to.rabbitmq',
            'queue_port': '5672',
            'queue_vhost': 'vhost',
        })(app)

        self.assertEqual(search_md.conf.get('queue_username'), 'user')
        self.assertEqual(search_md.conf.get('queue_password'), 'secret')
        self.assertEqual(search_md.conf.get('queue_url'), 'host.to.rabbitmq')
        self.assertEqual(search_md.conf.get('queue_port'), '5672')
        self.assertEqual(search_md.conf.get('queue_vhost'), 'vhost')


class TestSwiftSearchCall(unittest.TestCase):
    """
    There are two important steps before send to queue:
        - Verify if the request is valid
        - Connect to a queue

    If any step fails, it should return the app to the pipeline, and should not
    try to send message to the queue

    """

    def setUp(self):
        self.app = md.SwiftSearch(FakeApp(), {})
        self.send_req_to_queue = patch(
            'swift_metadata_indexer.middleware.SwiftSearch.send_req_to_queue',
            Mock()).start()

    def test_is_suitable_for_indexing_returns_falsy(self):
        """ Send to queue should not be called """
        patch(('swift_metadata_indexer.middleware.SwiftSearch'
               '.is_suitable_for_indexing'), Mock(return_value=None)).start()

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    def test_start_queue_conn_returns_falsy(self):
        """ Send to queue should not be called """
        patch(('swift_metadata_indexer.middleware.SwiftSearch'
               '.is_suitable_for_indexing'), Mock(return_value=True)).start()

        patch('swift_metadata_indexer.middleware.start_queue_conn',
              Mock(return_value=None)).start()

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    def tearDown(self):
        patch.stopall()


class StartQueueTestCase(unittest.TestCase):
    """
    Test only start_queue_conn method.
    No side effect on the middleware is tested here
    """

    def setUp(self):

        self.conf = {
            'queue_username': 'user',
            'queue_password': 'secret',
            'queue_url': 'host.to.rabbitmq',
            'queue_port': '5672',
            'queue_vhost': 'vhost',
        }

        self.logger = Mock()
        self.pika = patch('swift_metadata_indexer.middleware.pika',
                          Mock()).start()

    def tearDown(self):
        patch.stopall()

    def test_start_queue_conn(self):
        """
        Happy path.Test all pika methods calls when everything works
        It should return a channel (connection.channel.return_value)
        """

        self.pika.PlainCredentials.return_value = 'credential_return'
        self.pika.ConnectionParameters.return_value = 'parameters_return'

        connection = self.pika.BlockingConnection.return_value
        channel = connection.channel.return_value

        result = md.start_queue_conn(self.conf, self.logger)

        self.assertEqual(result, channel)

        connection.channel.assert_called_once()
        channel.queue_declare.assert_called_with(
            queue='swift_search',
            durable=True)

        self.pika.PlainCredentials.assert_called_with('user', 'secret')
        self.pika.ConnectionParameters.assert_called_with(
            host='host.to.rabbitmq',
            port=5672,
            virtual_host='vhost',
            credentials='credential_return'
        )
        self.pika.BlockingConnection.assert_called_with('parameters_return')

    def test_start_queue_conn_fail_to_connect(self):
        """ It should return None """
        self.pika.BlockingConnection.side_effect = Exception

        result = md.start_queue_conn(self.conf, self.logger)

        self.assertIsNone(result)

    def test_start_queue_conn_fail_to_create_queue(self):
        """ It should return None """
        connection = self.pika.BlockingConnection.return_value
        connection.channel.side_effect = Exception

        result = md.start_queue_conn(self.conf, self.logger)

        self.assertIsNone(result)

    def test_start_queue_conn_fail_to_declare_queue(self):
        """ It should return None """
        connection = self.pika.BlockingConnection.return_value
        channel = connection.channel.return_value
        channel.queue_declare.side_effect = Exception

        result = md.start_queue_conn(self.conf, self.logger)

        self.assertIsNone(result)


class SwiftSearchValidateRequesTestCase(unittest.TestCase):
    """
    These tests intend to verify if the middleware is properly checking if
    the request is suitable or not to be indexed. Everything is mocked,
    but the method that validates the request.

    If it is suitable, ``send_req_to_queue`` method should be called.
    Otherwise, ``send_req_to_queue`` must not be called.
    """

    def setUp(self):
        self.app = md.SwiftSearch(FakeApp(), {})

        self.send_req_to_queue = patch(
            'swift_metadata_indexer.middleware.SwiftSearch.send_req_to_queue',
            Mock()).start()

        # Mocking interactions with queue
        patch('swift_metadata_indexer.middleware.start_queue_conn',
              Mock()).start()

    def tearDown(self):
        patch.stopall()

    @patch('swift_metadata_indexer.middleware.SwiftSearch._has_optin_header')
    def test_allowed_method_request_must_be_published(self, mock):
        mock.return_value = True

        for method in md.ALLOWED_METHODS:
            swob.Request.blank('/v1/a/c/o',
                               environ={'REQUEST_METHOD': method}
                               ).get_response(self.app)

        expected = len(md.ALLOWED_METHODS)
        computed = self.send_req_to_queue.call_count

        self.assertEqual(computed, expected)

    @patch('swift_metadata_indexer.middleware.SwiftSearch._has_optin_header')
    def test_NOT_allowed_method_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        for method in ['GET', 'HEAD', 'OPTIONS']:
            swob.Request.blank('/v1/a/c/o',
                               environ={'REQUEST_METHOD': method}
                               ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_metadata_indexer.middleware.SwiftSearch._has_optin_header')
    def test_valid_object_url_request_must_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_metadata_indexer.middleware.SwiftSearch._has_optin_header')
    def test_container_url_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a/c',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_metadata_indexer.middleware.SwiftSearch._has_optin_header')
    def test_account_url_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_metadata_indexer.middleware.get_container_info')
    def test_container_has_optin_header_must_be_published_(self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'True'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_metadata_indexer.middleware.get_account_info')
    def test_account_has_optin_header_must_be_published_(self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'True'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_metadata_indexer.middleware.get_container_info')
    def test_container_has_falsy_optin_header_must_NOT_be_published(
            self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'False'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_metadata_indexer.middleware.get_account_info')
    def test_account_has_falsy_optin_header_must_NOT_be_published(
            self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'False'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    def test_account_container_dont_have_optin_header_must_NOT_be_published(
            self):

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()


class SendToQueueTestCase(unittest.TestCase):

    def setUp(self):
        self.app = md.SwiftSearch(FakeApp(), {})

        patch('swift_metadata_indexer.middleware.SwiftSearch._mk_message',
              Mock(return_value='message')).start()

    def tearDown(self):
        patch.stopall()

    @patch('swift_metadata_indexer.middleware.SwiftSearch._publish')
    def test_publish_works_on_first_try(self, mock_publish):

        req = swob.Request.blank('/v1/a/c/o')
        self.app.send_req_to_queue('queue', req)

        mock_publish.called_once_with('queue', 'message')

    @patch('swift_metadata_indexer.middleware.start_queue_conn')
    @patch('swift_metadata_indexer.middleware.SwiftSearch._publish')
    def test_publish_works_on_second_try(self, mock_pub, mock_start_q):

        mock_start_q.return_value = 'new_queue'
        mock_pub.side_effect = [Exception, Mock()]

        req = swob.Request.blank('/v1/a/c/o')
        self.app.send_req_to_queue('queue', req)

        mock_pub.called_with('new_queue', 'message')

    @patch('swift_metadata_indexer.middleware.start_queue_conn')
    @patch('swift_metadata_indexer.middleware.SwiftSearch._publish')
    def test_publish_fail_to_reconnect_to_queue(self, mock_pub, mock_start_q):
        """
        Publish fail on first try.
        Then it trys to reconnect to queue, but fails.
        Publish should not be called again
        """
        mock_start_q.return_value = None
        mock_pub.side_effect = Exception

        req = swob.Request.blank('/v1/a/c/o')
        self.app.send_req_to_queue('queue', req)

        mock_pub.assert_called_once()


class SwiftSearchHelpersTestCase(unittest.TestCase):
    """
    Test helpers methods:
        - _filter_headers
        - _mk_message
        - _publish
        - _is_valid_method
        - _is_valid_object_url
        - _has_optin_header
    """

    def setUp(self):
        self.app = md.SwiftSearch(FakeApp(), {})

        # Mocking connection to queue
        patch('swift_metadata_indexer.middleware.start_queue_conn',
              Mock()).start()

        # Ignores request validation
        patch(('swift_metadata_indexer.middleware.SwiftSearch'
               '.is_suitable_for_indexing'), Mock(return_value=True)).start()

        patch(('swift_metadata_indexer.middleware.SwiftSearch'
               '.send_req_to_queue'), Mock()).start()

    def tearDown(self):
        patch.stopall()

    def test_filter_headers_allowed_should_return_all_allowed_headers(self):
        """ Should return all allowed headers """

        expected = {}
        for header in md.ALLOWED_HEADERS:
            expected[header.title()] = header + '-value'

        expected[md.META_OBJECT_PREFIX.title() + '-Teste'] = 'teste'
        req = swob.Request.blank(
            '/v1/a/c/o',
            environ={'REQUEST_METHOD': 'PUT'},
            headers=expected
        )
        computed = self.app._filter_headers(req)

        self.assertEqual(computed, expected)

    def test_filter_headers_should_not_return_not_allowed_headers(self):
        """ No header allowed. Should return an empty dict """

        req = swob.Request.blank(
            '/v1/a/c/o',
            environ={'REQUEST_METHOD': 'PUT'},
            headers={'x-invalid-header': 'random'}
        )
        computed = self.app._filter_headers(req)

        self.assertEqual(computed, {})

    @patch('swift_metadata_indexer.middleware.datetime')
    def test_mk_message_should_return_the_proper_message(self, mock_date):
        patch('swift_metadata_indexer.middleware.SwiftSearch._filter_headers',
              Mock(return_value={'header': 'value'})).start()

        utcnow = mock_date.utcnow.return_value
        utcnow.isoformat.return_value = '2017-02-02T16:53:33.355817'

        req = swob.Request.blank(
            '/v1/a/c/o',
            environ={'REQUEST_METHOD': 'PUT'}
        )

        computed = self.app._mk_message(req)

        expected = {
            'uri': '/v1/a/c/o',
            'http_method': 'PUT',
            'headers': {'header': 'value'},
            'timestamp': '2017-02-02T16:53:33.355817'
        }

        self.assertEqual(computed, expected)

    def test_publish_should_call_queue_with_proper_args(self):

        # Mock: pika.BasicProperties(delivery_mode=2)
        patch('swift_metadata_indexer.middleware.pika.BasicProperties',
              Mock(return_value={})).start()

        queue = Mock()
        message = {'body': 'random text', 'x-container': 'test'}
        self.app._publish(queue, message)

        queue.basic_publish.assert_called_with(
            exchange='',
            routing_key='swift_search',
            body=json.dumps(message),
            properties={}
        )

    def test_is_valid_method_should_return_true_for_valid_methods(self):

        for method in md.ALLOWED_METHODS:
            req = swob.Request.blank(
                '/v1/a/c/o',
                environ={'REQUEST_METHOD': method}
            )

            computed = self.app._is_valid_method(req)

            self.assertTrue(computed)

    def test_is_valid_method_should_return_false_for_invalid_methods(self):

        http_methods = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'TRACE',
                        'OPTIONS', 'CONNECT', 'PATCH']

        for method in http_methods:
            if method not in md.ALLOWED_METHODS:
                req = swob.Request.blank(
                    '/v1/a/c/o',
                    environ={'REQUEST_METHOD': method}
                )

                computed = self.app._is_valid_method(req)

                self.assertFalse(computed)

    def test_is_valid_object_url_should_return_true_for_object_url(self):
        """ Testing object url """
        req = swob.Request.blank('/v1/a/c/o')
        computed = self.app._is_valid_object_url(req)

        self.assertTrue(computed)

    def test_is_valid_object_url_should_return_false_for_container_url(self):
        """ Testing container url """
        req = swob.Request.blank('/v1/a/c')
        computed = self.app._is_valid_object_url(req)

        self.assertFalse(computed)

    def test_is_valid_object_url_should_return_false_for_account_url(self):
        """ Testing account url """
        req = swob.Request.blank('/v1/a')
        computed = self.app._is_valid_object_url(req)

        self.assertFalse(computed)

    def test_is_valid_object_url_should_return_false_for_invalid_url(self):
        """ Testing /info url """
        req = swob.Request.blank('/info')
        computed = self.app._is_valid_object_url(req)

        self.assertFalse(computed)

    def test_has_optin_header_should_return_true_if_container_has_header(self):

        mock_return = {
            'meta': {
                md.META_SEARCH_ENABLED: 'True'
            }
        }
        patch('swift_metadata_indexer.middleware.get_container_info',
              Mock(return_value=mock_return)).start()

        req = swob.Request.blank('/v1/a/c/o')

        computed = self.app._has_optin_header(req)

        self.assertTrue(computed)

    def test_has_optin_header_should_return_true_if_account_has_header(self):

        mock_return = {
            'meta': {
                md.META_SEARCH_ENABLED: 'True'
            }
        }
        patch('swift_metadata_indexer.middleware.get_account_info',
              Mock(return_value=mock_return)).start()

        req = swob.Request.blank('/v1/a/c/o')

        computed = self.app._has_optin_header(req)

        self.assertTrue(computed)

    def test_has_optin_header_should_return_false_if_none_has_header(self):

        patch('swift_metadata_indexer.middleware.get_account_info',
              Mock(return_value={'meta': {}})).start()

        patch('swift_metadata_indexer.middleware.get_container_info',
              Mock(return_value={'meta': {}})).start()

        req = swob.Request.blank('/v1/a/c/o')

        computed = self.app._has_optin_header(req)

        self.assertFalse(computed)
