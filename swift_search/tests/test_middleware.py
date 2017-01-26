import unittest

from mock import patch, Mock
from functools import wraps
from swift.common import swob
from swift_search import middleware as md


class FakeApp(object):
    def __init__(self):
        self.responses = []  # fill in later
        self._calls = []

    def __call__(self, env, start_response):
        req = swob.Request(env)

        self._calls.append((
            req.method, req.path,
            # mutable dict; keep a copy so subsequent calls can't change it
            swob.HeaderKeyDict(req.headers)))

        if len(self.responses) > 1:
            resp = self.responses.pop(0)
        else:
            resp = self.responses[0]

        status = resp['status']
        headers = resp.get('headers', [])
        env.update(resp.get('environ', {}))
        body_iter = resp.get('body_iter', [])
        start_response(status, headers)
        return body_iter

    @property
    def calls(self):
        """
        Returns the calls received by this application as a list of
        (method, path) pairs.
        """
        return [x[:2] for x in self._calls]

    @property
    def call_headers(self):
        """
        Returns the list of headers received by this application as it was
        called
        """
        return [x[2] for x in self._calls]

    @property
    def calls_with_headers(self):
        """
        Returns the calls received by this application as a list of
        (method, path, headers) tuples.
        """
        return self._calls


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


def with_req(path, method, headers=None):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            req = swob.Request.blank(path)
            req.method = method
            if headers:
                req.headers.update(headers)
            kwargs['req'] = req
            return func(*args, **kwargs)
        return wrapped
    return decorator


class MiddlewareTestCase(unittest.TestCase):
    """
    Just a base class for other test cases. Some setup, some utility methods.
    Nothing too exciting.
    """
    def setUp(self):
        self.app = FakeApp()
        self.search_md = md.filter_factory({})(self.app)

        # Mocking interactions with queue
        self.start_queue_conn = patch(
            'swift_search.middleware.start_queue_conn', Mock()).start()

        self.queue = self.start_queue_conn.return_value

        # This object must be patched to allow assert_called_args
        patch('swift_search.middleware.pika.BasicProperties',
              return_value='patched').start()

    def tearDown(self):
        patch.stopall()

    def call_mware(self, req, expect_exception=False):
        status = [None]
        headers = [None]

        def start_response(s, h, ei=None):
            status[0] = s
            headers[0] = h

        body_iter = self.search_md(req.environ, start_response)
        body = ''
        caught_exc = None
        try:
            for chunk in body_iter:
                body += chunk
        except Exception as exc:
            if expect_exception:
                caught_exc = exc
            else:
                raise

        headerdict = swob.HeaderKeyDict(headers[0])
        if expect_exception:
            return status[0], headerdict, body, caught_exc
        else:
            return status[0], headerdict, body


class SwiftSearchTestCase(MiddlewareTestCase):

    def setUp(self):
        super(SwiftSearchTestCase, self).setUp()
        self.msg = 'message_to_send'
        patch('swift_search.middleware.SwiftSearch._mk_message',
              return_value=self.msg).start()

        self.expected_publish = {
            'body': '"message_to_send"',
            'exchange': '',
            'properties': 'patched',
            'routing_key': 'swift_search'
        }

        # Mocking _has_optin_header because its
        # calls a method on swift. We are assuming that the container/account
        # has the optin header.
        self.mock_h_o_header = patch(
            'swift_search.middleware.SwiftSearch._has_optin_header',
            Mock(return_value=True)).start()

    def tearDown(self):
        super(SwiftSearchTestCase, self).tearDown()
        patch.stopall()

    @with_req('/v1/a/c/o', 'PUT')
    def test_put_request_must_be_published(self, req):
        """ Tests a valid a request. """
        self.app.responses = [{'status': '201 Created'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_called_with(**self.expected_publish)

    @with_req('/v1/a/c/o', 'POST')
    def test_post_request_must_be_published(self, req):
        """ Tests a valid a request. """
        self.app.responses = [{'status': '201 Created'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_called_with(**self.expected_publish)

    @with_req('/v1/a/c/o', 'DELETE')
    def test_delete_request_must_be_published(self, req):
        """ Tests a valid a request. """
        self.app.responses = [{'status': '204 No Content'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_called_with(**self.expected_publish)

    @with_req('/v1/a/c/o', 'GET')
    def test_get_request_must_not_be_published(self, req):
        """ Tests a valid a request, not allowed method. """
        self.app.responses = [{'status': '200 OK'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    @with_req('/v1/a/c/o', 'HEAD')
    def test_head_request_must_not_be_published(self, req):
        """ Tests a valid a request, not allowed method. """
        self.app.responses = [{'status': '200 OK'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    @with_req('/v1/a/c/o', 'OPTIONS')
    def test_options_request_must_not_be_published(self, req):
        """ Tests a valid a request, not allowed method. """
        self.app.responses = [{'status': '200 OK'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    @with_req('/v1/a/c', 'PUT')
    def test_put_container_must_not_be_published(self, req):
        """ Tests a request to a container. Must not publish to queue! """
        self.app.responses = [{'status': '200 OK'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    @with_req('/v1/a/c', 'POST')
    def test_post_container_must_not_be_published(self, req):
        """ Tests a request to a container. Must not publish to queue! """
        self.app.responses = [{'status': '200 OK'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    @with_req('/v1/a/c', 'DELETE')
    def test_delete_container_must_not_be_published(self, req):
        """ Tests a request to a container. Must not publish to queue! """
        self.app.responses = [{'status': '204 No Content'}]

        _, _, _ = self.call_mware(req)

        self.queue.basic_publish.assert_not_called()

    def test_optin_header_not_found(self):
        pass

    def test_filter_headers(self):
        pass

    def test_mk_message(self):
        pass

    def test_put_request_indexable(self):
        pass

    def test_post_request_indexable(self):
        pass

    def test_delete_request_indexable(self):
        pass

    def test_fail_to_connect_to_queue(self):
        pass

    def test_connection_to_queue_closed_on_publishing(self):
        pass

    def test_failt_to_connect_to_queue_on_publishing(self):
        pass


if __name__ == '__main__':
    unittest.main()
