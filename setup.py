from os.path import dirname, abspath, join

from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup, find_packages

version = "2.3-thread-simple-rabbit"


def get_path(*p):
    return join(dirname(abspath(__file__)), *p)


install_reqs = parse_requirements(get_path('requirements.txt'),
                                  session=PipSession())
reqs = [str(ir.req) for ir in install_reqs]

setup(
    name="swift_search",
    version=version,
    description='Swift Search Middleware',
    license='Apache License (2.0)',
    author='Storm Team Globo.com',
    author_email='storm@corp.globo.com',
    url='https://git@github.com:globocom/swift_search.git',
    packages=find_packages(),
    install_requires=reqs,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Environment :: No Input/Output (Daemon)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
    scripts=[],
    entry_points={
        'paste.search_factory': [
            'swift_search=swift_search.middleware:search_factory'
        ]})
