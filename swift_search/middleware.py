"""
``swift_search`` is a middleware which sends object metadata to a queue for
post-indexing in order to enable metadata based search.

``swift_search`` uses the ``x-(account|container)-meta-search-enabled``
metadata entry to verify if the object is suitable for search index. Nothing
will be done if ``x-(account|container)-meta-search-enabled`` is not set.

The ``swift_search`` middleware should be added to the pipeline in your
``/etc/swift/proxy-server.conf`` file just after any auth middleware.
For example:

    [pipeline:main]
    pipeline = catch_errors cache tempauth swift_search proxy-server

    [filter:swift_search]
    use = egg:swift#swift_search
    queue_username
    queue_password
    queue_url
    queue_port
    queue_vhost
    queue_conn_timeout

To enable the metadata indexing on an account level:

    swift -A http://127.0.0.1:8080/auth/v1.0 -U account:reseller -K secret \
post -m search-enabled:True

To enable the metadata indexing on an container level:

    swift -A http://127.0.0.1:8080/auth/v1.0 -U account:reseller -K secret \
post container -m search-enabled:True

Remove the metadata indexing:

    swift -A http://127.0.0.1:8080/auth/v1.0 -U account:reseller -K secret \
post -m search-enabled:
"""
import datetime
import threading
import pika
import json

from swift.common import get_logger, swob, utils
from swift.common.request_helpers import get_sys_meta_prefix
from swift.proxy.controllers.base import get_account_info, get_container_info

SYSMETA_SEARCH_ENABLED = 'search-enabled'
SYSMETA_ACCOUNT = get_sys_meta_prefix('account') + SYSMETA_SEARCH_ENABLED
SYSMETA_CONTAINER = get_sys_meta_prefix('container') + SYSMETA_SEARCH_ENABLED


class SwiftSearch(object):
    """
    Swift search middleware
    See above for a full description.
    """

    def __init__(self, app, conf):
        self.logger = get_logger(conf, log_route='swift-search')

        self.app = app
        self.conf = conf
        self.queue_channel = None

    @swob.wsgify
    def __call__(self, req):
        self.logger.debug('SwiftSearch called...')

        if not self.is_suitable_for_indexing(req):
            return self.app

        self.queue_channel = self.start_queue_conn()

        if self.queue_channel is not None:
            self.send_req_to_queue(req)
        else:
            self.logger.info('No RMQ connection, skiping indexing for: %s' %
                             req.path_info)

        return self.app

    def is_suitable_for_indexing(self, req):
        """
        Wheter the request is suitable for indexing. Conditions:

         * Method: PUT, POST or DELETE
         * Object request
         * Account or Container must have ``search-enabled`` meta set to True

         :param req
         :returns: True if the request is able to indexing; False otherwise.
        """
        if req.method not in ("PUT", "POST", "DELETE"):
            return False

        try:
            vrs, acc, con, obj = req.split_path(2, 4, rest_with_last=True)
        except ValueError:
            # /info or similar...
            return False

        # Check if it's an account request or a container request
        if con is None or obj is None:
            return False

        sysmeta_c = get_container_info(req.environ, self.app)['sysmeta']
        sysmeta_a = get_account_info(req.environ, self.app)['sysmeta']

        enabled = sysmeta_c.get(SYSMETA_SEARCH_ENABLED)
        if enabled is None:
            enabled = sysmeta_a.get(SYSMETA_SEARCH_ENABLED)

        return utils.config_true_value(enabled)

    def start_queue_conn(self):
        """
        If there's a queue channel started, return it immediately.
        Otherwise, trys to connect to the queue and create the channel.

        :returns: pika.adapters.blocking_connection.BlockingChannel if success;
                  None otherwise.
        """

        if self.queue_channel is not None:
            return self.queue_channel

        credentials = pika.PlainCredentials(self.conf.get('queue_username'),
                                            self.conf.get('queue_password'))

        blocked_conn_timeout = int(self.conf.get('queue_conn_timeout', 1))
        params = pika.ConnectionParameters(
            host=self.conf.get('queue_url'),
            port=int(self.conf.get('queue_port')),
            virtual_host=self.conf.get('queue_vhost'),
            blocked_connection_timeout=blocked_conn_timeout,
            credentials=credentials
        )

        try:
            connection = pika.BlockingConnection(params)
        except (pika.exceptions.ConnectionClosed, Exception):
            self.logger.error('Fail to connect to RabbitMQ')
            return None

        try:
            channel = connection.channel()
            channel.queue_declare(queue='swift_search', durable=True)
        except (pika.exceptions.ConnectionClosed, Exception):
            self.logger.exception('Fail to create channel')
            channel = None

        return channel

    def send_req_to_queue(self, req):
        SwiftSearch.send_thread = SendThread(self.queue_channel,
                                             req,
                                             self.logger)
        SwiftSearch.send_thread.start()


class SendThread(threading.Thread):

    def __init__(self, queue_channel, req, logger):
        super(SendThread, self).__init__()
        self.req = req
        self.queue_channel = queue_channel
        self.logger = logger

    def run(self):
        self.logger.debug('SendThread.run started')

        message = {
            'uri': self.req.path_info,
            'http_method': self.req.method,
            'headers': self.req.headers,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }

        self.logger.debug(message)

        try:
            resp = self.queue_channel.basic_publish(
                exchange='',
                routing_key='swift_search', body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2)
            )

            if not resp:
                self.logger.error('Fail to send message to queue')
                self.logger.error(message)

        except Exception:
            self.logger.exception('Exception on send to queue')
            self.logger.error(message)


def search_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    # Registers information to be retrieved on /info
    utils.register_swift_info('swift_search')

    def filter(app):
        return SwiftSearch(app, conf)

    return filter
