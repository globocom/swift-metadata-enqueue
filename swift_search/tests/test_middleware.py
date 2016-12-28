
import threading
import unittest
import pika

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
        print "Done"

    def test_apply_middleware_on_app(self):
        app = self.app

        self.assertIsInstance(app, SwiftSearch)

    def test_put_request(self):

        self.environ = {'REQUEST_METHOD': 'PUT'}

        resp = Request.blank('/teste', environ=self.environ).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_post_request(self):

        self.environ = {'REQUEST_METHOD': 'POST'}

        resp = Request.blank('/teste', environ=self.environ).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_post_request(self):

        self.environ = {'REQUEST_METHOD': 'DELETE'}

        resp = Request.blank('/teste', environ=self.environ).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)

    def test_response_ok(self):

        self.environ = {'REQUEST_METHOD': 'GET'}

        resp = Request.blank('/teste', environ=self.environ).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")
        self.assertEqual(resp.status_code, 200)
