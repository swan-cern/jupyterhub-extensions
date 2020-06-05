# Author: Prasanth Kothuri 2020
# Copyright CERN

"""KeyCloakAuthenticator"""

from jupyterhub.handlers import LogoutHandler
from oauthenticator.generic import GenericOAuthenticator
from tornado import gen, web
from traitlets import Unicode, Set
import jwt, os

class KeyCloakLogoutHandler(LogoutHandler):
    """Log a user out by clearing both their JupyterHub login cookie and SSO cookie."""

    async def get(self):
        if self.authenticator.keycloak_logout_url:
            await self.default_handle_logout()
            await self.handle_logout()
            self.redirect(self.authenticator.keycloak_logout_url)
        else:
            await super().get()

class KeyCloakAuthenticator(GenericOAuthenticator):
    """
    KeyCloakAuthenticator based on upstream jupyterhub/oauthenticator
    """

    keycloak_logout_url = Unicode(
        default_value='',
        config=True,
        help="""URL to invalidate the SSO cookie."""
    )

    accepted_roles = Set (
        Unicode(),
        default_value=set(),
        config=True,
        help="""The role for which the login will be accepted. Default is all roles."""
    )

    admin_role = Unicode(
        default_value='swan-admins',
        config=True,
        help="""Users with this role login as jupyterhub administrators"""
    )

    def validate_roles(self, user_roles):
        return bool(not self.accepted_roles or (self.accepted_roles & user_roles))

    def decode_token(self, token):
        return jwt.decode(token, verify=False, algorithms='RS256')

    def get_roles_for_token(self, token):
        decoded_token = self.decode_token(token)
        return set(
            decoded_token.\
               get('resource_access', {'app': ''}).\
               get(os.environ.get('OAUTH_CLIENT_ID'), {'roles_list': ''}).\
               get('roles', 'no_roles')
        )

    async def authenticate(self, handler, data=None):
        user = await super().authenticate(handler, data=None)
        if user:
            self.user_roles = self.get_roles_for_token(user['auth_state']['access_token'])
            if not self.validate_roles(self.user_roles):
                return None
            user['admin'] = bool(self.admin_role and (self.admin_role in self.user_roles))
            self.log.info("Authentication Successful for user: %s, roles: %s, admin: %s" % (user['name'],self.user_roles,user['admin']))
            return user
        else:
            return None

    async def pre_spawn_start(self, user, spawner):
        if hasattr(self, 'user_roles'):
            spawner.user_roles = self.user_roles

    def get_handlers(self, app):
        return super().get_handlers(app) + [(r'/logout', KeyCloakLogoutHandler)]
