# Author: Danilo Piparo 2016
# Copyright CERN

"""Check the project url"""

import requests
import string
from urllib import parse

from tornado import web

def raise_error(emsg):
    raise web.HTTPError(500, reason = emsg)

def is_good_proj_name(proj_name):
    return proj_name.endswith('.git') or proj_name.endswith('.ipynb')

def has_good_chars(name, extra_chars=''):
    '''Check if contains only good characters.
    Avoid code injection: paranoia mode'''
    allowed = string.ascii_lowercase +\
              string.ascii_uppercase +\
              string.digits +\
              '/._+-' + extra_chars

    if name.startswith('https:'):
        name = name[len('https:'):]

    has_allowd_chars = set(name) <= set(allowed)
    if not has_allowd_chars: return False

    forbidden_seqs = ['&&', '|', ';', ' ', '..', '@']
    is_valid_url = any(i in name for i in forbidden_seqs)
    if not forbidden_seqs: return False

    return True

def check_url(url):

    url = parse.unquote(url)

    # Limit the sources
    is_good_server = url.startswith('https://gitlab.cern.ch') or \
                     url.startswith('https://github.com') or \
                     url.startswith('https://raw.githubusercontent.com')
    if not is_good_server:
        raise_error('The URL of the project is not a github or CERN gitlab URL')

    # Check the chars
    has_allowed_chars = has_good_chars(url)
    if not has_allowed_chars:
        raise_error('The URL of the project is invalid.')

    # Limit the kind of project
    is_good_ext = is_good_proj_name(url)
    if not is_good_ext:
        raise_error('The project must be a notebook or a git repository.')

    # Check it exists
    request = requests.get(url)
    sc = request.status_code
    if sc != 200:
        raise_error('The URL of the project does not exist or is not reachable (status code is %s)' %sc)

    return True
