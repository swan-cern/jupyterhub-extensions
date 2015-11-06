"""Pass through authenticator"""

from jupyterhub.auth import LocalAuthenticator
from traitlets import Unicode
from tornado import gen, web


class PassThroughAuthenticator(LocalAuthenticator):
    """Authenticate a user without checkoing the password"""
    service = Unicode('login', config=True,
        help="""The authentication without password checking."""
    )

    @gen.coroutine
    def authenticate(self, handler, data):
        """Return the username and skip authentication."""
        print (data['username'])
        return data['username']
