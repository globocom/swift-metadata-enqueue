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

from swift.common.swob import wsgify
from swift.common.utils import get_logger
from swift.proxy.controllers.base import get_container_info

from eventlet import Timeout
import six
if six.PY3:
    from eventlet.green.urllib import request as urllib2
else:
    from eventlet.green import urllib2

QUEUE_URL = "localhost:5672"


class SwiftSearchMiddleware(object):

    def __init__(self, app, conf):
        self.app = app
        self.logger = get_logger(conf, log_route='swift_search')

    @wsgify
    def __call__(self, req):
        object_url = req.path_info

        if (req.method == 'PUT' or req.method == 'POST' or req.method == 'DELETE'):
                # container_info = get_container_info(req.environ, self.app)
                # create a POST request with obj url
                with Timeout(20):
                    try:
                        urllib2.urlopen(QUEUE_URL, data=object_url).read()
                    except (Exception, Timeout):
                        self.logger.exception(
                            'failed POST to queue %s' % webhook)
                    else:
                        self.logger.info(
                            'successfully called queue %s' % webhook

        resp = req.get_response(self.app)
        return resp


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)
    def search_filter(app, conf):
        return SwiftSearchMiddleware(app)
    return search_filter
