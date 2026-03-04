import json
from datetime import datetime, timezone

import pytest
from swanculler import app
from swanculler.app import check_blocked_users

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(name):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "name": name,
        "servers": {'': {
            "last_activity": now,
        }},
    }


class MockHTTPResponse:
    def __init__(self, code=200, body=b""):
        self.code = code
        self.body = body


class MockHTTPClient:
    def __init__(self, handler):
        self.calls = []
        self._handler = handler

    async def fetch(self, req, **kwargs):
        self.calls.append(req)
        return self._handler(req)


def _token_ok():
    return MockHTTPResponse(
        200, json.dumps({"access_token": "mock-token"}).encode()
    )


def _identity(blocked=False, disabled=False):
    return MockHTTPResponse(
        200,
        json.dumps({"data": [{"blocked": blocked, "disabled": disabled}]}).encode(),
    )


HUB_URL = "http://hub/api"
AUTH_URL = "http://auth/token"
AUTHZ_URL = "http://authz/api/identity"
API_TOKEN = "test-token"
CLIENT_ID = "client-id"
CLIENT_SECRET = "secret"
AUDIENCE = "aud"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_users():
    """Reset the global users list between tests."""
    app.users = []
    yield
    app.users = []


@pytest.fixture
def mock_http(monkeypatch):
    def _create(handler=None):
        client = MockHTTPClient(handler=handler)
        monkeypatch.setattr("swanculler.app.AsyncHTTPClient", lambda: client)
        return client

    return _create

# ---------------------------------------------------------------------------
# check_blocked_users smoke tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("is_blocked", (True, False))
@pytest.mark.parametrize("is_disabled", (True, False))
async def test_check_blocked(mock_http, is_blocked, is_disabled):
    app.users = [make_user("alice")]

    def handler(req):
        if req.method == "POST":
            return _token_ok()
        if "/accounts" in req.url:
            return _identity(blocked=is_blocked, disabled=is_disabled)
        if req.method == "DELETE":
            return MockHTTPResponse(204)
        return MockHTTPResponse(200, b"[]")

    client = mock_http(handler=handler)
    await check_blocked_users(
        HUB_URL, API_TOKEN, CLIENT_ID, CLIENT_SECRET, AUTH_URL, AUDIENCE, AUTHZ_URL
    )
    delete_calls = [c for c in client.calls if c.method == "DELETE"]
    if is_blocked or is_disabled:
        # 2 delete calls (server DELETE + user DELETE) if the user is blocked or disabled
        assert len(delete_calls) == 2
    else:
        # No delete calls if the user is not blocked nor disabled
        assert len(delete_calls) == 0


@pytest.mark.asyncio
async def test_check_blocked_mix_of_users(mock_http):
    app.users = [
        make_user("blocked_user"),
        make_user("ok_user"),
    ]

    def handler(req):
        if req.method == "POST":
            return _token_ok()
        if "/blocked_user/accounts" in req.url:
            return _identity(blocked=True)
        if "/ok_user/accounts" in req.url:
            return _identity(blocked=False)
        if req.method == "DELETE":
            return MockHTTPResponse(204)
        return MockHTTPResponse(200, b"[]")

    client = mock_http(handler=handler)
    await check_blocked_users(
        HUB_URL, API_TOKEN, CLIENT_ID, CLIENT_SECRET, AUTH_URL, AUDIENCE, AUTHZ_URL
    )
    delete_calls = [c for c in client.calls if c.method == "DELETE"]
    # Only blocked_user: server DELETE + user DELETE
    assert len(delete_calls) == 2
    assert all("blocked_user" in c.url for c in delete_calls)
