# Author: Prasanth Kothuri, Diogo Castro 2020
# Copyright CERN

"""KeyCloakAuthenticator"""

import asyncio
import json
import time
from urllib import parse

import jwt
from jupyterhub.utils import maybe_future
from jwt.algorithms import RSAAlgorithm
from oauthenticator.generic import GenericOAuthenticator
from oauthenticator.oauth2 import OAuthLoginHandler
from tornado import web
from tornado.httpclient import HTTPClientError, HTTPRequest
from tornado.httputil import url_concat
from traitlets import Any, Bool, List, TraitError, Unicode, default, validate

from .metrics import (
    metric_authenticate,
    metric_exchange_tornado_queue_time,
    metric_exchange_tornado_request_time,
    metric_pre_spawn_start,
    metric_refresh_token,
    metric_refresh_user,
)


# Use a login handler wrapper to ensure the configuration was loaded before redirecting the user
# Otherwise, the login will end up in infinite loop of redirects
class OIDCOAuthLoginHandler(OAuthLoginHandler):
    def get(self):
        if not self.authenticator.configured:
            raise web.HTTPError(500, "Error configuring authenticator from IDP")
        super().get()


class KeyCloakAuthenticator(GenericOAuthenticator):
    """KeyCloakAuthenticator based on upstream jupyterhub/oauthenticator"""

    oidc_issuer = Unicode(
        default_value="",
        config=True,
        help="OIDC issuer URL for automatic discovery of configuration",
    )

    enable_logout = Bool(
        default_value=True,
        config=True,
        help="If True, it will logout in SSO.",
    )

    # Use Any instead of Callable for compatibility with Python < 3.7
    claim_roles_key = Any(
        config=True,
        help="""
            Callable that receives the spawner object and the user token json (as a dict) and returns the roles set.
            Useful for retrieving the info from a nested object.
            By default, retrieves the roles in resource_access.{client_id}.roles.
        """,
    )

    pre_spawn_hook = Any(
        allow_none=True,
        config=True,
        help="""
        Callable to execute before spawning a session. Useful to inject extra variables, like the oauth tokens
        Example::
            def pre_spawn_hook(authenticator, spawner, auth_state):
                spawner.environment['ACCESS_TOKEN'] = auth_state['exchanged_tokens']['eos-service']
            c.KeyCloakAuthenticator.pre_spawn_hook = pre_spawn_hook
        """,
    )

    check_signature = Bool(
        default_value=True,
        config=True,
        help="If False, it will disable JWT signature verification.",
    )

    verify_aud = Bool(
        default_value=True,
        config=True,
        help="If True, it will verify the audience in the JWT token.",
    )

    jwt_signing_algorithms = List(
        Unicode(),
        default_value=["HS256", "RS256"],
        config=True,
        help="The algorithms that can be used to check jwt signatures.",
    )

    exchange_tokens = List(
        Unicode(),
        default_value=[],
        config=True,
        help="List of audiences to exchange our token to",
    )

    @validate("pre_spawn_hook")
    def _validate_pre_spawn_hook(self, proposal):
        value = proposal["value"]
        if not callable(value):
            raise TraitError("pre_spawn_hook must be callable")
        return value

    @validate("claim_roles_key")
    def _validate_claim_roles_key(self, proposal):
        value = proposal["value"]
        if not callable(value):
            raise TraitError("claim_roles_key must be callable")
        return value

    @default("claim_roles_key")
    def _default_claim_roles_key(self):
        def get_roles(env, token):
            return set(
                token.get("resource_access", {"app": ""}).get(env.client_id, {"roles_list": ""}).get("roles", [])
            )

        return get_roles

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Force auth state so that we can store the tokens in the user dict
        self.enable_auth_state = True

        # Read JupyterHub groups from auth_state["roles"]
        if self.manage_groups:
            self.auth_state_groups_key = "roles"

        if not self.oidc_issuer:
            raise Exception("No OIDC issuer url provided")

        # Try to configure the authenticator
        self.configured = False
        asyncio.ensure_future(self._get_oidc_configs())
        self.login_handler = OIDCOAuthLoginHandler

    async def _get_oidc_configs_helper(self):
        data = await self.httpfetch(
            f"{self.oidc_issuer}/.well-known/openid-configuration", label="fetching oidc config"
        )

        if not set(["authorization_endpoint", "token_endpoint", "userinfo_endpoint"]).issubset(data.keys()):
            raise Exception("Unable to retrieve OIDC necessary values")

        self.authorize_url = data["authorization_endpoint"]
        self.token_url = data["token_endpoint"]
        self.userdata_url = data["userinfo_endpoint"]

        end_session_url = data.get("end_session_endpoint")
        if self.enable_logout and end_session_url:
            if self.logout_redirect_url:
                end_session_url = url_concat(
                    end_session_url,
                    {"post_logout_redirect_uri": self.logout_redirect_url, "client_id": self.client_id},
                )
            # Update parent class OAuthenticator.logout_redirect_url
            self.logout_redirect_url = end_session_url

        if self.check_signature:
            jwks_uri = data["jwks_uri"]

            self.log.info("Fetching JWKs data")
            jwk_data = await self.httpfetch(jwks_uri, label="fetching jwks")
            # Find signature key out of keys provided at certs endpoint
            sign_keys = [key for key in jwk_data["keys"] if key.get("use") == "sig"]
            if not sign_keys:
                # If no signature key is found, fallback to first key in the list
                sign_keys = jwk_data["keys"]
            self.public_key = RSAAlgorithm(RSAAlgorithm.SHA256).from_jwk(sign_keys[0])
            self.log.info(f"acquired public key from {jwks_uri}")
        else:
            self.log.info("JWT signature verification is disabled")
            self.public_key = None

        self.configured = True
        # All good, let's finish
        self.log.info("KeycloakAuthenticator fully configured")

    async def _get_oidc_configs(self):
        self.log.info("Configuring OIDC from %s" % self.oidc_issuer)

        # Try to load the configs until it succeeds
        while True:
            try:
                await self._get_oidc_configs_helper()
                break
            except Exception:
                self.log.error(
                    "Failure to retrieve the openid configuration, will try again in 1 min (auth calls will fail)",
                    exc_info=True,
                )
                await asyncio.sleep(60)

    def _decode_token(self, token, options=None):
        if options is None:
            options = {}
        if not self.check_signature:
            options.update({"verify_signature": False})
        if not self.verify_aud:
            options.update({"verify_aud": False})
        # if not explicitly disabled, verify issuer
        options.setdefault("verify_iss", True)
        # Skip verifying iat which is
        # - not very useful in the first place
        # - small clock drift can lead to rejected tokens (jwt.exceptions.ImmatureSignatureError)
        # See related issue in PyJWT: https://github.com/jpadilla/pyjwt/issues/939
        options.setdefault("verify_iat", False)

        try:
            decoded_token = jwt.decode(
                token,
                self.public_key,
                options=options,
                audience=self.client_id,
                issuer=self.oidc_issuer,
                algorithms=self.jwt_signing_algorithms,
            )
            return decoded_token
        except jwt.exceptions.ExpiredSignatureError:
            self.log.info("Token expired")
            return None

    async def _exchange_tokens(self, token):
        # Construct requests for all token exchanges
        exchange_requests = []
        for service_name in self.exchange_tokens:
            values = dict(
                grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
                client_id=self.client_id,
                client_secret=self.client_secret,
                subject_token=token,
                audience=service_name,
                requested_token_type="urn:ietf:params:oauth:token-type:access_token",
                subject_token_type="urn:ietf:params:oauth:token-type:access_token",
            )
            data = parse.urlencode(values)

            req = HTTPRequest(
                self.token_url,
                method="POST",
                body=data,
            )

            exchange_requests.append(req)

        # Schedule all exchange requests at once
        start = time.time()
        responses = await asyncio.gather(
            *(self.fetch(req, "exchanging token", parse_json=False) for req in exchange_requests)
        )
        total_t = time.time() - start
        self.log.info(f"Token exchanges finished, total time: {total_t} s")

        # Inspect the responses obtained for each service
        access_tokens = {}
        for response, service_name in zip(responses, self.exchange_tokens, strict=True):
            # Get the access token obtained for this service
            access_token = None
            if response.body:
                body = json.loads(response.body.decode("utf8", "replace"))
                access_token = body.get("access_token", None)
            if access_token is None:
                self.log.error(f"Could not obtain access token for {service_name}")
                continue

            access_tokens[service_name] = access_token

            # Produce logs and metrics for this token exchange
            queue_t = response.time_info["queue"] if "queue" in response.time_info else -1
            request_t = response.request_time
            self.log.info(f"Exchanged {service_name} token, queue time: {queue_t} s, request time: {request_t} s")
            metric_exchange_tornado_queue_time.labels(
                "exchange_token_{}".format(service_name.replace("-", "_"))
            ).observe(queue_t)
            metric_exchange_tornado_request_time.labels(
                "exchange_token_{}".format(service_name.replace("-", "_")), response.code
            ).observe(request_t)

        return access_tokens

    def modify_auth_state_hook(self, authenticator, auth_state):
        try:
            decoded_token = self._decode_token(auth_state["access_token"])
            if decoded_token is None:
                # The access token expired (e.g. the userinfo endpoint still accepted it due to clock skew).
                # Raise a 4xx client error so that upstream refresh_user treats it as a rejected token
                # and falls back to the refresh token, instead of requiring a new login.
                raise HTTPClientError(401, "Access token expired")
            user_roles = self.claim_roles_key(self, decoded_token)
            auth_state["roles"] = list(user_roles)
        except HTTPClientError:
            raise
        except Exception:
            self.log.exception("Unable to retrieve the roles, denying access.")
            raise

        return auth_state

    async def authenticate(self, handler, data=None):
        with metric_authenticate.time():
            user = await super().authenticate(handler, data=data)
            if not user:
                return None

            try:
                user["auth_state"]["exchanged_tokens"] = await self._exchange_tokens(user["auth_state"]["access_token"])
            except Exception:
                self.log.error("Failed to exchange tokens during authenticate.", exc_info=True)
                return None

            self.log.info(
                f"Authentication Successful for user: {user['name']}, roles: {user['auth_state']['roles']}, admin: {user['admin']}"
            )

            return user

    async def pre_spawn_start(self, user, spawner):
        with metric_pre_spawn_start.time():
            if self.pre_spawn_hook:
                auth_state = await user.get_auth_state()
                await maybe_future(self.pre_spawn_hook(self, spawner, auth_state))

    async def refresh_user(self, user, handler=None):
        """
        Refresh user's oAuth tokens.
        This is called when user info is requested and
        has passed more than "auth_refresh_age" seconds.
        """
        with metric_refresh_user.time():
            start = time.time()

            # The config was not loaded yet, just fail
            if not self.configured:
                return False

            try:
                with metric_refresh_token.time():
                    auth_model = await super().refresh_user(user, handler=handler)

                if not auth_model:
                    self.log.info(f"Failed to refresh user {user.name} tokens, took {time.time() - start}")
                    return False

                # Upstream returns True when the auth info is up-to-date and needs no changes
                if auth_model is True:
                    return True

                # Refresh exchanged tokens
                try:
                    auth_state = auth_model["auth_state"]
                    access_token = auth_state["access_token"]
                    auth_state["exchanged_tokens"] = await self._exchange_tokens(access_token)
                except Exception:
                    self.log.exception(f"Failed to exchange tokens during refresh, took {time.time() - start} seconds")
                    return False

                self.log.info(f"User {user.name} oAuth tokens refreshed, took {time.time() - start} seconds")
                return auth_model

            except Exception:
                self.log.exception(f"Failed to refresh the oAuth tokens, took {time.time() - start} seconds")

            return False
