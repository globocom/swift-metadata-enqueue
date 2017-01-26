
# import threading
import unittest
# import pika
# import mock

# from functools import wraps
# from mock import patch, Mock
# from webob import Request, Response

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


class SwiftSearchTestCase(unittest.TestCase):

    def test_invalid_method(self):
        pass

    def test_invalid_url(self):
        pass

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