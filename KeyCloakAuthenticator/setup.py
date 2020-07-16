#!/usr/bin/env python
# coding: utf-8


#-----------------------------------------------------------------------------
# Minimal Python version sanity check (from IPython/Jupyterhub)
#-----------------------------------------------------------------------------
from __future__ import print_function

import os
import sys
import setuptools

name = 'keycloakauthenticator'

v = sys.version_info
if v[:2] < (3,3):
    error = "ERROR: Jupyter Hub requires Python version 3.3 or above."
    print(error, file=sys.stderr)
    sys.exit(1)


if os.name in ('nt', 'dos'):
    error = "ERROR: Windows is not supported"
    print(error, file=sys.stderr)

# At least we're on the python version we need, move on.

from distutils.core import setup

pjoin = os.path.join
here = os.path.abspath(os.path.dirname(__file__))

# Get the current package version.
version_ns = {}
with open(pjoin(here, name, '_version.py')) as f:
    exec(f.read(), {}, version_ns)

with open(pjoin(here, 'README.md'), 'r') as fh:
    long_description = fh.read()


setup_args = dict(
    name                = name,
    packages            = setuptools.find_packages(),
    version             = version_ns['__version__'],
    description         = "KeyCloakAuthenticator: Authenticate JupyterHub users with KeyCloak and OIDC",
    long_description    = long_description,
    long_description_content_type = "text/markdown",
    author              = "SWAN Admins",
    url                 = "https://github.com/swan-cern/jupyterhub-extensions",
    license             = "AGPL-3.0",
    platforms           = "Linux, Mac OS X",
    keywords            = ["JupyterHub", "Authenticator", "SWAN", "CERN"],
    classifiers         = [
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)

# setuptools requirements
if 'setuptools' in sys.modules:
    setup_args['install_requires'] = install_requires = ['oauthenticator','pyjwt']
    with open('requirements.txt') as f:
        for line in f.readlines():
            req = line.strip()
            if not req or req.startswith(('-e', '#')):
                continue
            install_requires.append(req)



if __name__ == "__main__":
    setuptools.setup(**setup_args)
