#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='swanspawner',
      version='1.1',
      description='Spawner for SWAN',
      include_package_data=True,
      packages=find_packages(),
      zip_safe=False,
      install_requires=[
        'setuptools',
        'jupyterhub',
        'psutil',
        'dockerspawner==0.11.0',
        'jupyterhub-kubespawner==0.10.1'
      ],
  )