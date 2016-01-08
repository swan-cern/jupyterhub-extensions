# Author: Danilo Piparo, Enric Tejedor 2015
# Copyright CERN

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
        username = data['username']
        self.log.debug("Letting user %s pass through.", username)
        return username
