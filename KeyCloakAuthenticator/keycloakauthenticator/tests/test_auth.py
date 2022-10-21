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

    async def fetch(self, request, label):
        print("Mocking fetch for ", request, label)
        return {
            "access_token": _get_mock_token(private_key, "new_access_token"),
            "refresh_token": _get_mock_token(private_key, "new_refresh_token"),
        }

    # Mock the response from the server on refresh and exchange tokens
    monkeypatch.setattr(KeyCloakAuthenticator, "fetch", fetch)

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

    async def fetch(self, request, label):
        print("Mocking fetch for ", request, label)
        return {
            "access_token": _get_mock_token(private_key, "new_access_token"),
            "refresh_token": _get_mock_token(private_key, "new_refresh_token"),
        }

    monkeypatch.setattr(KeyCloakAuthenticator, "fetch", fetch)

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
