# Author: Prasanth Kothuri, Diogo Castro 2020
# Copyright CERN

"""KeyCloakAuthenticator"""

from jupyterhub.handlers import LogoutHandler
from jupyterhub.utils import maybe_future
from oauthenticator.generic import GenericOAuthenticator
from tornado import gen, web
from traitlets import Unicode, Set, Bool, Any
import jwt, os, pwd, time, json
from urllib import request, parse
from urllib.error import HTTPError

class KeyCloakLogoutHandler(LogoutHandler):
    """Log a user out by clearing both their JupyterHub login cookie and SSO cookie."""

    async def get(self):
        if self.authenticator.enable_logout:
            await self.default_handle_logout()
            await self.handle_logout()

            redirect_url = self.authenticator.end_session_url
            if self.authenticator.logout_redirect_uri:
                redirect_url += '?redirect_uri=%s' % self.authenticator.logout_redirect_uri

            self.redirect(redirect_url)
        else:
            await super().get()

class KeyCloakAuthenticator(GenericOAuthenticator):
    """KeyCloakAuthenticator based on upstream jupyterhub/oauthenticator"""

    oidc_issuer = Unicode(
        default_value='',
        config=True,
        help="OIDC issuer URL for automatic discovery of configuration"
    )

    enable_logout = Bool(
        default_value=True,
        config=True,
        help="If True, it will logout in SSO."
    )

    logout_redirect_uri = Unicode(
        default_value='',
        config=True,
        help="URL to invalidate the SSO cookie."
    )

    accepted_roles = Set (
        Unicode(),
        default_value=set(),
        config=True,
        help="The role for which the login will be accepted. Default is all roles."
    )

    admin_role = Unicode(
        default_value='swan-admins',
        config=True,
        help="Users with this role login as jupyterhub administrators"
    )
        
    get_uid_hook = Any(
        allow_none=False,
        help="""
        Mandatory function to retrieve the user uid from its auth state and pass it to spawner.
        Example::
            def get_uid_hook(spawner, auth_state):
                spawner.user_uid = auth_state['oauth_user']['cern_uid']
            c.KeyCloakAuthenticator.get_uid_hook = get_uid_hook
        """
    ).tag(config=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.oidc_issuer:
            raise Exception('No OIDC issuer url provided')

        self.log.info('Configuring OIDC from %s' % self.oidc_issuer)

        try:
            with request.urlopen('%s/.well-known/openid-configuration' % self.oidc_issuer) as response:
                data = json.loads(response.read())
                
                if not set(['authorization_endpoint', 'token_endpoint', 'userinfo_endpoint', 'end_session_endpoint']).issubset(data.keys()):
                    raise Exception('Unable to retrieve OIDC necessary values')

                self.authorize_url = data['authorization_endpoint']
                self.token_url = data['token_endpoint']
                self.userdata_url = data['userinfo_endpoint']
                self.end_session_url = data['end_session_endpoint']
        
        except HTTPError:
            self.log.error("Failure to retrieve the openid configuration")
            raise


    def _validate_roles(self, user_roles):
        return not self.accepted_roles or (self.accepted_roles & user_roles)

    def _decode_token(self, token):
        return jwt.decode(token, verify=False, algorithms='RS256')

    def _get_roles_for_token(self, token):
        decoded_token = self._decode_token(token)
        return set(
            decoded_token.\
               get('resource_access', {'app': ''}).\
               get(self.client_id, {'roles_list': ''}).\
               get('roles', 'no_roles')
        )

    async def authenticate(self, handler, data=None):
        user = await super().authenticate(handler, data=data)
        if user:
            user_roles = self._get_roles_for_token(user['auth_state']['access_token'])
            if not self._validate_roles(user_roles):
                return None
            user['admin'] = self.admin_role and (self.admin_role in user_roles)
            self.log.info("Authentication Successful for user: %s, roles: %s, admin: %s" % (user['name'],user_roles,user['admin']))
            return user
        else:
            return None

    async def pre_spawn_start(self, user, spawner):
        auth_state = await user.get_auth_state()
        spawner.access_token = auth_state['access_token']
        spawner.user_roles = self._get_roles_for_token(auth_state['access_token'])
        spawner.inspection_url = self.userdata_url
        # If function raises Exception, let the this fail
        await maybe_future(self.get_uid_hook(spawner, auth_state))


    async def refresh_user(self, user, handler=None):
        """
            Refresh user's oAuth tokens.
            This is called when user info is requested and
            has passed more than "auth_refresh_age" seconds.
        """

        try:
            # Retrieve user authentication info, decode, and check if refresh is needed
            auth_state = await user.get_auth_state()
            decoded_access_token = self._decode_token(auth_state['access_token'])
            decoded_refresh_token = self._decode_token(auth_state['refresh_token'])

            diff_access = decoded_access_token['exp'] - time.time()
            diff_refresh = decoded_refresh_token['exp'] - time.time()

            if diff_access > self.auth_refresh_age:
                # Access token is still valid and will stay until next refresh
                return True

            elif diff_refresh < 0:
                # Refresh token not valid, need to re-authenticate again
                return False

            else:
                # We need to refresh access token (which will also refresh the refresh token)
                values = dict(
                    grant_type = 'refresh_token',
                    client_id = self.client_id,
                    client_secret = self.client_secret,
                    refresh_token = auth_state['refresh_token']
                )
                data = parse.urlencode(values).encode('ascii')

                req = request.Request(self.token_url, data)
                with request.urlopen(req) as response:
                    data = json.loads(response.read())

                    auth_state['access_token'] = data.get('access_token', None)
                    auth_state['refresh_token'] = data.get('refresh_token', None)
                    refresh_user_return = {
                        'auth_state': auth_state
                    }

                    self.log.info('User %s oAuth tokens refreshed' % user.name)
                    return refresh_user_return

        except HTTPError as e:
            self.log.error("Failure calling the renew endpoint: %s (code: %s)" % (e.read(), e.code))

        except:
            self.log.error("Failed to refresh the oAuth token", exc_info=True)

        return False

    def get_handlers(self, app):
        return super().get_handlers(app) + [(r'/logout', KeyCloakLogoutHandler)]
