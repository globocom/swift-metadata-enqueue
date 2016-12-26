"""
Swift Search Middleware for Swift Proxy
Configuration:
In /etc/swift/proxy-server.conf on the main pipeline add "swift-search" just
before "proxy-server" and add the following filter in the file:
.. code-block:: python
    [filter:swift-search]
    paste.filter_factory = swift-search.swiftsearchmiddleware:filter_factory
    # Queue Name.
    queue_name = swift_search
    # Queue URL.
    queue_url = rabbit://storm:storm@databases.rjocta012ahobe-126.cp.globoi.com:5672/s3busca
    # Logging level control
    log_level = INFO
"""

import logging
import datetime
import threading
import pika
from webob import Request


LOG = logging.getLogger(__name__)


class SwiftSearch(object):
    """Swift middleware to index object info."""

    thread_lock = threading.Lock()

    def __init__(self, app, conf):
        self._app = app
        self.conf = conf
        self.conn = self.start_queue()

        LOG.setLevel(getattr(logging, conf.get('log_level', 'WARNING')))

    def __call__(self, environ, start_response):
        req = Request(environ)
        allowed_methods = ["PUT", "POST", "DELETE"]

        # import ipdb
        # ipdb.set_trace()

        if (req.method in allowed_methods):
            print ">>>> In Verbs"
            # container_info = get_container_info(req.environ, self._app)
            # TODO: check if container search is enabled
            self.send_queue(req)

        return self._app(environ, start_response)

    def start_queue(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.conf.get('queue_url')))
        channel = connection.channel()
        channel.queue_declare(queue=self.conf.get('queue_name'), durable=True)

        return connection

    def send_queue(self, req):
        SwiftSearch.thread_lock.acquire()
        SwiftSearch.send_thread = SendThread(self.conn, req)
        SwiftSearch.send_thread.daemon = True
        SwiftSearch.send_thread.start()
        SwiftSearch.thread_lock.release()


class SendThread(threading.Thread):

    def __init__(self, conn, req):
        super(SendThread, self).__init__()
        self.req = req
        self.conn = conn

    def run(self):
        while True:
            try:
                message = {
                    "url": self.req.path_info,
                    "verb": self.req.method,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
                channel = self.conn.channel()
                channel.basic_publish(exchange='',
                                      routing_key=self.conf.get('queue_name'),
                                      body=message,
                                      properties=pika.BasicProperties(delivery_mode=2))
                self.conn.close()
            except BaseException:
                LOG.exception('Error on send to queue {}'.format(message))


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return SwiftSearch(app, conf)

    return filter
