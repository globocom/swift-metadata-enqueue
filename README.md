# Swift Metadata Enqueue

[![Build Status](https://travis-ci.org/globocom/swift-metadata-queuer.svg?branch=master)](https://travis-ci.org/globocom/swift-metadata-queuer)

Middleware for OpenStack Swift that implements indexing for object metadata functionality.

``metadata_enqueue`` is a middleware which sends object metadata to a
queue for post-processing.

``metadata_enqueue`` uses the ``x-(account|container)-meta-enqueue``
metadata entry to verify if the object is suitable for enqueueing. Nothing
will be done if ``x-(account|container)-meta-enqueue`` is not set.

``metadata_enqueue`` exports all meta headers (x-object-meta-), content-type and
content-length headers.

The ``metadata_enqueue`` middleware should be added to the pipeline in your
``/etc/swift/proxy-server.conf`` file just after any auth middleware.
For example:

    [pipeline:main]
    pipeline = catch_errors cache tempauth metadata_enqueue proxy-server

    [filter:metadata_enqueue]
    use = egg:swift#metadata_enqueue
    queue_username
    queue_password
    queue_url
    queue_port
    queue_vhost
    queue_name

To enable the metadata indexing on an account level:

    swift post -m enqueue:True

To enable the metadata indexing on an container level:

    swift post container -m enqueue:True

Remove the metadata indexing:

    swift post -m enqueue:

To create an object with indexable metadata:
    swift upload <container> <file> -H "x-object-meta-example:content"

# Testing

    pip install -r requirements_test.txt
    make tests

# Team

Created by Storm @ Globo.com
