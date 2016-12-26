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
# Utils
import datetime
import logging

# Pika
import pika
import sys

# Threading
import threading

# Swift
from swift.common.swob import wsgify
from swift.proxy.controllers.base import get_container_info

LOG = logging.getLogger(__name__)


class SwiftSearchMiddleware(object):
    """Swift middleware used for process object info for search."""

    threadLock = threading.Lock()

    def __init__(self, app, conf):

        self._app = app
        self.conf = conf

        self.connection = start_queue()

        LOG.setLevel(getattr(logging, conf.get('log_level', 'WARNING')))

    @wsgify
    def __call__(self, req):

        optin = check_container(req)

        if (optin is not None and optin and (req.method == "PUT" or req.method == "POST" or req.method == "DELETE")):
            LOG.info('Starting Queue')
            self.send_queue(req)

        response = req.get_response(self.app)

    def start_queue(self):

            connection = connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.conf.get('queue_url')))

            channel = connection.channel()

            channel.queue_declare(queue=self.conf.get('queue_name'), durable=True)

            return connection

    def check_container(self, req):

        container_info = get_container_info(req.environ, self.app)
        optin = container_info['meta'].get('index')

        return optin

    def send_queue(self, req):

        SwiftSearchMiddleware.threadLock.acquire()

        SwiftSearchMiddleware.event_sender = SendEventThread(self, req)
        SwiftSearchMiddleware.event_sender.daemon = True
        SwiftSearchMiddleware.event_sender.start()

        SwiftSearchMiddleware.threadLock.release()


class SendEventThread(threading.Thread):

    def __init__(self, req):

        super(SendEventThread, self).__init__()
        self.req = req

    def run(self):

        while True:
            try:

                message = {
                        "url": self.req.path_info:
                        "verb": self.req.method,
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                }

                channel = self.connection.channel()

                channel.basic_publish(exchange='', routing_key=self.conf.get('queue_name'),
                    body=message, properties=pika.BasicProperties(delivery_mode=2))

                self.connection.close()
            except BaseException:
                LOG.exception('Error on send to queue ' + message)


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return SwiftSearhMiddleware(app, conf)

    return filter
