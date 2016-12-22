#
# Copyright 2012 eNovance <licensing@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import mock
from oslo_config import cfg
import six

from swift_search import middleware
from swift_search.tests import base as tests_base
import threading


class FakeApp(object):
    def __init__(self, body=None):
        self.body = body or ['This is a body for Swift Search Middleware.']

    def __call__(self, env, start_response):
        yield
        start_response('200 OK', [
            ('Content-Type', 'text/plain'),
            ('Content-Length', str(sum(map(len, self.body))))
        ])
        # while env['wsgi.input'].read(5):
        #    pass
        # for line in self.body:
        #    yield line


class FakeRequest(object):
    """A bare bones request object
    The middleware will inspect this for request method,
    wsgi.input and headers.
    """

    def __init__(self, path, environ=None, headers=None):
        environ = environ or {}
        headers = headers or {}

        environ['PATH_INFO'] = path

        if 'wsgi.input' not in environ:
            environ['wsgi.input'] = six.moves.cStringIO('')

        for header, value in six.iteritems(headers):
            environ['HTTP_%s' % header.upper()] = value
        self.environ = environ


@mock.patch('oslo_messaging.get_transport', mock.MagicMock())
class TestSwift(tests_base.TestCase):

    def setUp(self):
        super(TestSwift, self).setUp()
        cfg.CONF([], project='swiftsearchmiddleware')
        self.addCleanup(cfg.CONF.reset)

    @staticmethod
    def start_response(*args):
            pass

    def test_get(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(), {})
        req = FakeRequest('/1.0/account/container/obj',
                          environ={'REQUEST_METHOD': 'GET'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            resp = app(req.environ, self.start_response)
            self.assertEqual(["This is a body for Swift Search Middleware."], list(resp))
            # self.assertEqual(1, len(notify.call_args_list))
            # data = notify.call_args_list[0][0]
            # self.assertEqual('storage.index', data[1])
            # self.assertEqual('container', metadata['container'])
            # self.assertEqual('obj', metadata['object'])

    def indev_test_get_background(self):
        notified = threading.Event()
        app = middleware.SwiftSearchMiddleware(FakeApp(),
                          {"nonblocking_notify": "True",
                           "send_queue_size": "1"})
        req = FakeRequest('/1.0/account/container/obj',
                          environ={'REQUEST_METHOD': 'GET'})
        with mock.patch('oslo_messaging.Notifier.info',
                        side_effect=lambda *args, **kwargs: notified.set()
                        ) as notify:
            resp = app(req.environ, self.start_response)
            self.assertEqual(["This is a body for Swift Search Middleware."], list(resp))
            notified.wait()
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('storage.index', data[1])
            self.assertEqual('container', metadata['container'])

    def indev_test_put(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
        req = FakeRequest(
            '/1.0/account/container/obj',
            environ={'REQUEST_METHOD': 'PUT',
                     'wsgi.input':
                     six.moves.cStringIO('some stuff')})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('storage.index', data[1])
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('container', metadata['container'])
            self.assertEqual('obj', metadata['object'])

    def indev_test_post(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
        req = FakeRequest(
            '/1.0/account/container/obj',
            environ={'REQUEST_METHOD': 'POST',
                     'wsgi.input': six.moves.cStringIO('some other stuff')})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('storage.index', data[1])
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('container', metadata['container'])

    def indev_test_bogus_request(self):
        """Test even for arbitrary request method, this will still work."""
        app = middleware.SwiftSearchMiddleware(FakeApp(body=['']), {})
        req = FakeRequest('/1.0/account/container/obj',
                          environ={'REQUEST_METHOD': 'BOGUS'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('storage.index', data[1])
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('container', metadata['container'])
            self.assertEqual('obj', metadata['object'])

    def indev_test_get_container(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(), {})
        req = FakeRequest('/1.0/account/container',
                          environ={'REQUEST_METHOD': 'GET'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('storage.index', data[1])
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('container', metadata['container'])
            self.assertIsNone(metadata['object'])

    def indev_test_metadata_headers_unicode(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(), {
            'metadata_headers': 'unicode'
        })
        uni = u'\xef\xbd\xa1\xef\xbd\xa5'
        req = FakeRequest('/1.0/account/container',
                          environ={'REQUEST_METHOD': 'GET'},
                          headers={'UNICODE': uni})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(1, len(notify.call_args_list))
            data = notify.call_args_list[0][0]
            self.assertEqual('storage.index', data[1])
            self.assertEqual('1.0', metadata['version'])
            self.assertEqual('container', metadata['container'])
            self.assertIsNone(metadata['object'])

    def indev_test_bogus_path(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(), {})
        req = FakeRequest('/5.0//',
                          environ={'REQUEST_METHOD': 'GET'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertEqual(0, len(notify.call_args_list))

    @mock.patch('six.moves.urllib.parse.quote')
    def indev_test_emit_event_fail(self, mocked_func):
        mocked_func.side_effect = Exception("a exception")
        app = middleware.SwiftSearchMiddleware(FakeApp(body=["test"]), {})
        req = FakeRequest('/1.0/account/container',
                          environ={'REQUEST_METHOD': 'GET'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            resp = list(app(req.environ, self.start_response))
            self.assertEqual(0, len(notify.call_args_list))
            self.assertEqual(["test"], resp)

    def test_put_with_swift_source(self):
        app = middleware.SwiftSearchMiddleware(FakeApp(), {})

        req = FakeRequest(
            '/1.0/account/container/obj',
            environ={'REQUEST_METHOD': 'PUT',
                     'wsgi.input':
                     six.moves.cStringIO('some stuff'),
                     'swift.source': 'RL'})
        with mock.patch('oslo_messaging.Notifier.info') as notify:
            list(app(req.environ, self.start_response))
            self.assertFalse(notify.called)
