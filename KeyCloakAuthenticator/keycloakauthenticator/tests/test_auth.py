import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ..auth import KeyCloakAuthenticator


def _generate_mock_public_private_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return (public_key, private_key)


def _get_mock_token(private_key, token_id):
    return jwt.encode(
        payload={
            "sub": "dummy-subject",
            "iss": "dummy-oidc-url",
            "aud": "dummy-client-id",
            "iat": 0,  # Issued a long time ago: 1/1/1970
            "exp": 9999999999,  # One long-lasting token, expiring 11/20/2286
            "permissions": ["read", "write"],
            "jti": token_id,
        },
        key=private_key,
        algorithm="RS256",
        headers={"kid": "dummy-key-id"},
    )


@pytest.mark.asyncio
async def test_refresh_user(monkeypatch):

    public_key, private_key = _generate_mock_public_private_key_pair()

    async def mock_get_oidc_config(self):
        pass

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

    monkeypatch.setattr(KeyCloakAuthenticator, "fetch", fetch)

    class MockUser:
        name = "dummy-user"

        async def get_auth_state(self):
            return {
                "access_token": _get_mock_token(private_key, "old_access_token"),
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
