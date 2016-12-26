
import threading
import unittest
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
        print "Finish"

    def test_apply_middleware_on_app(self):
        app = self.app

        self.assertIsInstance(app, SwiftSearch)

    def test_get_request(self):

        self.environ = {'REQUEST_METHOD': 'GET'}

        resp = Request.blank('/teste', environ=self.environ).get_response(self.app)

        self.assertEqual(resp.body, "Fake Test App")

# @mock.patch('oslo_messaging.get_transport', mock.MagicMock())
# class TestSwift(unittest.TestCase):

#     def setUp(self):
#         super(TestSwift, self).setUp()
#         cfg.CONF([], project='swiftsearchmiddleware')
#         self.addCleanup(cfg.CONF.reset)

#     @staticmethod
#     def start_response(*args):
#             pass

#     def test_get(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(), {})
#         req = FakeRequest('/1.0/account/container/obj',
#                           environ={'REQUEST_METHOD': 'GET'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             resp = app(req.environ, self.start_response)
#             self.assertEqual(["This is a body for Swift Search Middleware."], list(resp))
#             # self.assertEqual(1, len(notify.call_args_list))
#             # data = notify.call_args_list[0][0]
#             # self.assertEqual('storage.index', data[1])
#             # self.assertEqual('container', metadata['container'])
#             # self.assertEqual('obj', metadata['object'])

#     def indev_test_get_background(self):
#         notified = threading.Event()
#         app = middleware.SwiftSearchMiddleware(FakeApp(),
#                           {"nonblocking_notify": "True",
#                            "send_queue_size": "1"})
#         req = FakeRequest('/1.0/account/container/obj',
#                           environ={'REQUEST_METHOD': 'GET'})
#         with mock.patch('oslo_messaging.Notifier.info',
#                         side_effect=lambda *args, **kwargs: notified.set()
#                         ) as notify:
#             resp = app(req.environ, self.start_response)
#             self.assertEqual(["This is a body for Swift Search Middleware."], list(resp))
#             notified.wait()
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('container', metadata['container'])

#     def indev_test_put(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
#         req = FakeRequest(
#             '/1.0/account/container/obj',
#             environ={'REQUEST_METHOD': 'PUT',
#                      'wsgi.input':
#                      six.moves.cStringIO('some stuff')})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('container', metadata['container'])
#             self.assertEqual('obj', metadata['object'])

#     def indev_test_post(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
#         req = FakeRequest(
#             '/1.0/account/container/obj',
#             environ={'REQUEST_METHOD': 'POST',
#                      'wsgi.input': six.moves.cStringIO('some other stuff')})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('container', metadata['container'])

#     def indev_test_bogus_request(self):
#         """Test even for arbitrary request method, this will still work."""
#         app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
#         req = FakeRequest('/1.0/account/container/obj',
#                           environ={'REQUEST_METHOD': 'BOGUS'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('container', metadata['container'])
#             self.assertEqual('obj', metadata['object'])

#     def indev_test_get_container(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(), {})
#         req = FakeRequest('/1.0/account/container',
#                           environ={'REQUEST_METHOD': 'GET'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('container', metadata['container'])
#             self.assertIsNone(metadata['object'])

#     def indev_test_metadata_headers_unicode(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(), {
#             'metadata_headers': 'unicode'
#         })
#         uni = u'\xef\xbd\xa1\xef\xbd\xa5'
#         req = FakeRequest('/1.0/account/container',
#                           environ={'REQUEST_METHOD': 'GET'},
#                           headers={'UNICODE': uni})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(1, len(notify.call_args_list))
#             data = notify.call_args_list[0][0]
#             self.assertEqual('storage.index', data[1])
#             self.assertEqual('1.0', metadata['version'])
#             self.assertEqual('container', metadata['container'])
#             self.assertIsNone(metadata['object'])

#     def indev_test_bogus_path(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(), {})
#         req = FakeRequest('/5.0//',
#                           environ={'REQUEST_METHOD': 'GET'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertEqual(0, len(notify.call_args_list))

#     @mock.patch('six.moves.urllib.parse.quote')
#     def indev_test_emit_event_fail(self, mocked_func):
#         mocked_func.side_effect = Exception("a exception")
#         app = middleware.SwiftSearchMiddleware(FakeApp(body=["test"]), {})
#         req = FakeRequest('/1.0/account/container',
#                           environ={'REQUEST_METHOD': 'GET'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             resp = list(app(req.environ, self.start_response))
#             self.assertEqual(0, len(notify.call_args_list))
#             self.assertEqual(["test"], resp)

#     def test_put_with_swift_source(self):
#         app = middleware.SwiftSearchMiddleware(FakeApp(), {})

#         req = FakeRequest(
#             '/1.0/account/container/obj',
#             environ={'REQUEST_METHOD': 'PUT',
#                      'wsgi.input':
#                      six.moves.cStringIO('some stuff'),
#                      'swift.source': 'RL'})
#         with mock.patch('oslo_messaging.Notifier.info') as notify:
#             list(app(req.environ, self.start_response))
#             self.assertFalse(notify.called)
