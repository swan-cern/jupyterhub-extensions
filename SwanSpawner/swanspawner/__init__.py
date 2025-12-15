import os

from ._version import __version__ 
from .swandockerspawner import *


# KubeSpawner must run in a k8s environment, otherwise it fails to import
# so only import it when not in dev mode.
if os.environ.get('SWANHUB_ENV') != 'dev':
    from .swankubespawner import *
