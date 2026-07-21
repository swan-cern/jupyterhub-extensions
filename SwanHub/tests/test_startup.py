import os
import shutil
import subprocess
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests
from jupyterhub import orm
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

HUB_URL = "http://127.0.0.1:18000"
ADMIN_TOKEN = "test-admin-token"
OPTIONS_FORM_CONFIG = Path(__file__).parents[2] / "SwanSpawner" / "options_form_config.json"

# ---------------------------------------------------------------------------
# User population — controls what gets inserted into the DB before hub start
# ---------------------------------------------------------------------------

REGULAR_USER_COUNT = 300
ADMIN_USERS = ["admin_alice", "admin_bob", "admin_chloe", "admin_donald"]
# Subset of regular users that had an active session when the hub last shut down.
# On restart, the hub should detect the session is no longer running and reconcile.
USERS_WITH_PRIOR_SESSION = [f"user_{i:03d}" for i in range(10)]

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
def prepopulated_db(hub_dir):
    db_path = hub_dir / "jupyterhub.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    orm.Base.metadata.create_all(engine)
    with Session(engine) as session:
        for name in _regular_users:
            user = orm.User(name=name)
            session.add(user)
            if name in USERS_WITH_PRIOR_SESSION:
                # Simulate a session that was running when the hub last shut down.
                # The hub will call poll() on restart, find PID 99999 is gone, and
                # mark the session as stopped — this exercises init_spawners().
                session.add(orm.Spawner(
                    user=user,
                    name="",
                    state={"pid": 99999},
                    started=datetime.now(UTC),
                    last_activity=datetime.now(UTC),
                    user_options={},
                ))
        for name in ADMIN_USERS:
            session.add(orm.User(name=name, admin=True))
        session.commit()
    engine.dispose()
    return db_path


@pytest.fixture(scope="module")
def hub_config(hub_dir, prepopulated_db):
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
        c.LocalSwanSpawner.options_form_config = '{OPTIONS_FORM_CONFIG}'

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

    deadline = time.monotonic() + 60
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
        raise RuntimeError(f"Hub did not start within 60s\n{output}")

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
