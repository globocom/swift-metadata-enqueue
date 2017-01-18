import logging
import datetime
import threading
import pika
import json
from webob import Request

ALLOWED_METHODS = ["PUT", "POST", "DELETE"]

logger = logging.getLogger(__name__)


class SwiftSearch(object):
    """Swift middleware to index object info."""

    def __init__(self, app, conf):
        self._app = app
        self.conf = conf
        self.conn = None
        logger.info("SwiftSearch middleware initialized...")

    def __call__(self, environ, start_response):
        logger.info("call swift search middleware")

        req = Request(environ)

        if req.method in ALLOWED_METHODS:

            self.conn = self.start_queue()

            if self.conn is not None:
                self.send_queue(req)
            else:
                logger.error('')

        return self._app(environ, start_response)

    def start_queue(self):

        # Lazy conn
        if self.conn is not None:
            return self.conn

        credentials = pika.PlainCredentials(self.conf.get('queue_username'),
                                            self.conf.get('queue_password'))

        params = pika.ConnectionParameters(
            host=self.conf.get('queue_url'),
            port=int(self.conf.get('queue_port')),
            virtual_host=self.conf.get('queue_vhost'),
            credentials=credentials
        )

        try:
            connection = pika.BlockingConnection(params)
        except pika.exceptions.ConnectionClosed:
            connection = None
            logger.error('Fail to connect to RabbitMQ')

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
        logger.info("call Send Thread")

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
            logger.error("Error on send to queue")
            logger.error(e)


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return SwiftSearch(app, conf)

    return filter
