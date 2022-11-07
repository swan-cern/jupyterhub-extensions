# Author: Prasanth Kothuri, Diogo Castro 2020
# Copyright CERN

"""KeyCloakAuthenticator"""
from jupyterhub.utils import maybe_future
from oauthenticator.generic import GenericOAuthenticator
from oauthenticator.oauth2 import OAuthLoginHandler
from traitlets import Unicode, Bool, List, Any, TraitError, default, validate
import jwt, time, json
from jwt.algorithms import RSAAlgorithm
from urllib import request, parse
from urllib.error import HTTPError
from tornado.httpclient import HTTPRequest
from tornado import web
import asyncio
import time
from .metrics import metric_refresh_user, metric_exchange_token, metric_refresh_token, metric_authenticate, metric_pre_spawn_start

# Use a login handler wrapper to ensure the configuration was loaded before redirecting the user
# Otherwise, the login will end up in infinite loop of redirects
class OIDCOAuthLoginHandler(OAuthLoginHandler):
    def get(self):
        if not self.authenticator.configured:
            raise web.HTTPError(
                500, "Error configuring authenticator from IDP"
            )
        super().get()


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

    # Use Any instead of Callable for compatibility with Python < 3.7
    claim_roles_key = Any (
        config=True,
        help="""
            Callable that receives the spawner object and the user token json (as a dict) and returns the roles set.
            Useful for retrieving the info from a nested object.
            By default, retrieves the roles in resource_access.{client_id}.roles.
        """,
    )

    # Use list instead of set to allow easy configuration in Helm/Kbernetes yaml files
    # This gets converted to a set internally
    allowed_roles = List (
        Unicode(),
        default_value=[],
        config=True,
        help="List with the roles for which the login will be accepted. If an empty list is given (default) all users are allowed."
    )

    admin_role = Unicode(
        default_value='swan-admins',
        config=True,
        help="Users with this role login as jupyterhub administrators"
    )

    pre_spawn_hook = Any(
        allow_none=True,
        config=True,
        help="""
        Callable to execute before spawning a session. Usefull to inject extra variables, like the oauth tokens
        Example::
            def pre_spawn_hook(authenticator, spawner, auth_state):
                spawner.environment['ACCESS_TOKEN'] = auth_state['exchanged_tokens']['eos-service']
            c.KeyCloakAuthenticator.pre_spawn_hook = pre_spawn_hook
        """
    )

    check_signature = Bool(
        default_value=True,
        config=True,
        help="If False, it will disable JWT signature verification."
    )

    jwt_signing_algorithms = List (
        Unicode(),
        default_value=["HS256", "RS256"],
        config=True,
        help="The algorithms that can be used to check jwt signatures."
    )

    exchange_tokens = List (
        Unicode(),
        default_value=[],
        config=True,
        help="List of audiences to exchange our token to"
    )

    @validate('pre_spawn_hook')
    def _validate_pre_spawn_hook(self, proposal):
        value = proposal['value']
        if not callable(value):
            raise TraitError("pre_spawn_hook must be callable")
        return value

    @validate('claim_roles_key')
    def _validate_claim_roles_key(self, proposal):
        value = proposal['value']
        if not callable(value):
            raise TraitError("claim_roles_key must be callable")
        return value

    @default("claim_roles_key")
    def _default_claim_roles_key(self):
        def get_roles(env, token):
            return set(token.\
                get('resource_access', {'app': ''}).\
                get(env.client_id, {'roles_list': ''}).\
                get('roles', []))
        return get_roles

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Force auth state so that we can store the tokens in the user dict
        self.enable_auth_state = True
        self._allowed_roles = set(self.allowed_roles)

        if not self.oidc_issuer:
            raise Exception('No OIDC issuer url provided')

        # Try to configure the authenticator
        self.configured = False
        asyncio.ensure_future(self._get_oidc_configs())
        self.login_handler = OIDCOAuthLoginHandler

    async def _get_oidc_configs(self):

        self.log.info('Configuring OIDC from %s' % self.oidc_issuer)

        # Try to load the configs until it succeeds
        while True:
            try:
                req = HTTPRequest(f"{self.oidc_issuer}/.well-known/openid-configuration", headers=self._get_headers())
                data = await self.fetch(req, "fetching oidc config")

                if not set(['authorization_endpoint', 'token_endpoint', 'userinfo_endpoint']).issubset(data.keys()):
                    raise Exception('Unable to retrieve OIDC necessary values')

                self.authorize_url = data['authorization_endpoint']
                self.token_url = data['token_endpoint']
                self.userdata_url = data['userinfo_endpoint']
                
                end_session_url = data.get('end_session_endpoint')
                if self.enable_logout and end_session_url:
                    if self.logout_redirect_url:
                        end_session_url += '?redirect_uri=%s' % self.logout_redirect_url
                    # Update parent class OAuthenticator.logout_redirect_url
                    self.logout_redirect_url = end_session_url 

                if self.config.check_signature :
                    jwks_uri = data['jwks_uri']

                    req = HTTPRequest(jwks_uri, headers=self._get_headers())
                    jwk_data = await self.fetch(req, "fetching jwks")
                    self.public_key = RSAAlgorithm(RSAAlgorithm.SHA256).from_jwk(jwk_data['keys'][0])
                    self.log.info(f"aquired public key from {jwks_uri}")
                else:
                    self.public_key = None

                self.configured = True
                # All good, let's finish
                self.log.info('KeycloakAuthenticator fully configured')
                break
            except:
                self.log.error("Failure to retrieve the openid configuration, will try again in 1 min (auth calls will fail)")
                await asyncio.sleep(60)

    def _validate_roles(self, user_roles):
        return not self._allowed_roles or \
            (self._allowed_roles & user_roles)

    def _decode_token(self, token, options={}):
        if not self.config.check_signature:
            options.update({"verify_signature": False})
        #if not explicitly disabled, verify issuer
        options.setdefault("verify_iss", True)

        try:
            decoded_token = jwt.decode(token, self.public_key, options=options, audience=self.client_id,
                    issuer=self.oidc_issuer, algorithms=self.jwt_signing_algorithms)
            return decoded_token
        except jwt.exceptions.ExpiredSignatureError:
            self.log.info("Token expired")
            return None

    async def _exchange_tokens(self, token):

        tokens = dict()

        for new_token in self.exchange_tokens:

            # Record duration of request in metric with label:
            # keycloak_authenticator_request_duration_seconds{request="exchange_token_<service_name>"}
            with metric_exchange_token.labels("exchange_token_{}".format(new_token.replace("-","_"))).time():
                start = time.time()
                values = dict(
                    grant_type = 'urn:ietf:params:oauth:grant-type:token-exchange',
                    client_id = self.client_id,
                    client_secret = self.client_secret,
                    subject_token = token,
                    audience = new_token,
                    requested_token_type = 'urn:ietf:params:oauth:token-type:access_token'
                )
                data = parse.urlencode(values)

                req = HTTPRequest(
                    self.token_url,
                    method="POST",
                    headers=self._get_headers(),
                    body=data,
                )
                response = await self.fetch(req, "exchanging token")
                tokens[new_token] = response.get('access_token', None)
                self.log.info('Exchanged {} token in {} seconds'.format(new_token, time.time() - start))
        return tokens
    
    @metric_refresh_token.time()
    async def _refresh_token(self, refresh_token):
        start = time.time()
        values = dict(
            grant_type = 'refresh_token',
            client_id = self.client_id,
            client_secret = self.client_secret,
            refresh_token = refresh_token
        )
        data = parse.urlencode(values)

        req = HTTPRequest(
            self.token_url,
            method="POST",
            headers=self._get_headers(),
            body=data,
        )
        response = await self.fetch(req, "refreshing token")
        self.log.info('Refresh token request completed in {} seconds'.format(time.time() - start))
        return (response.get('access_token', None), response.get('refresh_token', None))
    
    @metric_authenticate.time()
    async def authenticate(self, handler, data=None):
        user = await super().authenticate(handler, data=data)
        if not user:
            return None

        try:
            decoded_token = self._decode_token(user['auth_state']['access_token'])
            user_roles = self.claim_roles_key(self, decoded_token)
        except:
            self.log.error("Unable to retrieve the roles, denying access.", exc_info=True)
            return None

        if not isinstance(user_roles, set):
            self.log.error("User roles is not a 'set', denying access")
            return None

        if not self._validate_roles(user_roles):
            self.log.info(f"User '{user['name']}' doesn't have apropriate role to be allowed")
            return None
        try:
            user['auth_state']['exchanged_tokens'] = await self._exchange_tokens(user['auth_state']['access_token'])
        except:
            self.log.error("Failed to exchange tokens during authenticate.", exc_info=True)
            return None

        user['admin'] = self.admin_role and (self.admin_role in user_roles)
        self.log.info("Authentication Successful for user: %s, roles: %s, admin: %s" % (user['name'], user_roles, user['admin']))

        return user

    @metric_pre_spawn_start.time()
    async def pre_spawn_start(self, user, spawner):
        if self.pre_spawn_hook:
            auth_state = await user.get_auth_state()
            await maybe_future(self.pre_spawn_hook(self, spawner, auth_state))

    @metric_refresh_user.time()
    async def refresh_user(self, user, handler=None):
        """
            Refresh user's oAuth tokens.
            This is called when user info is requested and
            has passed more than "auth_refresh_age" seconds.
        """
        start = time.time()

        # The config was not loaded yet, just fail
        if not self.configured:
            return False

        try:
            # Retrieve user authentication info, decode, and check if refresh is needed
            auth_state = await user.get_auth_state()

            # no verification of the refresh token signature as it is not needed, the auth server
            # verifies it
            decoded_refresh_token = self._decode_token(auth_state['refresh_token'], options={"verify_signature": False})

            # If we request the offline_access scope, our refresh token won't have expiration
            diff_refresh = (decoded_refresh_token['exp'] - time.time()) if 'exp' in decoded_refresh_token else 0

            if diff_refresh < 0:
                # Refresh token not valid, need to re-authenticate again
                self.log.info('Failed to refresh token as refresh token expired, took {}'.format(time.time() - start))
                return False

            else:
                # We need to refresh access token (which will also refresh the refresh token)
                access_token, refresh_token = await self._refresh_token(auth_state['refresh_token'])
                #check signature for new access token, if it fails we catch in the exception below
                self._decode_token(access_token)
                auth_state['access_token'] = access_token
                auth_state['refresh_token'] = refresh_token
                try:
                    auth_state['exchanged_tokens'] = await self._exchange_tokens(access_token)
                except:
                    self.log.error("Failed to exchange tokens during refresh, took %s seconds" % (time.time()-start), exc_info=True)

                    return False

                self.log.info('User %s oAuth tokens refreshed, took %s seconds' % (user.name, (time.time() - start)))
                return {
                    'auth_state': auth_state
                }

        except HTTPError as e:
            self.log.error("Failure calling the renew endpoint: %s (code: %s)" % (e.read(), e.code))

        except:
            self.log.error("Failed to refresh the oAuth tokens, took %s seconds" % (time.time()-start), exc_info=True)

        return False
