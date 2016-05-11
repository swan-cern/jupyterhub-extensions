# Author: Danilo Piparo 2016
# Copyright CERN

"""Check the project url"""

import requests
import http
import re

def check_url(url):

    # Limit the sources
    is_good_server = url.beginswith('https://gitlab.cern.ch') or url.beginswith('https://github.com')
    if not is_good_server:
        raise ValueError('Project URL is not a github or CERN gitlab URL')

    # Limit the kind of project
    is_good_ext = url.endswith('.git') or url.endswith('.ipynb')
    if not is_good_server:
        raise ValueError('Project URL is not a git repository or a notebook')

    # Avoid code injection
    forbidden_seqs = ['&&', '|', ';', ' ']
    is_valid_url = any(i in url for i in forbidden_seqs)
    if not is_good_server:
        raise ValueError('Project URL is invalid')

    # Check it exists
    request = requests.get(url)

    if request.status_code != 200:
        raise ValueError('Project URL does not exist')

    return True
