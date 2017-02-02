Middleware for OpenStack Swift that implements indexing for object metadata functionality.

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