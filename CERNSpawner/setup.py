#!/usr/bin/env python

from setuptools import setup
import os
import sys

if os.name in ('nt', 'dos'):
    error = "ERROR: Windows is not supported"
    print(error, file=sys.stderr)

# At least we're on the python version we need, move on.

from distutils.core import setup

pjoin = os.path.join
here = os.path.abspath(os.path.dirname(__file__))

# Get the current package version.
version_ns = {}
with open(pjoin(here, 'version.py')) as f:
    exec(f.read(), {}, version_ns)


setup(name='cernspawner',
      packages=['cernspawner'],
      version=version_ns['__version__'],
      description='Spawner for SWAN',
      include_package_data=True,
      zip_safe=False,
      author="Danilo Piparo",
      author_email="danilo.piparo@cern.ch",
      url="root.cern.ch",
      license="BSD",
      platforms="Linux, Mac OS X",
      keywords=['Interactive', 'Interpreter', 'Shell', 'Web'],
      classifiers=[
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'Intended Audience :: Science/Research',
          'License :: OSI Approved :: BSD License',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
      ],
      install_requires=[
          'setuptools',
          'jupyterhub',
          'dockerspawner==0.10.*',
      ],
      )
