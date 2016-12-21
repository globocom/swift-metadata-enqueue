"""
Swift Search Middleware for Swift Proxy
Configuration:
In /etc/swift/proxy-server.conf on the main pipeline add "swift-search" just
before "proxy-server" and add the following filter in the file:
.. code-block:: python
    [filter:swift-search]
    paste.filter_factory = swift-search.swiftsearchmiddleware:filter_factory
    # Set control_exchange to publish to.
    control_exchange = swift
    # Set transport url
    url = rabbit://storm:storm@databases.rjocta012ahobe-126.cp.globoi.com:5672/s3busca
    # set messaging driver
    driver = messagingv2
    # set topic
    topic = indexer
    # Whether to send events to messaging driver in a background thread
    nonblocking_notify = False
    # Queue size for sending notifications in background thread (0=unlimited).
    send_queue_size = 5000
    # Logging level control
    log_level = INFO
"""
# Utils
import datetime
import functools
import logging

# Oslo
from oslo_config import cfg
import oslo_messaging
from oslo_utils import strutils

# Queue
import six
import six.moves.queue as queue
# import six.moves.urllib.parse as urlparse

# Threading
import threading

# Swift
from swift.common.http import is_success
from swift.common.swob import wsgify
from swift.common.utils import split_path
from swift.proxy.controllers.base import get_container_info

LOG = logging.getLogger(__name__)

PUBLISHER_ID = 'swiftsearchmiddleware'
EVENT_TYPE = 'storage.index'


def _log_and_ignore_error(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            LOG.exception('Ocorreu um erro ao processar a chamada : queue %s ', e)
    return wrapper


class SwiftSearchMiddleware(object):
    """Swift middleware used for process object info for search."""

    event_queue = None
    threadLock = threading.Lock()

    def __init__(self, app, conf):
        self._app = app
        self.conf = conf

        self._notifier = get_notifier()
        self.start_queue()

        LOG.setLevel(getattr(logging, conf.get('log_level', 'WARNING')))

    @wsgify
    def __call__(self, req):

        optin = check_container(req)

        if (optin is not None):
            LOG.info('Sending Event.')
            self.emit_event(req)

    def check_container(self, req):

        obj = None
        try:
            (version, account, container, obj) = \
                split_path(req.path_info, 4, 4, True)
        except ValueError:
            # not an object request
            pass

        response = req.get_response(self.app)

        verb = req.method
        optin = ""

        if obj and is_success(response.status_int) and (verb == 'PUT' or verb == 'POST' or verb == 'DELETE'):
            container_info = get_container_info(req.environ, self.app)
            optin = container_info['meta'].get('index')

        return optin

    def start_queue(self):

        # NOTE: If the background thread's send queue fills up, the event will
        #  be discarded

        # For backward compatibility we default to False and wait for sending to complete.
        # Swift proxy to suspend if the destination is unavailable.
        self.nonblocking_notify = strutils.bool_from_string(
            self.conf.get('nonblocking_notify', False))

        # Initialize the sending queue and thread, SINGLETON
        if self.nonblocking_notify and SwiftSearchMiddleware.event_queue is None:
            SwiftSearchMiddleware.threadLock.acquire()

            if SwiftSearchMiddleware.event_queue is None:
                send_queue_size = int(self.conf.get('send_queue_size', 1000))
                SwiftSearchMiddleware.event_queue = queue.Queue(send_queue_size)
                self.start_sender_thread()

            SwiftSearchMiddleware.threadLock.release()

    def get_notifier(self):

        # default exchange under which topics are scoped
        oslo_messaging.set_transport_defaults(conf.get('control_exchange', 'swift'))

        # The Notifier class is used for sending notification messages over a messaging transport
        # get transportUrl and virtualhost
        # specifying publisher_id
        # drive recommended for use rabbitmq
        # define routing_key for topic
        return oslo_messaging.Notifier(oslo_messaging.get_transport(cfg.CONF, url=self.conf.get('url')),
                        publisher_id=PUBLISHER_ID,
                        driver=self.conf.get('driver', 'messagingv2'),
                        topic=self.conf.get('topic', 'notifications.indexer'))

    @_log_and_ignore_error
    def emit_event(self, req, outcome='success'):

        event = {
            "message_id": six.text_type(uuid.uuid4()),
            "publisher_id": PUBLISHER_ID,
            "priority": "INFO",
            "event_type": EVENT_TYPE,
            "payload": {
                "url": req.path_info: {
                    "verb": req.method,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
            }
        }

        if self.nonblocking_notify:
            try:
                SwiftSearchMiddleware.event_queue.put(event, False)
                if not SwiftSearchMiddleware.event_sender.is_alive():
                    SwiftSearchMiddleware.threadLock.acquire()
                    self.start_sender_thread()
                    SwiftSearchMiddleware.threadLock.release()

            except queue.Full:
                LOG.warning('Send queue FULL: Event %s not added', event.message_id)
        else:
            SwiftSearchMiddleware.send_notification(self._notifier, event)

    def start_sender_thread(self):
        SwiftSearchMiddleware.event_sender = SendEventThread(self._notifier)
        SwiftSearchMiddleware.event_sender.daemon = True
        SwiftSearchMiddleware.event_sender.start()

    @staticmethod
    def send_notification(notifier, event):
        notifier.info({}, EVENT_TYPE, event.as_dict())


class SendEventThread(threading.Thread):

    def __init__(self, notifier):
        super(SendEventThread, self).__init__()
        self.notifier = notifier

    def run(self):
        """Send events without blocking swift proxy."""
        while True:
            try:
                event = SwiftSearchMiddleware.event_queue.get()
                LOG.debug('Get event %s processing now ', event.id)
                SwiftSearchMiddleware.send_notification(self.notifier, event)
                LOG.debug('Sended %s event.', event.id)
            except BaseException:
                LOG.exception("Error on send event " + event.id)


def search_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return SwiftSearhMiddleware(app, conf)
    return filter
