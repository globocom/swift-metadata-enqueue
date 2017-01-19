
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


# class SwiftSearchTestCase(unittest.TestCase):

#     @classmethod
#     def setUpClass(cls):

#         # Silent log
#         patch('swift_search.middleware.LOG', Mock()).start()
#         patch('swift_search.middleware.SwiftSearch.start_queue', Mock()).start()

#         cls.environ = {'HTTP_HOST': 'localhost',
#                        'PATH_INFO': '/teste',
#                        'REQUEST_METHOD': 'PUT'}

#         cls.conf = {"queue_name": "swiftsearch",
#                     "queue_url": "localhost",
#                     "queue_username": "storm",
#                     "queue_password": "storm",
#                     "queue_vhost": "s3busca",
#                     "queue_port": 5672
#                     }

#         cls.app = SwiftSearch(FakeApp(), cls.conf)

#     @classmethod
#     def tearDownClass(cls):
#         pass

#     def test_apply_middleware_on_app(self):
#         app = self.app

#         self.assertIsInstance(app, SwiftSearch)

#     def test_put_request(self):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)

#         self.assertEqual(resp.body, "Fake Test App")
#         self.assertEqual(resp.status_code, 200)

#     def test_post_request(self):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'POST'}).get_response(self.app)

#         self.assertEqual(resp.body, "Fake Test App")
#         self.assertEqual(resp.status_code, 200)

#     def test_delete_request(self):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'DELETE'}).get_response(self.app)

#         self.assertEqual(resp.body, "Fake Test App")
#         self.assertEqual(resp.status_code, 200)

#     def test_get_ok(self):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'GET'}).get_response(self.app)

#         self.assertEqual(resp.body, "Fake Test App")
#         self.assertEqual(resp.status_code, 200)

#     @patch("swift_search.middleware.SwiftSearch.send_queue")
#     def test_send_queue_not_called(self, mock_send_queue):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'GET'}).get_response(self.app)

#         mock_send_queue.assert_not_called()

#     @patch("swift_search.middleware.SwiftSearch.send_queue")
#     def test_request_put_function_send_queue_called(self, mock_send_queue):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)

#         mock_send_queue.assert_called()

#     @patch("swift_search.middleware.SwiftSearch.send_queue")
#     def test_request_post_function_send_queue_called(self, mock_send_queue):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'POST'}).get_response(self.app)

#         mock_send_queue.assert_called()

#     @patch("swift_search.middleware.SwiftSearch.send_queue")
#     def test_request_delete_function_send_queue_called(self, mock_send_queue):

#         resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'DELETE'}).get_response(self.app)

#         mock_send_queue.assert_called()

#     def test_get_threading(self):
#         queued = threading.Event()

#         # Call send_queue with side effect with lambda setting a threading.Event flag to true,
#         # for execute immediately.
#         with mock.patch('swift_search.middleware.SwiftSearch.send_queue',
#                          side_effect=lambda *args, **kwargs: queued.set()) as queue:

#             resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)
#             self.assertEqual("Fake Test App", resp.body)

#             # queued.wait()

#             # Check if queued.set is called in call send_queue function
#             queue.assert_called()

#             # Check if queued.set is calling with arguments.
#             self.assertEqual(1, len(queue.call_args_list))

if __name__ == '__main__':
    unittest.main()