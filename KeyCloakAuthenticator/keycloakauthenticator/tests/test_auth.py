import json
from unittest.mock import AsyncMock, MagicMock
from urllib.error import HTTPError
from urllib.parse import parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jupyterhub.handlers.login import LogoutHandler
from jwt.algorithms import RSAAlgorithm
from oauthenticator.oidc import OIDCOAuthenticator
from traitlets import TraitError

from ..auth import KeyCloakAuthenticator, KeyCloakLogoutHandler


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
def unconfigured_authenticator():
    auth = KeyCloakAuthenticator(openid_provider_url="http://fake-issuer", manage_groups=True)
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
    unconfigured_authenticator.openid_configuration = OIDC_DISCOVERY_DOC
    return unconfigured_authenticator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OIDC_DISCOVERY_DOC = {
    "issuer": "http://fake-issuer",
    "jwks_uri": "http://fake/certs",
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


class TestKeyCloakAuthenticator:
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

    class TestLoadOpenidConfiguration:
        async def test_set_urls(self, unconfigured_authenticator, monkeypatch):
            async def mock_httpfetch(url, **kwargs):
                return OIDC_DISCOVERY_DOC

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._load_openid_configuration()

            assert unconfigured_authenticator.authorize_url == "http://fake/auth"
            assert unconfigured_authenticator.token_url == "http://fake/token"
            assert unconfigured_authenticator.userdata_url == "http://fake/userinfo"

        async def test_check_signature_true_sig_key_present(self, unconfigured_authenticator, monkeypatch, key_pair):
            public_key, _ = key_pair
            jwks = _make_jwks(public_key, use_sig=True)

            call_count = 0

            async def mock_httpfetch(url, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return OIDC_DISCOVERY_DOC
                return jwks

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)
            unconfigured_authenticator.check_signature = True

            await unconfigured_authenticator._load_openid_configuration()
            await unconfigured_authenticator._load_jwk_signature()

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
                    return OIDC_DISCOVERY_DOC
                return jwks

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)
            unconfigured_authenticator.check_signature = True

            await unconfigured_authenticator._load_openid_configuration()
            await unconfigured_authenticator._load_jwk_signature()

            assert unconfigured_authenticator.public_key is not None

        async def test_check_signature_false_skip_jwks_fetch(self, unconfigured_authenticator, monkeypatch):
            call_count = 0

            async def mock_httpfetch(url, **kwargs):
                nonlocal call_count
                call_count += 1
                return OIDC_DISCOVERY_DOC

            monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

            await unconfigured_authenticator._load_openid_configuration()
            await unconfigured_authenticator._load_jwk_signature()

            assert call_count == 1
            assert unconfigured_authenticator.public_key is None

    class TestLogoutHandler:
        END_SESSION_URL = "http://fake/logout"
        POST_LOGOUT_URL = "http://fake/post-logout"

        @pytest.fixture
        def handler(self, authenticator, monkeypatch):
            authenticator.openid_configuration = {**OIDC_DISCOVERY_DOC, "end_session_endpoint": self.END_SESSION_URL}
            # as filled by upstream when loading the OIDC configuration
            authenticator.logout_redirect_url = self.END_SESSION_URL
            monkeypatch.setattr(KeyCloakLogoutHandler, "authenticator", authenticator)
            handler = KeyCloakLogoutHandler.__new__(KeyCloakLogoutHandler)
            handler.redirect = MagicMock()
            return handler

        @pytest.fixture
        def default_logout_page(self, monkeypatch):
            mock = AsyncMock()
            monkeypatch.setattr(LogoutHandler, "render_logout_page", mock)
            return mock

        async def test_sso_logout_with_post_logout_redirect_url(self, handler, authenticator):
            authenticator.post_logout_redirect_url = self.POST_LOGOUT_URL

            await handler.render_logout_page()

            url = handler.redirect.call_args.args[0]
            base, query = url.split("?", 1)
            assert base == self.END_SESSION_URL
            assert parse_qs(query) == {
                "post_logout_redirect_uri": [self.POST_LOGOUT_URL],
                "client_id": ["dummy-client"],
            }

        async def test_sso_logout_without_post_logout_redirect_url(self, handler):
            await handler.render_logout_page()

            # the end_session_endpoint upstream stored in logout_redirect_url is not used as redirect target
            handler.redirect.assert_called_once_with(self.END_SESSION_URL)

        async def test_sso_logout_disabled_redirects_to_post_logout_redirect_url(self, handler, authenticator):
            authenticator.enable_logout = False
            authenticator.post_logout_redirect_url = self.POST_LOGOUT_URL

            await handler.render_logout_page()

            handler.redirect.assert_called_once_with(self.POST_LOGOUT_URL)

        async def test_no_end_session_endpoint_redirects_to_post_logout_redirect_url(self, handler, authenticator):
            authenticator.openid_configuration = OIDC_DISCOVERY_DOC
            authenticator.post_logout_redirect_url = self.POST_LOGOUT_URL

            await handler.render_logout_page()

            handler.redirect.assert_called_once_with(self.POST_LOGOUT_URL)

        async def test_sso_logout_disabled_shows_logout_page(self, handler, authenticator, default_logout_page):
            authenticator.enable_logout = False

            await handler.render_logout_page()

            # no redirect to the end_session_endpoint stored in logout_redirect_url
            handler.redirect.assert_not_called()
            default_logout_page.assert_awaited_once_with(handler)

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
            unconfigured_authenticator.allowed_groups = {"admin"}
            assert await self._check_allowed(unconfigured_authenticator, ["admin", "user"])

        async def test_no_matching_role_denies(self, unconfigured_authenticator):
            unconfigured_authenticator.allowed_groups = {"admin"}
            assert not await self._check_allowed(unconfigured_authenticator, ["user"])

        async def test_admin_role_sets_admin_and_permits(self, unconfigured_authenticator):
            unconfigured_authenticator.admin_groups = {"swan-admins"}
            auth_model = {"name": "test-user", "admin": None, "auth_state": {"roles": ["swan-admins"]}}
            auth_model = await unconfigured_authenticator._apply_managed_groups(auth_model)
            assert auth_model["admin"]
            assert await unconfigured_authenticator.check_allowed("test-user", auth_model)

        async def test_non_admin_role_does_not_set_admin(self, unconfigured_authenticator):
            unconfigured_authenticator.admin_groups = {"swan-admins"}
            auth_model = {"name": "test-user", "admin": None, "auth_state": {"roles": ["user"]}}
            auth_model = await unconfigured_authenticator._apply_managed_groups(auth_model)
            assert not auth_model["admin"]
            assert not await unconfigured_authenticator.check_allowed("test-user", auth_model)

    class TestDecodeToken:
        def _setup(self, authenticator, public_key):
            authenticator.public_key = public_key
            authenticator.client_id = "dummy-client-id"
            authenticator.jwt_issuer = "dummy-oidc-url"
            authenticator.check_signature = True

        async def test_returns_decoded_payload_for_valid_token(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            token = _get_mock_token(private_key, "test-token")
            result = await authenticator._decode_token(token)
            assert result is not None
            assert result["jti"] == "test-token"

        async def test_returns_none_for_expired_token(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            token = _get_mock_token(private_key, "test-token", expired=True)
            assert await authenticator._decode_token(token) is None

        async def test_skips_signature_when_check_signature_disabled(self, authenticator, key_pair):
            _, _ = key_pair
            _, other_private_key = _generate_mock_public_private_key_pair()
            # public_key from key_pair A, token signed with key B — signature mismatch
            authenticator.public_key = key_pair[0]
            authenticator.client_id = "dummy-client-id"
            authenticator.jwt_issuer = "dummy-oidc-url"
            authenticator.check_signature = False
            token = _get_mock_token(other_private_key, "test-token")
            assert await authenticator._decode_token(token) is not None

        async def test_skips_audience_when_verify_aud_disabled(self, authenticator, key_pair):
            public_key, private_key = key_pair
            self._setup(authenticator, public_key)
            authenticator.client_id = "wrong-audience"
            authenticator.verify_aud = False
            token = _get_mock_token(private_key, "test-token")
            assert await authenticator._decode_token(token) is not None

        async def test_default_options_immutability(self, authenticator, key_pair):
            public_key, _ = key_pair
            self._setup(authenticator, public_key)

            # generate a bad token to check failure
            _, other_private_key = _generate_mock_public_private_key_pair()
            token = _get_mock_token(other_private_key, "test-token")

            # first time bad token passes since check_signature is false
            authenticator.check_signature = False
            assert await authenticator._decode_token(token) is not None

            # make sure this fails since check_signature is now true
            authenticator.check_signature = True
            with pytest.raises(jwt.exceptions.InvalidSignatureError):
                await authenticator._decode_token(token)

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

    class TestRefreshToken:
        async def test_empty_response_body_returns_none_tokens(self, authenticator, monkeypatch):
            async def mock_httpfetch(*_, **_kw):
                return MockFetchResponse(body="")

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)

            access_t, refresh_t = await authenticator._refresh_token("old-refresh")

            assert access_t is None
            assert refresh_t is None

        async def test_missing_access_token_in_body(self, authenticator, monkeypatch):
            async def mock_httpfetch(*_, **_kw):
                return MockFetchResponse(body=json.dumps({"refresh_token": "new-refresh"}).encode())

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)

            access_t, refresh_t = await authenticator._refresh_token("old-refresh")

            assert access_t is None
            assert refresh_t == "new-refresh"

        async def test_missing_refresh_token_in_body(self, authenticator, monkeypatch):
            async def mock_httpfetch(*_, **_kw):
                return MockFetchResponse(body=json.dumps({"access_token": "new-access"}).encode())

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)

            access_t, refresh_t = await authenticator._refresh_token("old-refresh")

            assert access_t == "new-access"
            assert refresh_t is None

        async def test_returns_both_tokens_on_success(self, authenticator, monkeypatch):
            async def mock_httpfetch(*_, **_kw):
                return MockFetchResponse(
                    body=json.dumps(
                        {
                            "access_token": "new-access",
                            "refresh_token": "new-refresh",
                        }
                    ).encode()
                )

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)

            access_t, refresh_t = await authenticator._refresh_token("old-refresh")

            assert access_t == "new-access"
            assert refresh_t == "new-refresh"

        async def test_request_contains_correct_params(self, authenticator, monkeypatch):
            from urllib.parse import parse_qs

            captured = {}

            async def mock_httpfetch(url, **kwargs):
                captured["url"] = url
                captured["body"] = kwargs["body"]
                return MockFetchResponse(body="")

            monkeypatch.setattr(authenticator, "httpfetch", mock_httpfetch)

            await authenticator._refresh_token("my-refresh-token")

            assert captured["url"] == "http://fake/token"
            params = parse_qs(captured["body"])
            assert params["grant_type"] == ["refresh_token"]
            assert params["client_id"] == ["dummy-client"]
            assert params["client_secret"] == ["dummy-secret"]
            assert params["refresh_token"] == ["my-refresh-token"]

    class TestRefreshUser:
        def _make_mock_user(self, refresh_token="old-refresh", access_token="old-access"):
            class MockUser:
                name = "test-user"

                async def get_auth_state(self_inner):
                    return {"refresh_token": refresh_token, "access_token": access_token}

            return MockUser()

        async def test_returns_false_when_not_configured(self, authenticator):
            authenticator.openid_configuration = None
            result = await authenticator.refresh_user(self._make_mock_user())
            assert not result

        async def test_returns_false_when_refresh_token_expired(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value={"exp": 0}))
            result = await authenticator.refresh_user(self._make_mock_user())
            assert not result

        async def test_proceeds_when_no_exp_in_refresh_token(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value={}))

            async def mock_refresh_token(_):
                return "new-access", "new-refresh"

            async def mock_exchange_tokens(_):
                return {}

            monkeypatch.setattr(authenticator, "_refresh_token", mock_refresh_token)
            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)

            result = await authenticator.refresh_user(self._make_mock_user())
            assert result

        async def test_returns_updated_auth_state_on_success(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value={"exp": 9999999999}))

            async def mock_refresh_token(_):
                return "new-access", "new-refresh"

            async def mock_exchange_tokens(_):
                return {"service-a": "exchanged"}

            monkeypatch.setattr(authenticator, "_refresh_token", mock_refresh_token)
            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)

            result = await authenticator.refresh_user(self._make_mock_user())

            assert result["auth_state"]["access_token"] == "new-access"
            assert result["auth_state"]["refresh_token"] == "new-refresh"
            assert result["auth_state"]["exchanged_tokens"] == {"service-a": "exchanged"}

        async def test_returns_false_when_exchange_tokens_fails(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value={}))

            async def mock_refresh_token(_):
                return "new-access", "new-refresh"

            async def mock_exchange_tokens(_):
                raise Exception("exchange failed")

            monkeypatch.setattr(authenticator, "_refresh_token", mock_refresh_token)
            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)

            result = await authenticator.refresh_user(self._make_mock_user())
            assert not result

        async def test_returns_false_on_exception_in_get_auth_state(self, authenticator):
            user = MagicMock()
            user.get_auth_state = MagicMock(side_effect=Exception("db error"))
            result = await authenticator.refresh_user(user)
            assert not result

        async def test_returns_false_on_http_error(self, authenticator):
            user = MagicMock()
            user.get_auth_state = MagicMock(side_effect=HTTPError("http://fake", 500, "Server Error", {}, None))
            result = await authenticator.refresh_user(user)
            assert not result

    class TestModifyAuthStateHook:
        async def test_raises_when_decode_token_raises(self, authenticator, monkeypatch):
            async def mock_decode(*_):
                raise Exception("bad token")

            monkeypatch.setattr(authenticator, "_decode_token", mock_decode)
            with pytest.raises(Exception, match="bad token"):
                await authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

        async def test_raises_when_claim_roles_key_raises(self, authenticator, monkeypatch):
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value={}))
            monkeypatch.setattr(
                authenticator, "claim_roles_key", lambda *_: (_ for _ in ()).throw(Exception("roles error"))
            )
            with pytest.raises(Exception, match="roles error"):
                await authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

        async def test_writes_roles_to_auth_state(self, authenticator, monkeypatch):
            decoded_token = {"resource_access": {"dummy-client": {"roles": ["swan-admins"]}}}
            monkeypatch.setattr(authenticator, "_decode_token", AsyncMock(return_value=decoded_token))

            auth_state = await authenticator.modify_auth_state_hook(authenticator, {"access_token": "dummy-token"})

            assert auth_state["roles"] == ["swan-admins"]

    class TestAuthenticate:
        def _make_mock_user(self):
            return {"name": "test-user", "admin": None, "auth_state": {"access_token": "dummy-token", "roles": []}}

        def _patch_super(self, monkeypatch, return_value):
            async def mock_super(self, handler, data=None):
                return return_value

            monkeypatch.setattr(OIDCOAuthenticator, "authenticate", mock_super)

        async def test_returns_none_when_super_returns_none(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, None)
            assert await authenticator.authenticate(None) is None

        async def test_returns_none_when_exchange_tokens_raises(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, self._make_mock_user())

            async def mock_exchange_tokens(_):
                raise Exception("exchange failed")

            monkeypatch.setattr(authenticator, "_exchange_tokens", mock_exchange_tokens)
            assert await authenticator.authenticate(None) is None

        async def test_returns_user_on_success(self, authenticator, monkeypatch):
            self._patch_super(monkeypatch, self._make_mock_user())

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
