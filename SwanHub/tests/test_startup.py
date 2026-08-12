import os
import shutil
import subprocess
import textwrap
import time
from datetime import UTC, datetime

import pytest
import requests
from jupyterhub import orm
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

HUB_URL = "http://127.0.0.1:18000"
ADMIN_TOKEN = "test-admin-token"

# ---------------------------------------------------------------------------
# User population — controls what gets inserted into the DB before hub start
# ---------------------------------------------------------------------------

REGULAR_USER_COUNT = 300
ADMIN_USERS = ["admin_alice", "admin_bob", "admin_chloe", "admin_donald"]
# Subset of regular users that had an active session when the hub last shut down.
# On restart, the hub should detect the session is no longer running and reconcile.
USERS_WITH_PRIOR_SESSION = [f"user_{i:03d}" for i in range(30)]

_regular_users = [f"user_{i:03d}" for i in range(REGULAR_USER_COUNT)]
ALL_USERS = _regular_users + ADMIN_USERS

pytestmark = pytest.mark.integration

if shutil.which("configurable-http-proxy") is None:
    pytest.skip(
        "configurable-http-proxy not installed — run: npm install --prefix ~/.local configurable-http-proxy",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def hub_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("hub")


@pytest.fixture(scope="module")
def options_form_config(hub_dir):
    """Generate a large synthetic YAML to make the event-loop-starvation bug detectable.

    init_spawners() creates a Python spawner object for each prior-session user,
    calling SwanSpawner.__init__(). The bug (parsing YAML synchronously in __init__)
    blocks the event loop for ~1.4 s per spawner on this machine. With 30 prior-session
    spawners that adds ~42 s of blocking on top of the ~7 s clean startup, pushing the
    hub past the 15 s startup timeout. The file is written to a temp dir and never
    committed to the repo.
    """
    path = hub_dir / "options_form_config_test.yaml"
    path.write_text(
        "padding:\n" + "".join(f"  key_{i:05d}: {'x' * 80}\n" for i in range(20_000))
    )
    return path


@pytest.fixture(scope="module")
def prepopulated_db(hub_dir):
    db_path = hub_dir / "jupyterhub.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    orm.Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Pass 1: create all user accounts
        users = {}
        for name in _regular_users:
            users[name] = orm.User(name=name)
            session.add(users[name])
        for name in ADMIN_USERS:
            session.add(orm.User(name=name, admin=True))

        # Pass 2: give a subset of users a "running" session from the previous hub
        # lifecycle. init_spawners() only processes spawners where server IS NOT NULL,
        # so a linked orm.Server is required to make the hub create a spawner Python
        # object (calling __init__) and then poll() to discover the process is gone.
        for i, name in enumerate(USERS_WITH_PRIOR_SESSION):
            server = orm.Server(
                proto="http",
                ip="127.0.0.1",
                port=28000 + i,
                base_url=f"/user/{name}/",
                cookie_name="username-localhost",
            )
            session.add(server)
            session.flush()
            session.add(orm.Spawner(
                user=users[name],
                name="",
                state={"pid": 99999},
                started=datetime.now(UTC),
                last_activity=datetime.now(UTC),
                user_options={},
                server=server,
            ))
        session.commit()
    engine.dispose()
    return db_path


@pytest.fixture(scope="module")
def hub_config(hub_dir, prepopulated_db, options_form_config):
    config = textwrap.dedent(f"""\
        c.JupyterHub.ip = '127.0.0.1'
        c.JupyterHub.port = 18000
        c.JupyterHub.cookie_secret_file = '{hub_dir}/jupyterhub_cookie_secret'

        c.JupyterHub.authenticator_class = 'keycloakauthenticator.auth.KeyCloakAuthenticator'
        c.KeyCloakAuthenticator.oidc_issuer = 'http://127.0.0.1:19999/fake'
        c.KeyCloakAuthenticator.username_claim = 'preferred_username'
        c.KeyCloakAuthenticator.oauth_callback_url = '{HUB_URL}/hub/oauth_callback'
        c.KeyCloakAuthenticator.allowed_roles = []

        c.JupyterHub.spawner_class = 'swanspawner.localswanspawner.LocalSwanSpawner'
        c.LocalSwanSpawner.options_form_config = '{options_form_config}'

        # Without this, JupyterHub falls back to serving requests after 10s even
        # if init_spawners hasn't finished. Setting it high forces the hub to wait
        # for all spawner objects to be created, so a slow __init__ (e.g. blocking
        # I/O on every spawner instance) delays the health endpoint and is caught
        # by this test's startup timeout.
        c.JupyterHub.init_spawners_timeout = 300

        c.JupyterHub.db_url = 'sqlite:///{prepopulated_db}'

        c.JupyterHub.services = [{{
            'name': 'test',
            'api_token': '{ADMIN_TOKEN}',
        }}]
        c.JupyterHub.load_roles = [{{
            'name': 'test-service-admin',
            'scopes': ['admin:users', 'read:users'],
            'services': ['test'],
        }}]
    """)
    config_path = hub_dir / "jupyterhub_config.py"
    config_path.write_text(config)
    return config_path


@pytest.fixture(scope="module")
def hub(hub_config):
    env = {
        **os.environ,
        "JUPYTERHUB_CRYPT_KEY": "0" * 64,
        "SWANHUB_ENV": "dev",
    }
    proc = subprocess.Popen(
        ["swanhub", "-f", str(hub_config)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{HUB_URL}/hub/health", timeout=2).status_code == 200:
                break
        except requests.ConnectionError:
            pass
        time.sleep(1)
    else:
        proc.kill()
        output = proc.stdout.read().decode()
        raise RuntimeError(f"Hub did not start within 15s\n{output}")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHubStartup:
    def test_health(self, hub):
        r = requests.get(f"{HUB_URL}/hub/health")
        assert r.status_code == 200

    def _get_all_users(self):
        users = []
        offset = 0
        while True:
            r = requests.get(
                f"{HUB_URL}/hub/api/users",
                headers={"Authorization": f"token {ADMIN_TOKEN}"},
                params={"offset": offset, "limit": 100},
            )
            assert r.status_code == 200
            page = r.json()
            users.extend(page)
            if len(page) < 100:
                break
            offset += 100
        return users

    def test_all_users_loaded(self, hub):
        names = {u["name"] for u in self._get_all_users()}
        assert names == set(ALL_USERS)

    def test_admin_users_recognized(self, hub):
        admins = {u["name"] for u in self._get_all_users() if u["admin"]}
        assert admins == set(ADMIN_USERS)

    def test_prior_sessions_reconciled(self, hub):
        """Hub should detect that prior sessions are no longer running on restart."""
        for name in USERS_WITH_PRIOR_SESSION:
            r = requests.get(
                f"{HUB_URL}/hub/api/users/{name}",
                headers={"Authorization": f"token {ADMIN_TOKEN}"},
            )
            assert r.status_code == 200
            # After reconciliation the hub clears the dead session — no active servers
            # should be reported (key absent or empty dict).
            assert not r.json().get("servers")
