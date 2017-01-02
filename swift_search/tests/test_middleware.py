
import threading
import unittest
import pika
import mock

from mock import patch, Mock

from webob import Request, Response

from swift_search.middleware import *


class FakeApp(object):

    def __call__(self, env, start_response):
        return Response('Fake Test App')(env, start_response)


class SwiftSearchTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # Silent log
        patch('swift_search.middleware.LOG', Mock()).start()

        cls.environ = {'HTTP_HOST': 'localhost',
                       'PATH_INFO': '/teste',
                       'REQUEST_METHOD': 'PUT'}

        cls.conf = {"queue_name": "swiftsearch",
                    "queue_url": "localhost"}

        cls.app = SwiftSearch(FakeApp(), cls.conf)

    @classmethod
    def tearDownClass(cls):
        pass

    def test_apply_middleware_on_app(self):
        app = self.app

        self.assertIsInstance(app, SwiftSearch)

    def test_put_request(self):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_post_request(self):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'POST'}).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_delete_request(self):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'DELETE'}).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_get_ok(self):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'GET'}).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    @patch("swift_search.middleware.SwiftSearch.start_queue")
    def test_start_queue_called(self, mock_queue):

        SwiftSearch(FakeApp(), {"queue_url": "teste", "queue_name": "bla"})

        mock_queue.assert_called()

    @patch("swift_search.middleware.SwiftSearch.send_queue")
    def test_send_queue_not_called(self, mock_send_queue):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'GET'}).get_response(self.app)

        mock_send_queue.assert_not_called()

    @patch("swift_search.middleware.SwiftSearch.send_queue")
    def test_request_put_function_send_queue_called(self, mock_send_queue):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)

        mock_send_queue.assert_called()

    @patch("swift_search.middleware.SwiftSearch.send_queue")
    def test_request_post_function_send_queue_called(self, mock_send_queue):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'POST'}).get_response(self.app)

        mock_send_queue.assert_called()

    @patch("swift_search.middleware.SwiftSearch.send_queue")
    def test_request_delete_function_send_queue_called(self, mock_send_queue):

        resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'DELETE'}).get_response(self.app)

        mock_send_queue.assert_called()

    def test_get_threading(self):
        queued = threading.Event()

        # Call send_queue with side effect with lambda setting a threading.Event flag to true,
        # for execute immediately.
        with mock.patch('swift_search.middleware.SwiftSearch.send_queue',
                         side_effect=lambda *args, **kwargs: queued.set()) as queue:

            resp = Request.blank('/teste', environ={'REQUEST_METHOD': 'PUT'}).get_response(self.app)
            self.assertEqual("Fake Test App", resp.body)

            # queued.wait()

            # Check if queued.set is called in call send_queue function
            queue.assert_called()

            # Check if queued.set is calling with arguments.
            self.assertEqual(1, len(queue.call_args_list))
