import os

from ._version import __version__  # noqa: F401


def get_templates():
    path = os.path.abspath(__file__)
    return os.path.join(os.path.dirname(path), 'templates')
