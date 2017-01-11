import logging
import datetime
import threading
import pika
import json
from webob import Request

LOG = logging.getLogger(__name__)


class SwiftSearch(object):
    """Swift middleware to index object info."""

    def __init__(self, app, conf):
        self._app = app
        self.conf = conf
        self.conn = self.start_queue()
        LOG.info("init Swift middleware to index")

    def __call__(self, environ, start_response):
        LOG.info("call swift search middleware")

        req = Request(environ)
        allowed_methods = ["PUT", "POST", "DELETE"]

        if (req.method in allowed_methods):
            if (self.conn is not None):
                self.send_queue(req)
            else:
                self.conn = self.start_queue()
                self.send_queue(req)

        return self._app(environ, start_response)

    def start_queue(self):

        connection = None

        credentials = pika.PlainCredentials(self.conf.get('queue_username'), self.conf.get('queue_password'))

        connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.conf.get('queue_url'),
                                                                           port=int(self.conf.get('queue_port')),
                                                                           virtual_host=self.conf.get('queue_vhost'),
                                                                           credentials=credentials))

        return connection

    def send_queue(self, req):
        SwiftSearch.send_thread = SendThread(self.conn, req)
        SwiftSearch.send_thread.start()


class SendThread(threading.Thread):

    def __init__(self, conn, req):
        super(SendThread, self).__init__()
        self.req = req
        self.conn = conn

    def run(self):
        LOG.info("call Send Thread")

        message = ''
        try:
            message = {
                "uri": self.req.path_info,
                "http_method": self.req.method,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }

            channel = self.conn.channel()
            channel.queue_declare(queue='swift_search', durable=True)

            channel.basic_publish(exchange='',
                                  routing_key='swift_search',
                                  body=json.dumps(message),
                                  properties=pika.BasicProperties(delivery_mode=2))
        except Exception as e:
            LOG.error("Error on send to queue")
            LOG.error(e)


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return SwiftSearch(app, conf)

    return filter
