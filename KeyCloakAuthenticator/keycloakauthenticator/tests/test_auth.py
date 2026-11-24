import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote_plus

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from oauthenticator.generic import GenericOAuthenticator
from oauthenticator.oauth2 import OAuthLoginHandler
from tornado import web
from tornado.httpclient import HTTPClientError
from traitlets import TraitError

from ..auth import KeyCloakAuthenticator, OIDCOAuthLoginHandler


def _generate_mock_public_private_key_pair():
    """Create a mock public/private key pair for faking JWTs from the server"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return (public_key, private_key)


def _get_mock_token(private_key, token_id, expired=False):
    """Create a fake JWT issued by the server, that is valid if expired=False"""
    expiry = 300 if expired else 9999999999
    return jwt.encode(
        payload={
            "sub": "dummy-subject",
            "iss": "dummy-oidc-url",
            "aud": "dummy-client-id",
            "iat": 0,  # Issued a long time ago: 1/1/1970
            "exp": expiry,
            "permissions": ["read", "write"],
            "jti": token_id,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": "dummy-key-id"},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def unconfigured_authenticator(monkeypatch):
    monkeypatch.setattr(asyncio, "ensure_future", lambda coro: coro.close())
    auth = KeyCloakAuthenticator(oidc_issuer="http://fake-issuer", manage_groups=True)
    auth.check_signature = False  # disabled by default; check_signature tests enable it explicitly
    return auth


@pytest.fixture
def key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.public_key(), private_key


@pytest.fixture
def authenticator(unconfigured_authenticator):
    unconfigured_authenticator.token_url = "http://fake/token"
    unconfigured_authenticator.client_id = "dummy-client"
    unconfigured_authenticator.client_secret = "dummy-secret"
    unconfigured_authenticator.configured = True
    return unconfigured_authenticator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OIDC_DISCOVERY_DOC = {
    "authorization_endpoint": "http://fake/auth",
    "token_endpoint": "http://fake/token",
    "userinfo_endpoint": "http://fake/userinfo",
}


def _make_jwks(public_key, *, use_sig=True):
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    if use_sig:
        jwk["use"] = "sig"
    return {"keys": [jwk]}


class MockFetchResponse:
    def __init__(self, body=None, code=200):
        self.body = body
        self.code = code
        self.request_time = 0.0
        self.time_info = {"queue": 0.0}


class TestOIDCOAuthLoginHandler:
    class TestGet:
        def _make_handler(self, monkeypatch, configured):
            handler = OIDCOAuthLoginHandler.__new__(OIDCOAuthLoginHandler)
            monkeypatch.setattr(
                OIDCOAuthLoginHandler, "authenticator", property(lambda _: MagicMock(configured=configured))
            )
            return handler

        def test_raises_when_not_configured(self, monkeypatch):
            handler = self._make_handler(monkeypatch, configured=False)
            with pytest.raises(web.HTTPError) as exc_info:
                handler.get()
            assert exc_info.value.status_code == 500

        def test_calls_super_when_configured(self, monkeypatch):
            handler = self._make_handler(monkeypatch, configured=True)
            super_called = []
            monkeypatch.setattr(OAuthLoginHandler, "get", lambda _: super_called.append(True))
            handler.get()
            assert super_called


class TestKeyCloakAuthenticator:
    class TestInit:
        def test_raises_if_not_oidc_issuer(self):
            with pytest.raises(Exception, match="No OIDC issuer url provided"):
                KeyCloakAuthenticator()

    class TestValidators:
        def test_pre_spawn_hook_raises_for_non_callable(self, unconfigured_authenticator):
            with pytest.raises(TraitError):
                unconfigured_authenticator.pre_spawn_hook = "not callable"

        def test_claim_roles_key_raises_for_non_callable(self, unconfigured_authenticator):
            with pytest.raises(TraitError):
                unconfigured_authenticator.claim_roles_key = "not callable"

        def test_default_claim_roles_key_returns_empty_set_when_no_resource_access(self, authenticator):
            roles = authenticator.claim_roles_key(authenticator, {})
            assert roles == set()

    class TestGetOidcConfigs:
        @pytest.mark.parametrize(
            "doc",
            [
                {},
                {"authorization_endpoint": "http://fake/auth"},
                {"authorization_endpoint": "http://fake/auth", "token_endpoint": "http://fake/token"},
                {"token_endpoint": "http://fake/token"},
            ],
        )
        async def test_missing_required_authorisation_fields(self, unconfigured_authenticator, monkeypatch, doc):
            async def mock_httpfetch(url, **kwargs):
                return doc

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            with pytest.raises(Exception, match="Unable to retrieve OIDC necessary values"):
                await unconfigured_authenticator._get_oidc_configs_helper()

            assert not unconfigured_authenticator.configured

        async def test_set_urls(self, unconfigured_authenticator, monkeypatch):
            async def mock_httpfetch(url, **kwargs):
                return OIDC_DISCOVERY_DOC

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.authorize_url == "http://fake/auth"
            assert unconfigured_authenticator.token_url == "http://fake/token"
            assert unconfigured_authenticator.userdata_url == "http://fake/userinfo"
            assert unconfigured_authenticator.configured

        async def test_enable_logout_end_session_no_existing_redirect_url(
            self, unconfigured_authenticator, monkeypatch
        ):
            unconfigured_authenticator.enable_logout = True
            unconfigured_authenticator.logout_redirect_url = ""

            async def mock_httpfetch(url, **kwargs):
                return {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.logout_redirect_url == "http://fake/logout"

        async def test_enable_logout_end_session_existing_redirect_url(self, unconfigured_authenticator, monkeypatch):
            unconfigured_authenticator.enable_logout = True
            unconfigured_authenticator.logout_redirect_url = "http://fake/post-logout"
            unconfigured_authenticator.client_id = "dummy-client"

            async def mock_httpfetch(url, **kwargs):
                return {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.logout_redirect_url == (
                f"http://fake/logout?post_logout_redirect_uri={quote_plus('http://fake/post-logout')}&client_id=dummy-client"
            )

        @pytest.mark.parametrize(
            "enable_logout,doc",
            [
                (False, {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}),
                (True, OIDC_DISCOVERY_DOC),
            ],
        )
        async def test_logout_url_not_updated(self, unconfigured_authenticator, monkeypatch, enable_logout, doc):
            unconfigured_authenticator.enable_logout = enable_logout
            original_logout_url = unconfigured_authenticator.logout_redirect_url

            async def mock_httpfetch(url, **kwargs):
                return doc

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.logout_redirect_url == original_logout_url

        async def test_check_signature_true_sig_key_present(self, unconfigured_authenticator, monkeypatch, key_pair):
            public_key, _ = key_pair
            jwks = _make_jwks(public_key, use_sig=True)

            call_count = 0

            async def mock_httpfetch(url, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {**OIDC_DISCOVERY_DOC, "jwks_uri": "http://fake/certs"}
                return jwks

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)
            unconfigured_authenticator.check_signature = True

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.public_key is not None
            assert call_count == 2

        async def test_check_signature_true_no_sig_key(self, unconfigured_authenticator, monkeypatch, key_pair):
            public_key, _ = key_pair
            jwks = _make_jwks(public_key, use_sig=False)

            call_count = 0

            async def mock_httpfetch(url, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {**OIDC_DISCOVERY_DOC, "jwks_uri": "http://fake/certs"}
                return jwks

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)
            unconfigured_authenticator.check_signature = True

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert unconfigured_authenticator.public_key is not None

        async def test_check_signature_false_skip_jwks_fetch(self, unconfigured_authenticator, monkeypatch):
            call_count = 0

            async def mock_httpfetch(url, **kwargs):
                nonlocal call_count
                call_count += 1
                return OIDC_DISCOVERY_DOC

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._get_oidc_configs_helper()

            assert call_count == 1
            assert unconfigured_authenticator.public_key is None

        async def test_retries_after_failure(self, unconfigured_authenticator, monkeypatch):
            call_count = 0

            async def mock_helper(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("transient failure")
                unconfigured_authenticator.configured = True

            sleep_calls = []

            async def mock_sleep(duration):
                sleep_calls.append(duration)

            monkeypatch.setattr(KeyCloakAuthenticator, "_get_oidc_configs_helper", mock_helper)
            monkeypatch.setattr(asyncio, "sleep", mock_sleep)

            await unconfigured_authenticator._get_oidc_configs()

            assert call_count == 2
            assert len(sleep_calls) == 1
            assert sleep_calls[0] == 60

    class TestAllowedRoles:
        async def _check_allowed(self, authenticator, roles):
            auth_model = {"name": "test-user", "admin": None, "auth_state": {"roles": roles}}
            auth_model = await authenticator._apply_managed_groups(auth_model)
            return await authenticator.check_allowed("test-user", auth_model)

        async def test_allow_all_permits_all(self, unconfigured_authenticator):
            unconfigured_authenticator.allow_all = True
            assert await self._check_allowed(unconfigured_authenticator, ["any-role"])
            assert await self._check_allowed(unconfigured_authenticator, [])

        async def test_matching_role_permits(self, unconfigured_authenticator):
            unconfigured_authenticator.allowed_groups = {"users"}
            assert await self._check_allowed(unconfigured_authenticator, ["admins", "users"])

        async def test_no_matching_role_denies(self, unconfigured_authenticator):
            unconfigured_authenticator.allowed_groups = {"users"}
            assert not await self._check_allowed(unconfigured_authenticator, ["non-user"])

        async def test_admin_no_matching_role_permits(self, unconfigured_authenticator):
            unconfigured_authenticator.admin_groups = {"admins"}
            unconfigured_authenticator.allowed_groups = {"users"}
            assert await self._check_allowed(unconfigured_authenticator, ["admins"])

        async def test_admin_role_sets_admin_and_permits(self, unconfigured_authenticator):
            unconfigured_authenticator.admin_groups = {"admins"}
            auth_model = {"name": "test-user", "admin": None, "auth_state": {"roles": ["admins"]}}
            auth_model = await unconfigured_authenticator._apply_managed_groups(auth_model)
            assert auth_model["admin"]
            assert await unconfigured_authenticator.check_allowed("test-user", auth_model)

        async def test_non_admin_role_does_not_set_admin(self, unconfigured_authenticator):
            unconfigured_authenticator.admin_groups = {"admins"}
            auth_model = {"name": "test-user", "admin": None, "auth_state": {"roles": ["users"]}}
            auth_model = await unconfigured_authenticator._apply_managed_groups(auth_model)
            assert not auth_model["admin"]
            assert not await unconfigured_authenticator.check_allowed("test-user", auth_model)

    class TestDecodeToken:
        def _setup(self, authenticator, public_key):
            authenticator.public_key = public_key
            authenticator.client_id = "dummy-client-id"
            authenticator.oidc_issuer = "dummy-oidc-url"
            authenticator.check_signature = True

        def test_returns_decoded_payload_for_valid_token(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            token = _get_mock_token(private_key, "test-token")
            result = authenticator._decode_token(token, options={})
            assert result is not None
            assert result["jti"] == "test-token"

        def test_returns_none_for_expired_token(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            token = _get_mock_token(private_key, "test-token", expired=True)
            assert authenticator._decode_token(token, options={}) is None

        def test_skips_signature_when_check_signature_disabled(self, authenticator, key_pair):
            _, _ = key_pair
            _, other_private_key = _generate_mock_public_private_key_pair()
            # public_key from key_pair A, token signed with key B — signature mismatch
            authenticator.public_key = key_pair[0]
            authenticator.client_id = "dummy-client-id"
            authenticator.oidc_issuer = "dummy-oidc-url"
            authenticator.check_signature = False
            token = _get_mock_token(other_private_key, "test-token")
            assert authenticator._decode_token(token, options={}) is not None

        def test_skips_audience_when_verify_aud_disabled(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            authenticator.client_id = "wrong-audience"
            authenticator.verify_aud = False
            token = _get_mock_token(private_key, "test-token")
            assert authenticator._decode_token(token, options={}) is not None

        def test_default_options_immutability(self, authenticator, key_pair):
            public_key, _ = key_pair
            self._setup(authenticator, public_key)

            # generate a bad token to check failure
            _, other_private_key = _generate_mock_public_private_key_pair()
            token = _get_mock_token(other_private_key, "test-token")

            # first time bad token passes since check_signature is false
            authenticator.check_signature = False
            assert authenticator._decode_token(token) is not None

            # make sure this fails since check_signature is now true
            authenticator.check_signature = True
            with pytest.raises(jwt.exceptions.InvalidSignatureError):
                authenticator._decode_token(token)

    class TestExchangeTokens:
        async def test_empty_response_body_skips_service(self, authenticator, monkeypatch):
            authenticator.exchange_tokens = ["service-a"]

            async def mock_fetch(*_, **_kw):
                return MockFetchResponse(body="")

            monkeypatch.setattr(authenticator, "fetch", mock_fetch)

            result = await authenticator._exchange_tokens("dummy-token")

            assert "service-a" not in result

        async def test_missing_access_token_in_body_skips_service(self, authenticator, monkeypatch):
            authenticator.exchange_tokens = ["service-a"]

            async def mock_fetch(*_, **_kw):
                return MockFetchResponse(body=json.dumps({"other": "stuff"}).encode())

            monkeypatch.setattr(authenticator, "fetch", mock_fetch)

            result = await authenticator._exchange_tokens("dummy-token")

            assert "service-a" not in result

        async def test_returns_access_token_for_service(self, authenticator, monkeypatch):
            authenticator.exchange_tokens = ["service-a"]

            async def mock_fetch(*_, **_kw):
                return MockFetchResponse(body=json.dumps({"access_token": "token-for-a"}).encode())

            monkeypatch.setattr(authenticator, "fetch", mock_fetch)

            result = await authenticator._exchange_tokens("dummy-token")

            assert result == {"service-a": "token-for-a"}

    class TestRefreshUser:
        def _make_mock_user(self, access_token="old-access", refresh_token="old-refresh"):
            token_response = {"access_token": access_token, "refresh_token": refresh_token, "token_type": "Bearer"}

            class MockUser:
                name = "test-user"

                async def get_auth_state(self_inner):
                    return {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_response": token_response,
                    }

            return MockUser()

        # Unit tests: upstream refresh_user is mocked

        async def test_returns_false_when_not_configured(self, authenticator):
            authenticator.configured = False
            result = await authenticator.refresh_user(self._make_mock_user())
            assert not result

        async def test_returns_false_when_upstream_returns_false(self, authenticator, monkeypatch):
            monkeypatch.setattr(GenericOAuthenticator, "refresh_user", AsyncMock(return_value=False))
            assert await authenticator.refresh_user(self._make_mock_user()) is False

        async def test_returns_true_when_upstream_returns_true(self, authenticator, monkeypatch):
            monkeypatch.setattr(GenericOAuthenticator, "refresh_user", AsyncMock(return_value=True))
            assert await authenticator.refresh_user(self._make_mock_user()) is True

        async def test_exchanges_tokens_of_upstream_auth_model(self, authenticator, monkeypatch):
            auth_model = {"name": "test-user", "auth_state": {"access_token": "new-access"}}
            monkeypatch.setattr(GenericOAuthenticator, "refresh_user", AsyncMock(return_value=auth_model))
            monkeypatch.setattr(
                authenticator, "_exchange_tokens", AsyncMock(side_effect=lambda t: {"service-a": f"exchanged-{t}"})
            )

            result = await authenticator.refresh_user(self._make_mock_user())

            assert result is auth_model
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged-new-access"}

        async def test_returns_false_when_exchange_tokens_fails(self, authenticator, monkeypatch):
            monkeypatch.setattr(
                GenericOAuthenticator,
                "refresh_user",
                AsyncMock(return_value={"name": "test-user", "auth_state": {"access_token": "a"}}),
            )
            monkeypatch.setattr(authenticator, "_exchange_tokens", AsyncMock(side_effect=Exception("exchange failed")))

            assert await authenticator.refresh_user(self._make_mock_user()) is False

        async def test_returns_false_on_exception(self, authenticator, monkeypatch):
            monkeypatch.setattr(GenericOAuthenticator, "refresh_user", AsyncMock(side_effect=Exception("db error")))
            assert await authenticator.refresh_user(self._make_mock_user()) is False

        # Integration tests: run through upstream refresh_user, only mocking the IdP endpoints,
        # JWT decoding and token exchange. These check that our hooks fit upstream's flow.

        EXPIRED_TOKEN = "expired-access"

        @pytest.fixture
        def idp(self, authenticator, monkeypatch):
            """
            Fake IdP. The token endpoint always issues new-access/new-refresh.
            The userinfo endpoint answers with the HTTP code in userinfo_errors for the given access token.
            """
            authenticator.userdata_url = "http://fake/userinfo"
            idp = SimpleNamespace(userinfo_errors={})

            async def mock_httpfetch(url, label="fetching", parse_json=True, raise_error=True, **kwargs):
                if url == authenticator.token_url:
                    return {"access_token": "new-access", "refresh_token": "new-refresh", "token_type": "Bearer"}
                if url == authenticator.userdata_url:
                    token = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
                    if token in idp.userinfo_errors:
                        raise HTTPClientError(idp.userinfo_errors[token])
                    return {"username": "test-user"}
                raise AssertionError(f"Unexpected request to {url}")

            def mock_decode_token(token, options=None):
                if token == self.EXPIRED_TOKEN:
                    return None
                return {"resource_access": {"dummy-client": {"roles": [f"role-{token}"]}}}

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)
            monkeypatch.setattr(authenticator, "_decode_token", mock_decode_token)
            monkeypatch.setattr(
                authenticator, "_exchange_tokens", AsyncMock(side_effect=lambda t: {"service-a": f"exchanged-{t}"})
            )
            return idp

        async def test_valid_access_token(self, authenticator, idp):
            result = await authenticator.refresh_user(self._make_mock_user())

            assert result["auth_state"]["roles"] == ["role-old-access"]
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged-old-access"}
            assert result["groups"] == ["role-old-access"]

        async def test_access_token_rejected_by_userinfo(self, authenticator, idp):
            idp.userinfo_errors = {"old-access": 401}

            result = await authenticator.refresh_user(self._make_mock_user())

            assert result["auth_state"]["roles"] == ["role-new-access"]
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged-new-access"}
            assert result["groups"] == ["role-new-access"]

        async def test_access_token_expired_but_accepted_by_userinfo(self, authenticator, idp):
            # e.g. clock skew: the IdP still accepts the token but it is expired for us.
            # Our hook must make upstream fall back to the refresh token.
            result = await authenticator.refresh_user(self._make_mock_user(access_token=self.EXPIRED_TOKEN))

            assert result["auth_state"]["access_token"] == "new-access"
            assert result["auth_state"]["roles"] == ["role-new-access"]
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged-new-access"}
            assert result["groups"] == ["role-new-access"]

    class TestModifyAuthStateHook:
        def test_raises_when_decode_token_raises(self, authenticator, monkeypatch):
            def mock_decode(*_):
                raise Exception("bad token")

            monkeypatch.setattr(authenticator, "_decode_token", mock_decode)
            with pytest.raises(Exception, match="bad token"):
                authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

        def test_raises_when_claim_roles_key_raises(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", lambda *_: {})
            monkeypatch.setattr(
                authenticator, "claim_roles_key", lambda *_: (_ for _ in ()).throw(Exception("roles error"))
            )
            with pytest.raises(Exception, match="roles error"):
                authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

        def test_writes_roles_to_auth_state(self, authenticator, monkeypatch):
            decoded_token = {"resource_access": {"dummy-client": {"roles": ["swan-admins"]}}}
            monkeypatch.setattr(authenticator, "_decode_token", lambda *_: decoded_token)

            auth_state = authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

            assert auth_state["roles"] == ["swan-admins"]

    class TestAuthenticate:
        def _make_mock_user(self):
            return {"name": "test-user", "admin": None, "auth_state": {"access_token": "dummy-token", "roles": []}}

        def _patch_super(self, monkeypatch, return_value):
            async def mock_super(self, handler, data=None):
                return return_value

            monkeypatch.setattr(GenericOAuthenticator, "authenticate", mock_super)

        async def test_returns_none_when_super_returns_none(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, None)
            assert await authenticator.authenticate(None) is None

        async def test_returns_none_when_exchange_tokens_raises(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, self._make_mock_user())
            monkeypatch.setattr(authenticator, "_decode_token", lambda *_: {})
            monkeypatch.setattr(authenticator, "claim_roles_key", lambda *_: {"user-role"})

            async def mock_exchange_tokens(_):
                raise Exception("exchange failed")

            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)
            assert await authenticator.authenticate(None) is None

        async def test_returns_user_on_success(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, self._make_mock_user())
            monkeypatch.setattr(authenticator, "_decode_token", lambda *_: {})
            monkeypatch.setattr(authenticator, "claim_roles_key", lambda *_: {"user-role"})

            async def mock_exchange_tokens(_):
                return {"service-a": "exchanged"}

            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)

            result = await authenticator.authenticate(None)

            assert result is not None
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged"}
            assert not result["admin"]

    class TestPreSpawnStart:
        async def test_does_nothing_when_no_hook(self, authenticator):
            user = MagicMock()
            await authenticator.pre_spawn_start(user, MagicMock())
            user.get_auth_state.assert_not_called()

        async def test_calls_sync_hook_with_auth_state(self, authenticator):
            auth_state = {"access_token": "test-token"}
            hook_calls = []

            async def mock_get_auth_state():
                return auth_state

            def mock_hook(auth, spawner, state):
                hook_calls.append(state)

            user = MagicMock()
            user.get_auth_state = mock_get_auth_state
            authenticator.pre_spawn_hook = mock_hook

            await authenticator.pre_spawn_start(user, MagicMock())

            assert hook_calls == [auth_state]
