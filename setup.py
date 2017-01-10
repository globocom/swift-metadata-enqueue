from setuptools import setup, find_packages

version = "5.0"

setup(
    name="swift_search",
    version=version,
    description='Swift Search Middleware',
    license='Apache License (2.0)',
    author='Storm Team Globo.com',
    author_email='storm@corp.globo.com',
    url='https://git@github.com:globocom/swift_search.git',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.7',
        'Environment :: No Input/Output (Daemon)'],
    scripts=[],
    entry_points={
        'paste.search_factory': [
            'swift_search=swift_search.middleware:search_factory'
        ]})
