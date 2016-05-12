# Author: Danilo Piparo 2016
# Copyright CERN

"""Check the project url"""

import requests
import string
from urllib import parse

from tornado import web

def raise_error(emsg):
    raise web.HTTPError(500, reason = emsg)

def check_url(url):

    url = parse.unquote(url)

    # Limit the sources
    is_good_server = url.startswith('https://gitlab.cern.ch') or \
                     url.startswith('https://github.com') or \
                     url.startswith('https://raw.githubusercontent.com')
    if not is_good_server:
        raise_error('The URL of the project is not a github or CERN gitlab URL')

    # Check if contains only good characters
    allowed = string.ascii_lowercase +\
              string.ascii_uppercase +\
              '/.'
    has_allowd_chars = set(url[len('https:'):]) <= set(allowed)
    if not has_allowd_chars:
        raise_error('The URL of the project is invalid.')

    # Limit the kind of project
    is_good_ext = url.endswith('.git') or url.endswith('.ipynb')
    if not is_good_ext:
        raise_error('The project must be a repository or a notebook.')

    # Avoid code injection: paranoia mode
    forbidden_seqs = ['&&', '|', ';', ' ', '..', '@']
    is_valid_url = any(i in url for i in forbidden_seqs)
    if not forbidden_seqs:
        raise_error('The URL of the project is invalid.')

    # Check it exists
    request = requests.get(url)
    sc = request.status_code
    if sc != 200:
        raise_error('The URL of the project does not exist or is not reachable (status code is %s)' %sc)

    return True
