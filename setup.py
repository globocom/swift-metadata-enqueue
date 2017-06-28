from os.path import dirname, abspath, join

from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup, find_packages

VERSION = '0.0.7'


def get_path(*p):
    """ Project path """
    return join(dirname(abspath(__file__)), *p)


REQS_TXT = parse_requirements(get_path('requirements.txt'),
                              session=PipSession())
REQS = [str(ir.req) for ir in REQS_TXT]

setup(
    name="swift_metadata_enqueue",
    version=VERSION,
    description='Swift Enqueue Middleware',
    license='Apache License (2.0)',
    author='Storm Team Globo.com',
    author_email='storm@corp.globo.com',
    url='https://git@github.com:globocom/swift_metadata_enqueue.git',
    packages=find_packages(),
    install_requires=REQS,
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Environment :: No Input/Output (Daemon)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
    ],
    scripts=[],
    entry_points={
        'paste.filter_factory': [
            ('metadata_enqueue=metadata_enqueue.middleware:'
             'filter_factory')
        ]
    }
)
