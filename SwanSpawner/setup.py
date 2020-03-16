#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='swanspawner',
      version='1.2',
      description='Spawner for SWAN',
      include_package_data=True,
      packages=find_packages(),
      package_data={'swanspawner': ['templates/*']},
      zip_safe=False,
      install_requires=[
        'setuptools',
        'jupyterhub',
        'psutil',
        'dockerspawner==0.11.1',
        'jupyterhub-kubespawner==0.11.1'
      ],
  )