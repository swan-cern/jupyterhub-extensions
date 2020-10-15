from ._version import __version__ 
import os


def get_templates():
    path = os.path.abspath(__file__)
    return os.path.join(os.path.dirname(path), 'templates')
