#!/usr/bin/env python
# Copyright (c) 2014 SwiftStack, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from functools import wraps
import unittest

from swift.common import swob
from swift_undelete import middleware as md


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
    def test_defaults(self):
        app = FakeApp()
        undelete = md.filter_factory({})(app)

        self.assertEqual(undelete.trash_prefix, ".trash-")
        self.assertEqual(undelete.trash_lifetime, 86400 * 90)
        self.assertFalse(undelete.block_trash_deletes)

    def test_non_defaults(self):
        app = FakeApp()
        undelete = md.filter_factory({
            'trash_prefix': '.heap__',
            'trash_lifetime': '31536000',
            'block_trash_deletes': 'on',
        })(app)

        self.assertEqual(undelete.trash_prefix, ".heap__")
        self.assertEqual(undelete.trash_lifetime, 31536000)
        self.assertTrue(undelete.block_trash_deletes)


class MiddlewareTestCase(unittest.TestCase):
    """
    Just a base class for other test cases. Some setup, some utility methods.
    Nothing too exciting.
    """
    def setUp(self):
        self.app = FakeApp()
        self.undelete = md.filter_factory({})(self.app)

    def call_mware(self, req, expect_exception=False):
        status = [None]
        headers = [None]

        def start_response(s, h, ei=None):
            status[0] = s
            headers[0] = h

        body_iter = self.undelete(req.environ, start_response)
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


def with_req(path, method, headers=None, as_superuser=False):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            req = swob.Request.blank(path)
            req.method = method
            if headers:
                req.headers.update(headers)
            if as_superuser:
                req.environ['reseller_request'] = True
            kwargs['req'] = req
            return func(*args, **kwargs)
        return wrapped
    return decorator


class TestPassthrough(MiddlewareTestCase):
    @with_req('/v1/a', 'DELETE')
    def test_account_passthrough(self, req):
        """
        Account requests are passed through unmodified.
        """
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls, [('DELETE', '/v1/a')])

    @with_req('/v1/a/c', 'DELETE')
    def test_container_passthrough(self, req):
        """
        Container requests are passed through unmodified.
        """
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls, [('DELETE', '/v1/a/c')])

    @with_req('/v1/a/c/o', 'PUT')
    def test_object_passthrough(self, req):
        """
        Container requests are passed through unmodified.
        """
        self.app.responses = [{'status': '201 Created'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "201 Created")
        self.assertEqual(self.app.calls, [('PUT', '/v1/a/c/o')])


class TestObjectDeletion(MiddlewareTestCase):
    @with_req('/v1/a/elements/Cf', 'DELETE')
    def test_deleting_nonexistent_object(self, req):
        # If the object isn't there, ignore the 404 on COPY and pass the
        # DELETE request through. It might be an expired object, in which case
        # the object DELETE will actually get it out of the container listing
        # and free up some space.
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/a': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/a/elements': {
                 'status': 200, 'sysmeta': {}}}},
            # COPY request
            {'status': '404 Not Found'},
            # trash-versions container creation request
            #
            # Ideally we'd skip this stuff, but we can't tell the difference
            # between object-not-found (404) and
            # destination-container-not-found (also 404).
            {'status': '202 Accepted'},
            # trash container creation request
            {'status': '202 Accepted'},
            # second COPY attempt:
            {'status': '404 Not Found'},
            # DELETE request
            {'status': '404 Not Found',
             'headers': [('X-Exophagous', 'ungrassed')]}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(headers.get('X-Exophagous'), 'ungrassed')
        self.assertEqual(self.app.calls, [
            ('HEAD', '/v1/a'),
            ('HEAD', '/v1/a/elements'),
            ('COPY', '/v1/a/elements/Cf'),
            ('PUT', '/v1/a/.trash-elements-versions'),
            ('PUT', '/v1/a/.trash-elements'),
            ('COPY', '/v1/a/elements/Cf'),
            ('DELETE', '/v1/a/elements/Cf')])

    @with_req('/v1/MY_account/cats/kittens.jpg', 'DELETE')
    def test_delete_with_opted_out_container(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/MY_account': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/MY_account/cats': {
                 'status': 200, 'sysmeta': {'undelete-enabled': 'False'}}}},
            # DELETE request
            {'status': '204 No Content',
             'headers': [('X-Decadation', 'coprose')]}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        self.assertEqual(headers['X-Decadation'], 'coprose')

        self.assertEqual(3, len(self.app.calls))

        # First, we check that the account and container for opt-out
        method, path = self.app.calls[0]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account')

        method, path = self.app.calls[1]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account/cats')

        # Since the container opted out, no COPY request; we skip straight to
        # performing the DELETE request (and send that response to the client
        # unaltered)
        method, path, headers = self.app.calls_with_headers[2]
        self.assertEqual(method, 'DELETE')
        self.assertEqual(path, '/v1/MY_account/cats/kittens.jpg')

    @with_req('/v1/MY_account/cats/kittens.jpg', 'DELETE')
    def test_delete_with_opted_out_account(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/MY_account': {
                 'status': 200, 'sysmeta': {'undelete-enabled': 'False'}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/MY_account/cats': {
                 'status': 200, 'sysmeta': {}}}},
            # DELETE request
            {'status': '204 No Content',
             'headers': [('X-Decadation', 'coprose')]}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        self.assertEqual(headers['X-Decadation'], 'coprose')

        self.assertEqual(3, len(self.app.calls))

        # First, we check that the account and container for opt-out
        method, path = self.app.calls[0]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account')

        # First, we check that the account and container for opt-out
        method, path = self.app.calls[1]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account/cats')

        # Since the account opted out, no COPY request;
        # we skip straight to performing the DELETE request (and send that
        # response to the client unaltered)
        method, path, headers = self.app.calls_with_headers[2]
        self.assertEqual(method, 'DELETE')
        self.assertEqual(path, '/v1/MY_account/cats/kittens.jpg')

    @with_req('/v1/MY_account/cats/kittens.jpg', 'DELETE')
    def test_copy_to_existing_trash_container(self, req):
        self.undelete.trash_lifetime = 1997339
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/MY_account': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/MY_account/cats': {
                 'status': 200, 'sysmeta': {}}}},
            # COPY request
            {'status': '201 Created',
             'headers': [('X-Sir-Not-Appearing-In-This-Response', 'yup')]},
            # DELETE request
            {'status': '204 No Content',
             'headers': [('X-Decadation', 'coprose')]}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        # the client gets whatever the DELETE coughed up
        self.assertNotIn('X-Sir-Not-Appearing-In-This-Response', headers)
        self.assertEqual(headers['X-Decadation'], 'coprose')

        self.assertEqual(4, len(self.app.calls))

        # First, we check that the account and container haven't opted out
        method, path = self.app.calls[0]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account')

        method, path = self.app.calls[1]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account/cats')

        # Second, we performed a COPY request to save the object into the trash
        method, path, headers = self.app.calls_with_headers[2]
        self.assertEqual(method, 'COPY')
        self.assertEqual(path, '/v1/MY_account/cats/kittens.jpg')
        self.assertEqual(headers['Destination'], '.trash-cats/kittens.jpg')
        self.assertEqual(headers['X-Delete-After'], str(1997339))

        # Finally, we actually perform the DELETE request (and send that
        # response to the client unaltered)
        method, path, headers = self.app.calls_with_headers[3]
        self.assertEqual(method, 'DELETE')
        self.assertEqual(path, '/v1/MY_account/cats/kittens.jpg')

    @with_req('/v1/MY_account/cats/kittens.jpg', 'DELETE')
    def test_copy_to_existing_trash_container_no_expiration(self, req):
        self.undelete.trash_lifetime = 0
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/MY_account': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/MY_account/cats': {
                 'status': 200, 'sysmeta': {}}}},
            # COPY request
            {'status': '201 Created'},
            # DELETE request
            {'status': '204 No Content'}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        self.assertEqual(4, len(self.app.calls))

        # First, we check that the account and container haven't opted out
        method, path = self.app.calls[0]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account')

        method, path = self.app.calls[1]
        self.assertEqual(method, 'HEAD')
        self.assertEqual(path, '/v1/MY_account/cats')

        method, path, headers = self.app.calls_with_headers[2]
        self.assertEqual(method, 'COPY')
        self.assertEqual(path, '/v1/MY_account/cats/kittens.jpg')
        self.assertNotIn('X-Delete-After', headers)

    @with_req('/v1/a/elements/Lv', 'DELETE')
    def test_copy_to_missing_trash_container(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/a': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/a/elements': {
                 'status': 200, 'sysmeta': {}}}},
            # first COPY attempt: trash container doesn't exist
            {'status': '404 Not Found'},
            # trash-versions container creation request
            {'status': '201 Created'},
            # trash container creation request
            {'status': '201 Created'},
            # second COPY attempt:
            {'status': '404 Not Found'},
            # DELETE request
            {'status': '204 No Content'}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        self.assertEqual(self.app.calls, [
            ('HEAD', '/v1/a'),
            ('HEAD', '/v1/a/elements'),
            ('COPY', '/v1/a/elements/Lv'),
            ('PUT', '/v1/a/.trash-elements-versions'),
            ('PUT', '/v1/a/.trash-elements'),
            ('COPY', '/v1/a/elements/Lv'),
            ('DELETE', '/v1/a/elements/Lv')])

    @with_req('/v1/a/elements/Te', 'DELETE')
    def test_copy_error(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/a': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/a/elements': {
                 'status': 200, 'sysmeta': {}}}},
            # COPY attempt: some mysterious error with some headers
            {'status': '503 Service Unavailable',
             'headers': [('X-Scraggedness', 'Goclenian')],
             'body_iter': ['dunno what happened boss']}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(headers.get('X-Scraggedness'), 'Goclenian')
        self.assertIn('what happened', body)
        self.assertEqual(self.app.calls, [
            ('HEAD', '/v1/a'),
            ('HEAD', '/v1/a/elements'),
            ('COPY', '/v1/a/elements/Te')])

    @with_req('/v1/a/elements/U', 'DELETE')
    def test_copy_missing_trash_cont_error_creating_vrs_container(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/a': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/a/elements': {
                 'status': 200, 'sysmeta': {}}}},
            # first COPY attempt: trash container doesn't exist
            {'status': '404 Not Found'},
            # trash-versions container creation request: failure!
            {'status': '403 Forbidden',
             'headers': [('X-Pupillidae', 'Barry')],
             'body_iter': ['oh hell no']}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "403 Forbidden")
        self.assertEqual(headers.get('X-Pupillidae'), 'Barry')
        self.assertIn('oh hell no', body)
        self.assertEqual(self.app.calls, [
            ('HEAD', '/v1/a'),
            ('HEAD', '/v1/a/elements'),
            ('COPY', '/v1/a/elements/U'),
            ('PUT', '/v1/a/.trash-elements-versions')])

    @with_req('/v1/a/elements/Mo', 'DELETE')
    def test_copy_missing_trash_container_error_creating_container(self, req):
        self.app.responses = [
            # account HEAD request
            {'status': '200 OK',
             'environ': {'swift.account/a': {
                 'status': 200, 'sysmeta': {}}}},
            # container HEAD request
            {'status': '200 OK',
             'environ': {'swift.container/a/elements': {
                 'status': 200, 'sysmeta': {}}}},
            # first COPY attempt: trash container doesn't exist
            {'status': '404 Not Found'},
            # trash-versions container creation request
            {'status': '201 Created'},
            # trash container creation request: fails!
            {'status': "418 I'm a teapot",
             'headers': [('X-Body-Type', 'short and stout')],
             'body_iter': ['here is my handle, here is my spout']}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "418 I'm a teapot")
        self.assertEqual(headers.get('X-Body-Type'), 'short and stout')
        self.assertIn('spout', body)
        self.assertEqual(self.app.calls, [
            ('HEAD', '/v1/a'),
            ('HEAD', '/v1/a/elements'),
            ('COPY', '/v1/a/elements/Mo'),
            ('PUT', '/v1/a/.trash-elements-versions'),
            ('PUT', '/v1/a/.trash-elements')])

    @with_req('/v1/a/.trash-borkbork/bork', 'DELETE')
    def test_delete_from_trash_as_non_superuser(self, req):
        """
        Objects in trash containers can only be deleted by superusers.
        """
        self.app.responses = [{'status': '204 No Content'}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "403 Forbidden")
        self.assertEqual(self.app.calls, [])

    @with_req('/v1/a/.trash-borkbork/bork', 'DELETE', as_superuser=True)
    def test_delete_from_trash_as_superuser(self, req):
        """
        Objects in trash containers don't get saved.
        """
        self.app.responses = [{'status': '204 No Content'}]

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "204 No Content")
        self.assertEqual(self.app.calls,
                         [('DELETE', '/v1/a/.trash-borkbork/bork')])

    @with_req('/v1/a/.trash-borkbork/bork', 'DELETE', as_superuser=True)
    def test_delete_from_trash_blocked(self, req):
        self.undelete.block_trash_deletes = True

        status, headers, body = self.call_mware(req)
        self.assertEqual(status, "405 Method Not Allowed")
        self.assertEqual(self.app.calls, [])


class TestSysmetaPassthrough(MiddlewareTestCase):
    @with_req('/v1/a', 'POST', {
        'x-undelete-enabled': 'foo'}, as_superuser=True)
    def test_account_passthrough_to_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('POST', '/v1/a', {
            'X-Undelete-Enabled': 'foo',
            'X-Account-Sysmeta-Undelete-Enabled': 'False',
            'Host': 'localhost:80'})])

    @with_req('/v1/a', 'POST', {
        'x-undelete-enabled': 'yes'}, as_superuser=True)
    def test_account_can_remove_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('POST', '/v1/a', {
            'X-Undelete-Enabled': 'yes',
            'X-Account-Sysmeta-Undelete-Enabled': 'True',
            'Host': 'localhost:80'})])

    @with_req('/v1/a', 'POST')
    def test_account_passthrough_from_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK', 'headers': [(
            'X-Account-Sysmeta-Undelete-Enabled', 'False')]}]

        status, headers, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls, [('POST', '/v1/a')])

        self.assertIn('X-Undelete-Enabled', headers)
        self.assertEqual(headers['X-Undelete-Enabled'], 'False')
        self.assertIn('X-Account-Sysmeta-Undelete-Enabled', headers)
        self.assertEqual(headers['X-Account-Sysmeta-Undelete-Enabled'],
                         'False')

    @with_req('/v1/a', 'POST', {'x-undelete-enabled': 'foo'})
    def test_account_no_passthrough_to_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('POST', '/v1/a', {
            'X-Undelete-Enabled': 'foo',
            'Host': 'localhost:80'})])

    @with_req('/v1/a/c', 'PUT', {
        'x-undelete-enabled': 'bar'}, as_superuser=True)
    def test_container_passthrough_to_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('PUT', '/v1/a/c', {
            'X-Undelete-Enabled': 'bar',
            'X-Container-Sysmeta-Undelete-Enabled': 'False',
            'Host': 'localhost:80'})])

    @with_req('/v1/a/c', 'PUT', {
        'x-undelete-enabled': 'default'}, as_superuser=True)
    def test_container_can_remove_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('PUT', '/v1/a/c', {
            'X-Undelete-Enabled': 'default',
            'X-Container-Sysmeta-Undelete-Enabled': '',
            'Host': 'localhost:80'})])

    @with_req('/v1/a/c', 'GET')
    def test_container_passthrough_from_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK', 'headers': [(
            'X-Container-Sysmeta-Undelete-Enabled', 'True')]}]

        status, headers, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls, [('GET', '/v1/a/c')])

        self.assertIn('X-Undelete-Enabled', headers)
        self.assertEqual(headers['X-Undelete-Enabled'], 'True')
        self.assertIn('X-Container-Sysmeta-Undelete-Enabled', headers)
        self.assertEqual(headers['X-Container-Sysmeta-Undelete-Enabled'],
                         'True')

    @with_req('/v1/a/c', 'PUT', {'x-undelete-enabled': 'no'})
    def test_container_no_passthrough_to_sysmeta(self, req):
        self.app.responses = [{'status': '200 OK'}]

        status, _, _ = self.call_mware(req)
        self.assertEqual(status, "200 OK")
        self.assertEqual(self.app.calls_with_headers, [('PUT', '/v1/a/c', {
            'X-Undelete-Enabled': 'no',
            'Host': 'localhost:80'})])

if __name__ == '__main__':
    unittest.main()
