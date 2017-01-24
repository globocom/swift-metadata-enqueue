"""
``swift_search`` is a middleware which sends object metadata to a queue for
post-indexing in order to enable metadata based search.

``swift_search`` uses the ``x-(account|container)-meta-search-enabled``
metadata entry to verify if the object is suitable for search index. Nothing
will be done if ``x-(account|container)-meta-search-enabled`` is not set.

``swift_search`` exports all meta headers (x-object-meta-), content-type and
content-length headers.

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

To enable the metadata indexing on an account level:

    swift post -m search-enabled:True

To enable the metadata indexing on an container level:

    swift post container -m search-enabled:True

Remove the metadata indexing:

    swift post -m search-enabled:

To create an object with indexable metadata:
    swift upload <container> <file> -H "x-object-meta-example:content"
"""
import datetime
import threading
import pika
import json

from swift.common import swob, utils
from swift.proxy.controllers.base import get_account_info, get_container_info

META_SEARCH_ENABLED = 'search-enabled'
META_OBJECT_PREFIX = 'x-object-meta'

# Object headers allowed to be indexed
ALLOWED_HEADERS = ['content-type', 'content-length', 'x-project-name']


def start_queue_conn(conf, logger):
        """
        If there's a queue channel started, return it immediately.
        Otherwise, trys to connect to the queue and create the channel.

        :returns: pika.adapters.blocking_connection.BlockingChannel if success;
                  None otherwise.
        """

        credentials = pika.PlainCredentials(conf.get('queue_username'),
                                            conf.get('queue_password'))

        params = pika.ConnectionParameters(
            host=conf.get('queue_url'),
            port=int(conf.get('queue_port')),
            virtual_host=conf.get('queue_vhost'),
            credentials=credentials
        )

        try:
            connection = pika.BlockingConnection(params)
        except (pika.exceptions.ConnectionClosed, Exception):
            logger.error('SwiftSearch: Fail to connect to RabbitMQ')
            return None

        try:
            channel = connection.channel()
            channel.queue_declare(queue='swift_search', durable=True)
        except (pika.exceptions.ConnectionClosed, Exception):
            logger.exception('SwiftSearch: Fail to create channel')
            channel = None

        return channel


class SwiftSearch(object):
    """
    Swift search middleware
    See above for a full description.
    """

    def __init__(self, app, conf):
        self.logger = utils.get_logger(conf, log_route='swift-search')

        self.app = app
        self.conf = conf
        self.queue = None

    @swob.wsgify
    def __call__(self, req):

        if not self.is_suitable_for_indexing(req):
            return self.app

        # If queue is None, start connection
        self.queue = self.queue or start_queue_conn(self.conf, self.logger)

        if self.queue:
            self.send_req_to_queue(req)
        else:
            self.logger.error(
                'SwiftSearch: No RMQ connection, skiping indexing for: %s' %
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

        # Verify method
        if req.method not in ('PUT', 'POST', 'DELETE'):
            self.logger.debug(
                'SwiftSearch: %s %s not indexable: Invalid method',
                req.method, req.path_info)
            return False

        # Verify uri
        try:
            vrs, acc, con, obj = req.split_path(2, 4, rest_with_last=True)
        except ValueError:
            # /info or similar...
            self.logger.debug(
                'SwiftSearch: %s %s not indexable: Invalid url',
                req.method, req.path_info)
            return False

        # Check if it's an account request or a container request
        if con is None or obj is None:
            self.logger.debug(
                'SwiftSearch: %s %s not indexable: Not a object',
                req.method, req.path_info)
            return False

        # Verify if container has the meta-search-enabled header
        sysmeta_c = get_container_info(req.environ, self.app)['meta']
        enabled = sysmeta_c.get(META_SEARCH_ENABLED)

        if enabled is None:

            # Verify if account has the meta-search-enabled header
            sysmeta_a = get_account_info(req.environ, self.app)['meta']
            enabled = sysmeta_a.get(META_SEARCH_ENABLED)

        if not utils.config_true_value(enabled):
            self.logger.debug(
                'SwiftSearch: %s %s not indexable: header ``%s`` not found',
                req.method, req.path_info, META_SEARCH_ENABLED)

            self.logger.debug(
                'SwiftSearch: Container headers found - {}'.format(sysmeta_c))
            self.logger.debug(
                'SwiftSearch: Account headers found - {}'.format(sysmeta_a))

        return True

    def send_req_to_queue(self, req):
        self.logger.info('SwiftSearch: starting thread to send %s to queue' %
                         req.path_info)

        SwiftSearch.send_thread = SendThread(self.queue,
                                             req,
                                             self.logger,
                                             self.conf)
        SwiftSearch.send_thread.start()


class SendThread(threading.Thread):

    def __init__(self, queue, req, logger, conf):
        super(SendThread, self).__init__()
        self.req = req
        self.queue = queue
        self.logger = logger
        self.conf = conf

    def run(self):

        headers = self._filter_headers()

        message = {
            'uri': self.req.path_info,
            'http_method': self.req.method,
            'headers': headers,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }

        # self.logger.debug(message)

        result = None

        # First try to send to queue
        try:
            result = self._publish(message)

        except (pika.exceptions.ConnectionClosed, Exception):
            self.logger.exception('SwiftSearch: Exception on send to queue')
            self.logger.error(
                'SwiftSearch: ConnectionClosed to queue. Trying to reconnect')

            # Second try to send to queue
            self.queue = start_queue_conn(self.conf, self.logger)
            if self.queue:
                result = self._publish(message)

        if result:
            self.logger.info(
                'SwiftSearch: %s %s sent to queue',
                self.req.method, self.req.path_info)
        else:
            self.logger.error(
                'SwiftSearch: %s %s failed to send',
                self.req.method, self.req.path_info)

    def _filter_headers(self):
        headers = {}

        for key in self.req.headers.keys():
            # We only send allowed headers or ``x-object-meta`` headers
            if key.lower() in ALLOWED_HEADERS or \
               key.lower().startswith(META_OBJECT_PREFIX):
                headers[key] = self.req.headers.get(key)

        return headers

    def _publish(self, message):
        return self.queue.basic_publish(
            exchange='',
            routing_key='swift_search', body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2)
        )


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    # Registers information to be retrieved on /info
    utils.register_swift_info('swift_search')

    def filter(app):
        return SwiftSearch(app, conf)

    return filter
