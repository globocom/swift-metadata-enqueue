import logging
import datetime
import threading
import pika
from webob import Request


LOG = logging.getLogger(__name__)


class SwiftSearch(object):
    """Swift middleware to index object info."""

    # lock until has acquired
    thread_lock = threading.Lock()

    def __init__(self, app, conf):
        self._app = app
        self.conf = conf
        self.conn = self.start_queue()

        LOG.setLevel(getattr(logging, conf.get('log_level', 'WARNING')))

    def __call__(self, environ, start_response):
        req = Request(environ)
        allowed_methods = ["PUT", "POST", "DELETE"]

        if (req.method in allowed_methods):
            # container_info = get_container_info(req.environ, self._app)
            # TODO: check if container search is enabled
            self.send_queue(req)

        return self._app(environ, start_response)

    def start_queue(self):

        connection = ""

        try:
            # connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.conf.get('queue_url')))
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.conf.get('queue_url'), 
                port=self.conf.get('queue_port'), 
                virtual_host=self.conf.get('queue_vhost'), 
                credentials=pika.PlainCredentials(self.conf.get('queue_username'), self.conf.get('queue_password'))))
            channel = connection.channel()
            channel.queue_declare(queue=self.conf.get('queue_name'), durable=True)
        except Exception:
            LOG.exception('Error on start queue')

        return connection

    def send_queue(self, req):
        # acquire and lock subsequents attempts to acquire until realease
        SwiftSearch.thread_lock.acquire()
        SwiftSearch.send_thread = SendThread(self.conn, req)
        SwiftSearch.send_thread.daemon = True
        SwiftSearch.send_thread.start()
        # release called in the locked state only
        SwiftSearch.thread_lock.release()


class SendThread(threading.Thread):

    def __init__(self, conn, req):
        super(SendThread, self).__init__()
        self.req = req
        self.conn = conn

    def run(self):
        message = ''
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
