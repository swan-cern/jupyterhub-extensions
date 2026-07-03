import json
import asyncio

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ..auth import KeyCloakAuthenticator


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
    async def _break_retry_loop(_):
        raise RuntimeError("asyncio.sleep called unexpectedly — check for uncaught exceptions in _get_oidc_configs")
    monkeypatch.setattr(asyncio, "sleep", _break_retry_loop)
    auth = KeyCloakAuthenticator(oidc_issuer="http://fake-issuer")
    auth.config.check_signature = False  # disabled by default; check_signature tests enable it explicitly
    return auth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OIDC_DISCOVERY_DOC = {
    "authorization_endpoint": "http://fake/auth",
    "token_endpoint": "http://fake/token",
    "userinfo_endpoint": "http://fake/userinfo",
}


# ---------------------------------------------------------------------------
# TestGetOidcConfigs
# ---------------------------------------------------------------------------

class TestGetOidcConfigs:
    """
    options are:
     - authorize_url, token_url, userdata_url not all present, expect exception and have to break loop by patching sleep [test_missing_required_authorisation_fields]

     - authorize_url, token_url, userdata_url all present, 
        - enable_logout and end_session present
            - logout_redirect_url not present
            - logout_redirect_url present

        - enable_logout and end_session not all present

        - check_signature True
            - sign_keys True
            - sign_keys False
        - check_signature False
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("doc", [
        {},
        {"authorization_endpoint": "http://fake/auth"},
        {"authorization_endpoint": "http://fake/auth", "token_endpoint": "http://fake/token"},
        {"token_endpoint": "http://fake/token"},
    ])
    async def test_missing_required_authorisation_fields(self, unconfigured_authenticator, monkeypatch, doc):
        async def mock_httpfetch(url, **kwargs):
            return doc

        async def mock_sleep(_):
            raise RuntimeError("breaking retry loop")

        monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)
        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        with pytest.raises(RuntimeError):
            await unconfigured_authenticator._get_oidc_configs()

        assert unconfigured_authenticator.configured is False


    @pytest.mark.asyncio
    async def test_set_urls(self, unconfigured_authenticator, monkeypatch):
        async def mock_httpfetch(url, **kwargs):
            return OIDC_DISCOVERY_DOC

        monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

        await unconfigured_authenticator._get_oidc_configs()

        assert unconfigured_authenticator.authorize_url == "http://fake/auth"
        assert unconfigured_authenticator.token_url == "http://fake/token"
        assert unconfigured_authenticator.userdata_url == "http://fake/userinfo"
        assert unconfigured_authenticator.configured is True


    @pytest.mark.asyncio
    async def test_enable_logout_end_session_no_existing_redirect_url(self, unconfigured_authenticator, monkeypatch):
        unconfigured_authenticator.enable_logout = True
        unconfigured_authenticator.logout_redirect_url = ""

        async def mock_httpfetch(url, **kwargs):
            return {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}

        monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

        await unconfigured_authenticator._get_oidc_configs()

        assert unconfigured_authenticator.logout_redirect_url == "http://fake/logout"

    @pytest.mark.asyncio
    async def test_enable_logout_end_session_existing_redirect_url(self, unconfigured_authenticator, monkeypatch):
        unconfigured_authenticator.enable_logout = True
        unconfigured_authenticator.logout_redirect_url = "http://fake/post-logout"
        unconfigured_authenticator.client_id = "dummy-client"

        async def mock_httpfetch(url, **kwargs):
            return {**OIDC_DISCOVERY_DOC, "end_session_endpoint": "http://fake/logout"}

        monkeypatch.setattr(unconfigured_authenticator, "httpfetch", mock_httpfetch)

        await unconfigured_authenticator._get_oidc_configs()

        assert unconfigured_authenticator.logout_redirect_url == (
            "http://fake/logout"
            "?post_logout_redirect_uri=http://fake/post-logout"
            "&client_id=dummy-client"
        )


@pytest.mark.asyncio
async def test_refresh_user(monkeypatch):
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


@pytest.mark.asyncio
async def test_refresh_user_with_expired_refresh_token(monkeypatch):
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
