#!/usr/bin/python
# Copyright (c) 2014 SwiftStack, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from setuptools import setup, find_packages

version = "__VERSION__"

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
    # Ubuntu packaging incorrectly detects this as a dependency on the
    # "python-swift" package, which SwiftStack doesn't use.  So commenting this
    # out so SwiftStack can still use ${python:Depends}
    # install_requires=["swift"],
    # test_suite='nose.collector',
    # tests_require=["nose"],
    scripts=[],
    entry_points={
        'paste.filter_factory': ['swift_search=swift_search:search_factory']})
