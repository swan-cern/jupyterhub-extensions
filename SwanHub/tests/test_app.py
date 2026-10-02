import datetime as _real_datetime

import pytest
import swanhub.app as app_module
from jupyterhub import app
from jupyterhub.apihandlers import users
from jupyterhub.handlers import pages
from swanhub.app import SWAN
from swanhub.error_handler import ProxyErrorHandler
from swanhub.spawn_handler import SpawnHandler
from swanhub.userapi_handler import SelfAPIHandler

SWAN_TEMPLATES = "/swan/templates"
DEFAULT_TEMPLATES = "/default/templates"


class _MockSWAN(SWAN):
    """Subclass so super() resolves correctly; JupyterHub __init__ is skipped."""

    def __init__(self):
        self.template_vars = {}
        self.template_paths = []
        self.handlers = []

    def _template_paths_default(self):
        return [DEFAULT_TEMPLATES]


def _fake_datetime(month):
    """Return a fake datetime module where date.today() returns the given month."""
    class _date:
        @staticmethod
        def today():
            return _real_datetime.date(2024, month, 1)

    class _datetime:
        @staticmethod
        def now():
            class _now:
                year = 2024
            return _now()

    class _module:
        date = _date
        datetime = _datetime

    return _module()


# ---------------------------------------------------------------------------
# TestInitHandlers
# ---------------------------------------------------------------------------

class TestInitHandlers:
    @pytest.fixture(autouse=True)
    def _no_super(self, monkeypatch):
        monkeypatch.setattr(app.JupyterHub, "init_handlers", lambda self: None)

    def test_spawn_handler_replaced(self):
        swan = _MockSWAN()
        swan.handlers = [("/spawn", pages.SpawnHandler)]
        swan.init_handlers()
        assert swan.handlers[0][1] is SpawnHandler

    def test_proxy_error_handler_replaced(self):
        swan = _MockSWAN()
        swan.handlers = [("/error", pages.ProxyErrorHandler)]
        swan.init_handlers()
        assert swan.handlers[0][1] is ProxyErrorHandler

    def test_self_api_handler_replaced(self):
        swan = _MockSWAN()
        swan.handlers = [("/api/user", users.SelfAPIHandler)]
        swan.init_handlers()
        assert swan.handlers[0][1] is SelfAPIHandler

    def test_unrecognised_handler_unchanged(self):
        class _Other:
            pass

        swan = _MockSWAN()
        swan.handlers = [("/other", _Other)]
        swan.init_handlers()
        assert swan.handlers[0][1] is _Other

    def test_tuple_extra_elements_preserved(self):
        kwargs = {"key": "val"}
        swan = _MockSWAN()
        swan.handlers = [("/spawn", pages.SpawnHandler, kwargs)]
        swan.init_handlers()
        assert len(swan.handlers[0]) == 3
        assert swan.handlers[0][2] is kwargs


# ---------------------------------------------------------------------------
# TestInitTornadoSettings
# ---------------------------------------------------------------------------

class TestInitTornadoSettings:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        monkeypatch.setattr(app.JupyterHub, "init_tornado_settings", lambda self: None)
        monkeypatch.setattr("swanhub.app.get_templates", lambda: SWAN_TEMPLATES)

    def _make_swan(self, template_paths=None):
        swan = _MockSWAN()
        swan.template_paths = list(template_paths) if template_paths is not None else [DEFAULT_TEMPLATES]
        return swan

    def test_december_uses_christmas_logo(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(12))
        swan = self._make_swan()
        swan.init_tornado_settings()
        assert swan.template_vars["swan_logo_filename"] == "swan_letters_christmas.png"

    def test_non_december_uses_regular_logo(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(6))
        swan = self._make_swan()
        swan.init_tornado_settings()
        assert swan.template_vars["swan_logo_filename"] == "logo_swan_letters.png"

    def test_current_year_is_set(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(6))
        swan = self._make_swan()
        swan.init_tornado_settings()
        assert swan.template_vars["current_year"] == 2024

    def test_swan_templates_added_to_path(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(6))
        swan = self._make_swan(template_paths=[])
        swan.init_tornado_settings()
        assert SWAN_TEMPLATES in swan.template_paths

    def test_swan_templates_not_added_twice(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(6))
        swan = self._make_swan(template_paths=[SWAN_TEMPLATES])
        swan.init_tornado_settings()
        assert swan.template_paths.count(SWAN_TEMPLATES) == 1

    def test_default_path_removed_when_swan_path_added(self, monkeypatch):
        monkeypatch.setattr(app_module, "datetime", _fake_datetime(6))
        swan = self._make_swan(template_paths=[DEFAULT_TEMPLATES])
        swan.init_tornado_settings()
        assert DEFAULT_TEMPLATES not in swan.template_paths
        assert SWAN_TEMPLATES in swan.template_paths
