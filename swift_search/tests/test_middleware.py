import unittest
from cStringIO import StringIO
from webob import Request, Response


class FakeApp(object):
    def __call__(self, env, start_response):
        return Response(body="FAKE APP")(env, start_response)


class TestSwiftSearchMiddleware(unittest.TestCase):
    def setUp(self):
        self.app = SwiftSearchMiddleware(FakeApp(), {})

    def test_put_empty(self):
        resp = Request.blank('/v1/account/container/object', environ={'REQUEST_METHOD': 'PUT', }).get_response(self.app)

        self.assertEqual(resp.body, "FAKE APP")

    def test_put(self):
        resp = Request.blank('/v1/account/container/object',
                             environ={'REQUEST_METHOD': 'PUT', 'wsgi.input': StringIO(pyclamd.EICAR)}).get_response(self.app)

        self.assertEqual(resp.status_code, 403)
