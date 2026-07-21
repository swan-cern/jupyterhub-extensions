import json
from datetime import UTC, datetime, timedelta

import pytest
from swanculler import app
from swanculler.app import check_blocked_users, cull_idle, format_td, parse_date

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ago(minutes):
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _server_model(*, inactive_minutes, age_minutes=60, pending=None, ready=True):
    return {
        "url": "/user/x/",
        "ready": ready,
        "pending": pending,
        "last_activity": _ago(inactive_minutes),
        "started": _ago(age_minutes),
    }


def _user_model(name, *, servers=None, inactive_minutes=5, created_minutes=60):
    return {
        "name": name,
        "servers": servers if servers is not None else {},
        "last_activity": _ago(inactive_minutes),
        "created": _ago(created_minutes),
        "server": None,
    }


def make_user(name):
    now = datetime.now(UTC).isoformat()
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
    def _create(handler):
        client = MockHTTPClient(handler=handler)
        monkeypatch.setattr("swanculler.app.AsyncHTTPClient", lambda: client)
        return client

    return _create

# ---------------------------------------------------------------------------
# TestCheckBlockedUsers
# ---------------------------------------------------------------------------

class TestCheckBlockedUsers:
    @pytest.mark.parametrize("is_blocked", (True, False))
    @pytest.mark.parametrize("is_disabled", (True, False))
    async def test_blocked_or_disabled_user_is_culled(self, mock_http, is_blocked, is_disabled):
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
            assert len(delete_calls) == 2
        else:
            assert len(delete_calls) == 0

    async def test_only_blocked_user_is_culled_in_mixed_list(self, mock_http):
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
        assert len(delete_calls) == 2
        assert all("blocked_user" in c.url for c in delete_calls)


# ---------------------------------------------------------------------------
# TestParseDate
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_with_timezone_is_preserved(self):
        dt = parse_date("2024-06-01T10:00:00+00:00")
        assert dt.tzinfo is not None
        assert dt.year == 2024

    def test_without_timezone_defaults_to_utc(self):
        dt = parse_date("2024-06-01T10:00:00")
        assert dt.tzinfo == UTC


# ---------------------------------------------------------------------------
# TestFormatTd
# ---------------------------------------------------------------------------

class TestFormatTd:
    def test_none_returns_unknown(self):
        assert format_td(None) == "unknown"

    def test_string_passes_through(self):
        assert format_td("5 minutes") == "5 minutes"

    def test_formats_as_hms(self):
        assert format_td(timedelta(hours=2, minutes=5, seconds=30)) == "02:05:30"

    def test_zero_timedelta(self):
        assert format_td(timedelta(0)) == "00:00:00"


# ---------------------------------------------------------------------------
# TestCullIdle
# ---------------------------------------------------------------------------

class TestCullIdle:
    INACTIVE_LIMIT = 1800  # 30 minutes in seconds

    @pytest.fixture(autouse=True)
    def _patch_check_ticket(self, monkeypatch):
        monkeypatch.setattr("swanculler.app.check_ticket", lambda _: None)

    def _handler(self, users, *, deleted=None, slow_servers=None):
        """Build a handler for cull_idle HTTP calls.

        GET /users → users JSON.
        DELETE     → 204, or 202 for usernames in slow_servers.
        Appends ("server"|"user", name) tuples to deleted when provided.
        """
        slow_servers = slow_servers or set()

        def handler(req):
            if req.method == "GET":
                return MockHTTPResponse(200, json.dumps(users).encode())
            if req.method == "DELETE":
                is_server = req.url.endswith("/server") or "/servers/" in req.url
                username = req.url.split("/users/")[1].split("/")[0]
                if deleted is not None:
                    deleted.append(("server" if is_server else "user", username))
                return MockHTTPResponse(202 if username in slow_servers else 204)
            return MockHTTPResponse(200, b"[]")

        return handler

    async def test_inactive_server_is_culled(self, mock_http):
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=60)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert ("server", "alice") in deleted

    async def test_active_server_is_not_culled(self, mock_http):
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=5)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert deleted == []

    async def test_pending_server_is_not_culled(self, mock_http):
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=60, pending="spawn")})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert deleted == []

    async def test_not_ready_server_is_not_culled(self, mock_http):
        server = _server_model(inactive_minutes=60, ready=False)
        server["url"] = ""
        user = _user_model("alice", servers={"": server})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert deleted == []

    async def test_max_age_culls_active_server(self, mock_http):
        # Server recently used but older than max_age → culled regardless
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=5, age_minutes=120)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, max_age=3600)

        assert ("server", "alice") in deleted

    async def test_max_age_keeps_young_active_server(self, mock_http):
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=5, age_minutes=30)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, max_age=3600)

        assert deleted == []

    async def test_no_last_activity_falls_back_to_started(self, mock_http):
        # When last_activity is None, idleness is measured from the start time
        server = _server_model(inactive_minutes=5, age_minutes=60)
        server["last_activity"] = None
        user = _user_model("alice", servers={"": server})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        # age = 60 min = 3600 s > 1800 s inactive_limit → culled
        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert ("server", "alice") in deleted

    async def test_cull_users_removes_inactive_user(self, mock_http):
        user = _user_model("alice", servers={}, inactive_minutes=60)
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, cull_users=True)

        assert ("user", "alice") in deleted

    async def test_cull_users_keeps_active_user(self, mock_http):
        user = _user_model("alice", servers={}, inactive_minutes=5)
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, cull_users=True)

        assert deleted == []

    async def test_user_with_running_server_not_culled(self, mock_http):
        # User has an active server; hub won't delete users with live servers
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=5)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, cull_users=True)

        assert ("user", "alice") not in deleted

    async def test_slow_stopping_server_blocks_user_cull(self, mock_http):
        # 202 means the server is still shutting down; user must not be deleted yet
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=60)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted, slow_servers={"alice"}))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, cull_users=True)

        assert ("server", "alice") in deleted   # DELETE was issued
        assert ("user", "alice") not in deleted  # but user not removed yet

    async def test_no_started_field_still_culls_by_inactivity(self, mock_http):
        server = _server_model(inactive_minutes=60)
        del server["started"]
        user = _user_model("alice", servers={"": server})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        assert ("server", "alice") in deleted

    async def test_no_started_field_skips_max_age_check(self, mock_http):
        # Without a start time age is None, so max_age cannot trigger culling
        server = _server_model(inactive_minutes=5)
        del server["started"]
        user = _user_model("alice", servers={"": server})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, max_age=1)

        assert deleted == []

    async def test_no_concurrency_limit_still_culls(self, mock_http):
        user = _user_model("alice", servers={"": _server_model(inactive_minutes=60)})
        deleted = []
        mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, concurrency=0)

        assert ("server", "alice") in deleted

    async def test_named_server_uses_servers_url(self, mock_http):
        user = _user_model("alice", servers={"gpu": _server_model(inactive_minutes=60)})
        deleted = []
        client = mock_http(handler=self._handler([user], deleted=deleted))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT)

        delete_calls = [c for c in client.calls if c.method == "DELETE"]
        assert len(delete_calls) == 1
        assert "/users/alice/servers/gpu" in delete_calls[0].url

    async def test_disable_hooks_skips_check_ticket(self, mock_http, monkeypatch):
        ticket_calls = []
        monkeypatch.setattr("swanculler.app.check_ticket", lambda name: ticket_calls.append(name))

        user = _user_model("alice", servers={"": _server_model(inactive_minutes=5)})
        mock_http(handler=self._handler([user]))

        await cull_idle(HUB_URL, api_token=API_TOKEN, inactive_limit=self.INACTIVE_LIMIT, disable_hooks=True)

        assert ticket_calls == []
