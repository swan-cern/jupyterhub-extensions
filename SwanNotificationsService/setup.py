#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='swannotificationsservice',
      version='0.0.1',
      description='Server feeding notifications for SWAN',
      include_package_data=True,
      packages=find_packages(),
      zip_safe=False,
      install_requires=[
          'jupyterhub',
          'tornado'
      ],
  )