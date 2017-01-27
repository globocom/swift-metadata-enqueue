import unittest

from mock import patch, Mock
from swift.common import swob
from swift_search import middleware as md


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
            'swift_search.middleware.SwiftSearch.send_req_to_queue',
            Mock()).start()

        # Mocking interactions with queue
        patch('swift_search.middleware.start_queue_conn', Mock()).start()

    def tearDown(self):
        patch.stopall()

    @patch('swift_search.middleware.SwiftSearch._has_optin_header')
    def test_allowed_method_request_must_be_published(self, mock):
        mock.return_value = True

        for method in md.ALLOWED_METHODS:
            swob.Request.blank('/v1/a/c/o',
                               environ={'REQUEST_METHOD': method}
                               ).get_response(self.app)

        expected = len(md.ALLOWED_METHODS)
        computed = self.send_req_to_queue.call_count

        self.assertEqual(computed, expected)

    @patch('swift_search.middleware.SwiftSearch._has_optin_header')
    def test_NOT_allowed_method_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        for method in ['GET', 'HEAD', 'OPTIONS']:
            swob.Request.blank('/v1/a/c/o',
                               environ={'REQUEST_METHOD': method}
                               ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_search.middleware.SwiftSearch._has_optin_header')
    def test_valid_object_url_request_must_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_search.middleware.SwiftSearch._has_optin_header')
    def test_container_url_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a/c',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_search.middleware.SwiftSearch._has_optin_header')
    def test_account_url_request_must_NOT_be_published(self, mock):
        mock.return_value = True

        swob.Request.blank('/v1/a',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_search.middleware.get_container_info')
    def test_container_has_optin_header_must_be_published_(self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'True'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_search.middleware.get_account_info')
    def test_account_has_optin_header_must_be_published_(self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'True'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_called()

    @patch('swift_search.middleware.get_container_info')
    def test_container_has_falsy_optin_header_must_NOT_be_published(
            self, mock):

        mock.return_value = {'meta': {md.META_SEARCH_ENABLED: 'False'}}

        swob.Request.blank('/v1/a/c/o',
                           environ={'REQUEST_METHOD': 'PUT'}
                           ).get_response(self.app)

        self.send_req_to_queue.assert_not_called()

    @patch('swift_search.middleware.get_account_info')
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

    # def test_filter_headers(self):
    #     pass

    # def test_mk_message(self):
    #     pass

    # def test_put_request_indexable(self):
    #     pass

    # def test_post_request_indexable(self):
    #     pass

    # def test_delete_request_indexable(self):
    #     pass

    # def test_fail_to_connect_to_queue(self):
    #     pass

    # def test_connection_to_queue_closed_on_publishing(self):
    #     pass

    # def test_fail_to_connect_to_queue_on_publishing(self):
    #     pass


if __name__ == '__main__':
    unittest.main()
