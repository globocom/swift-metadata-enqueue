"""
``metadata_queuer`` is a middleware which sends object metadata to a
queue for post-indexing in order to enable metadata based search.

``metadata_queuer`` uses the
``x-(account|container)-meta-indexer-enabled``
metadata entry to verify if the object is suitable for search index. Nothing
will be done if ``x-(account|container)-meta-queuer-enabled`` is not set.

``metadata_queuer`` exports all meta headers (x-object-meta-),
content-type and content-length headers.

The ``metadata_queuer`` middleware should be added to the pipeline in
your ``/etc/swift/proxy-server.conf`` file just after any auth middleware.
For example:

    [pipeline:main]
    pipeline = catch_errors cache tempauth metadata_queuer proxy-server

    [filter:metadata_queuer]
    use = egg:swift#metadata_queuer
    queue_username
    queue_password
    queue_url
    queue_port
    queue_vhost

To enable the metadata indexing on an account level:

    swift post -m queuer-enabled:True

To enable the metadata indexing on an container level:

    swift post container -m queuer-enabled:True

Remove the metadata indexing:

    swift post -m queuer-enabled:

To create an object with indexable metadata:
    swift upload <container> <file> -H "x-object-meta-example:content"
"""
import pika
import json

from datetime import datetime
from swift.common import swob, utils
from swift.proxy.controllers.base import get_account_info, get_container_info

META_SEARCH_ENABLED = 'queuer-enabled'
META_OBJECT_PREFIX = 'x-object-meta'

# Object headers allowed to be indexed
ALLOWED_HEADERS = ['content-type', 'content-length', 'x-project-name']
ALLOWED_METHODS = ('PUT', 'POST', 'DELETE')


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
        logger.debug('Queuer: Connection Queue connection OK')
    except (pika.exceptions.ConnectionClosed, Exception):
        logger.error('Queuer: Fail to connect to RabbitMQ')
        return None

    try:
        channel = connection.channel()
        channel.queue_declare(queue='swift_search', durable=True)
        logger.debug('Queuer: Queue Channel OK')
    except (pika.exceptions.ConnectionClosed, Exception):
        logger.exception('Queuer: Fail to create channel')
        channel = None

    return channel


class Queuer(object):
    """
    Swift search middleware
    See above for a full description.
    """

    def __init__(self, app, conf):
        self.logger = utils.get_logger(conf, log_route='metadata-indexer')

        self.app = app
        self.conf = conf
        self.queue = None

    @swob.wsgify
    def __call__(self, req):

        # If this request is not suitable for indexing, return immediately
        if not self.is_suitable_for_indexing(req):
            return self.app

        # If queue is None, start connection
        self.queue = self.queue or start_queue_conn(self.conf, self.logger)

        if self.queue:
            self.send_req_to_queue(self.queue, req)
        else:
            self.logger.error(
                'Queuer: Fail to connect to queue, skiping %s %s' %
                (req.method, req.path_info))

        return self.app

    def is_suitable_for_indexing(self, req):
        """
        Wheter the request is suitable for indexing. Conditions:

         * Method: PUT, POST or DELETE
         * Object request
         * Account or Container must have ``queuer-enabled`` meta set to True

         :param req
         :returns: True if the request is able to indexing; False otherwise.
        """
        log_msg = 'Queuer: %s %s not indexable: %s'

        # Verify method
        if not self._is_valid_method(req):
            reason = 'Invalid method'
            self.logger.debug(log_msg, req.method, req.path_info, reason)
            return False

        # Verify url
        if not self._is_valid_object_url(req):
            reason = 'Invalid object URL'
            self.logger.debug(log_msg, req.method, req.path_info, reason)
            return False

        # Verify if container has the meta-queuer-enabled header
        if not self._has_optin_header(req):
            reason = 'Header ``%s`` not found' % META_SEARCH_ENABLED
            self.logger.debug(log_msg, req.method, req.path_info, reason)
            return False

        return True

    def send_req_to_queue(self, queue, req):
        """
        Sends a message to the queue with the proper information.
        If the fistr try to send fails, try to reconnect to the queue and
        try to send it again
        """
        message = self._mk_message(req)
        result = None

        # First try to send to queue
        try:
            result = self._publish(queue, message)

        except (pika.exceptions.ConnectionClosed, Exception):
            self.logger.exception('Queuer: Exception on sending to queue')

            # Second try to send to queue
            # Update the queue property
            self.queue = start_queue_conn(self.conf, self.logger)
            if self.queue:
                result = self._publish(self.queue, message)

        if result:
            self.logger.info(
                'Queuer: %s %s sent to queue',
                req.method, req.path_info)
        else:
            self.logger.error(
                'Queuer: %s %s failed to send',
                req.method, req.path_info)

    def _filter_headers(self, req):
        headers = {}

        for key in req.headers.keys():
            # We only send allowed headers and ``x-object-meta`` headers
            if key.lower() in ALLOWED_HEADERS or \
               key.lower().startswith(META_OBJECT_PREFIX):

                headers[key] = req.headers.get(key)

        return headers

    def _mk_message(self, req):
        """
        Creates a dictionary with the information that will be send to the
        queue.
        """
        return {
            'uri': req.path_info,
            'http_method': req.method,
            'headers': self._filter_headers(req),
            'timestamp': datetime.utcnow().isoformat()
        }

    def _publish(self, queue, message):
        """ Send message to the queue

        :param queue pika Queue instance
        :param message Dictionary with data
        :returns: True if success; False otherwise.
        """
        return queue.basic_publish(
            exchange='',
            routing_key='swift_search', body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2)
        )

    def _is_valid_method(self, req):
        """ Return True if the request method is allowed. False otherwise. """
        return req.method in ALLOWED_METHODS

    def _is_valid_object_url(self, req):
        """ Return True if it is a object url. False otherwise. """
        try:
            vrs, acc, con, obj = req.split_path(2, 4, rest_with_last=True)
        except ValueError:
            return False

        # con = None: account URI | obj = None: container URI
        if con is None or obj is None:
            return False

        return True

    def _has_optin_header(self, req):
        """
        Return True if container or account has the enabling header.
        False otherwise.
        """
        sysmeta_a = get_account_info(req.environ, self.app)['meta']
        enabled_a = sysmeta_a.get(META_SEARCH_ENABLED)

        sysmeta_c = get_container_info(req.environ, self.app)['meta']
        enabled_c = sysmeta_c.get(META_SEARCH_ENABLED)

        return utils.config_true_value(enabled_c or enabled_a)


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    defaults = {
        'methods': ALLOWED_METHODS,
        'indexed_headers': ALLOWED_HEADERS + [META_OBJECT_PREFIX],
        'enabling_header': 'x-(account|container)-meta-' + META_SEARCH_ENABLED
    }

    # Registers information to be retrieved on /info
    utils.register_swift_info('metadata_queuer', **defaults)

    def filter(app):
        return Queuer(app, conf)

    return filter
