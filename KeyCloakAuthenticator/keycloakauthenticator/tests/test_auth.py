import asyncio
import json

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from tornado import web

from unittest.mock import MagicMock

from ..auth import KeyCloakAuthenticator, OIDCOAuthLoginHandler
from oauthenticator.oauth2 import OAuthLoginHandler


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
    auth = KeyCloakAuthenticator(oidc_issuer="http://fake-issuer")
    auth.config.check_signature = False  # disabled by default; check_signature tests enable it explicitly
    return auth


@pytest.fixture
def key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.public_key(), private_key


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


class TestOIDCOAuthLoginHandler:
    class TestGet:
        def _make_handler(self, monkeypatch, configured):
            handler = OIDCOAuthLoginHandler.__new__(OIDCOAuthLoginHandler)
            monkeypatch.setattr(OIDCOAuthLoginHandler, "authenticator", property(lambda _: MagicMock(configured=configured)))
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

    class TestGetOidcConfigs:
        @pytest.mark.parametrize("doc", [
            {},
            {"authorization_endpoint": "http://fake/auth"},
            {"authorization_endpoint": "http://fake/auth", "token_endpoint": "http://fake/token"},
            {"token_endpoint": "http://fake/token"},
        ])
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



        async def test_enable_logout_end_session_no_existing_redirect_url(self, unconfigured_authenticator, monkeypatch):
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
                "http://fake/logout"
                "?post_logout_redirect_uri=http://fake/post-logout"
                "&client_id=dummy-client"
            )


        @pytest.mark.parametrize("enable_logout,doc", [
            (False, {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}),
            (True, OIDC_DISCOVERY_DOC),
        ])
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
            unconfigured_authenticator.config.check_signature = True

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
            unconfigured_authenticator.config.check_signature = True

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



    async def test_refresh_user(self, monkeypatch):
        """
        Test KeyCloakAuthenticator.refresh_user() when everything works fine.
        Mocks the initial configuration with the server, and HTTP requests with a fake JWTs
        """
    
        public_key, private_key = _generate_mock_public_private_key_pair()
    
        async def mock_get_oidc_config(self):
            pass
        
        # The authenticator fetches OIDC configuration from KeyCloak on startup
        # mock that step, and configure some dummy configuration
        monkeypatch.setattr(
            KeyCloakAuthenticator, "_get_oidc_configs", mock_get_oidc_config
        )
        monkeypatch.setattr(KeyCloakAuthenticator, "oidc_issuer", "dummy-oidc-url")
    
        # Mock the response from the server on refresh and exchange tokens
        async def _mock_fetch(self, req, label, **kargs):
            print(f"Mocking fetch for {req} ({label})")
            mock_response_body = json.dumps({
                "access_token": _get_mock_token(private_key, "new_access_token"),
                "refresh_token": _get_mock_token(private_key, "new_refresh_token"),
                })
    
            class MockResponse:
                def __init__(self):
                    self.code = 200
                    self.body = mock_response_body.encode('utf-8')
                    self.request_time = 0
                    self.time_info = {
                        "queue": 0
                    }
            return MockResponse()
        monkeypatch.setattr(KeyCloakAuthenticator, "fetch", _mock_fetch)
    
        class MockUser:
            """Fake user object, with dummy authentication state from DB"""
            name = "dummy-user"
    
            async def get_auth_state(self):
                return {
                    "access_token": _get_mock_token(
                        private_key, "old_access_token", expired=True
                    ),
                    "refresh_token": _get_mock_token(private_key, "old_refresh_token"),
                }
    
        authenticator = KeyCloakAuthenticator()
        authenticator.configured = True
        authenticator.public_key = public_key
        authenticator.client_id = "dummy-client-id"
        authenticator.client_secret = "dummy-client-secret"
        authenticator.exchange_tokens = ["another-service-audience"]
    
        updated_auth_state = await authenticator.refresh_user(MockUser())
    
        # Assert that the refreshed tokens are returned as the new auth_state
        assert updated_auth_state["auth_state"]["refresh_token"] == _get_mock_token(
            private_key, "new_refresh_token"
        )
    
        assert updated_auth_state["auth_state"]["access_token"] == _get_mock_token(
            private_key, "new_access_token"
        )
    
    
    
    
    async def test_refresh_user_with_expired_refresh_token(self, monkeypatch):
        """
        Test KeyCloakAuthenticator.refresh_user() when the refresh_token stored in the users auth_state
        in the DB is expired, expecting the refresh to fail and return false.
    
        Mocks the initial configuration with the server, and HTTP requests with a fake JWTs that are expired
        """
    
        public_key, private_key = _generate_mock_public_private_key_pair()
    
        async def mock_get_oidc_config(self):
            pass
        
        # The authenticator fetches OIDC configuration from KeyCloak on startup
        # mock that step, and configure some dummy configuration
        monkeypatch.setattr(
            KeyCloakAuthenticator, "_get_oidc_configs", mock_get_oidc_config
        )
        # Mock the response from the server on refresh and exchange tokens
        monkeypatch.setattr(KeyCloakAuthenticator, "oidc_issuer", "dummy-oidc-url")
    
        async def _mock_httpfetch(self, url, label, **kargs):
            print(f"Mocking httpfetch for {url} ({label})")
            mock_response_body = json.dumps({
                "access_token": _get_mock_token(private_key, "new_access_token"),
                "refresh_token": _get_mock_token(private_key, "new_refresh_token"),
                })
    
            class MockResponse:
                def __init__(self):
                    self.code = 200
                    self.body = mock_response_body.encode('utf-8')
                    self.request_time = 0
                    self.time_info = {
                        "queue": 0
                    }
            return MockResponse()
        monkeypatch.setattr(KeyCloakAuthenticator, "httpfetch", _mock_httpfetch)
    
        class MockUser:
            """Fake user object, with dummy authentication state from DB"""
            name = "dummy-user"
    
            async def get_auth_state(self):
                return {
                    "access_token": _get_mock_token(
                        private_key, "old_access_token", expired=True
                    ),
                    "refresh_token": _get_mock_token(
                        private_key, "old_refresh_token", expired=True
                    ),
                }
    
        authenticator = KeyCloakAuthenticator()
        authenticator.configured = True
        authenticator.public_key = public_key
        authenticator.client_id = "dummy-client-id"
        authenticator.client_secret = "dummy-client-secret"
        authenticator.exchange_tokens = ["another-service-audience"]
    
        refresh_result = await authenticator.refresh_user(MockUser())
    
        assert refresh_result is False
