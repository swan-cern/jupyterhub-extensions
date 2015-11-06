"""Kerberos authenticator"""

import os
import sys

from jupyterhub.auth import LocalAuthenticator
from traitlets import Unicode
from tornado import gen, web

class KerberosAuthenticator(LocalAuthenticator):
    """Kerberos authenticate a user"""
    service = Unicode('login', config=True,
        help="""The Kerberos authentication."""
    )

    @gen.coroutine
    def authenticate(self, handler, data):
        """Authenticate a user with Kerberos."""
        username = data['username']
        retCode = os.system('echo %s > kinit %s' %(data['password'], username))
        if 0 != retCode:
            print("WARNING: Kinit failed for user %s!" %username, file=sys.stderr)
        return username
