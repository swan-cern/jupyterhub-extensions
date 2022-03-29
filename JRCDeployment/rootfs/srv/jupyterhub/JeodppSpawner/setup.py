#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='jeodpppawner',
      version='1.1',
      description='Spawner for SWAN at JEODPP',
      include_package_data=True,
      packages=find_packages(),
      zip_safe=False,
      install_requires=[
        'setuptools',
        'jupyterhub',
        'psutil',
        'jupyterhub-kubespawner',
        'kubernetes' #kubespawnwer failing with version 10
      ],
  )

setup(name='JeoClasses',
      version='1.0',
      packages=['JeoClasses'],
  )
