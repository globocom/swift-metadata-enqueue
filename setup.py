from os.path import dirname, abspath, join

from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup, find_packages

version = '0.0.4'


def get_path(*p):
    return join(dirname(abspath(__file__)), *p)


install_reqs = parse_requirements(get_path('requirements.txt'),
                                  session=PipSession())
reqs = [str(ir.req) for ir in install_reqs]

setup(
    name="metadata_queuer",
    version=version,
    description='Swift Search Middleware',
    license='Apache License (2.0)',
    author='Storm Team Globo.com',
    author_email='storm@corp.globo.com',
    url='https://git@github.com:globocom/swift_metadata_queuer.git',
    packages=find_packages(),
    install_requires=reqs,
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
            ('metadata_queuer=metadata_queuer.middleware:'
             'filter_factory')
        ]
    }
)
