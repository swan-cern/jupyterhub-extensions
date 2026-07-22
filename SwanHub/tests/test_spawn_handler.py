import pytest

from swanhub.handlers_configs import SpawnHandlersConfigs
from swanhub.spawn_handler import SpawnHandler, sentry_set_spawn_tags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockHandler:
    """Minimal stand-in for SpawnHandler — only request.files is accessed."""
    class request:
        files = {}


def _validate(configs, raw_options, files=None):
    """Call _validate_mandatory_options without a real Tornado handler."""
    handler = _MockHandler()
    if files is not None:
        handler.request.files = files
    return SpawnHandler._validate_mandatory_options(handler, configs, raw_options)


def _b(value):
    """Encode a string to bytes, as Tornado passes body arguments."""
    return [value.encode()]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def configs():
    SpawnHandlersConfigs.clear_instance()
    instance = SpawnHandlersConfigs.instance()
    yield instance
    SpawnHandlersConfigs.clear_instance()


# ---------------------------------------------------------------------------
# TestValidateMandatoryOptions
# ---------------------------------------------------------------------------

class TestValidateMandatoryOptions:
    def test_empty_options_returns_no_error(self, configs):
        error, decoded = _validate(configs, {})
        assert error is None
        assert decoded == {}

    def test_valid_lcg_source_accepted(self, configs):
        error, _ = _validate(configs, {"software_source": _b("lcg")})
        assert error is None

    def test_valid_customenv_source_accepted(self, configs):
        error, _ = _validate(configs, {"software_source": _b("customenv")})
        assert error is None

    def test_invalid_software_source_returns_error(self, configs):
        error, _ = _validate(configs, {"software_source": _b("unknown")})
        assert error is not None
        assert "unknown" in error

    def test_tn_request_rejected_when_tn_disabled(self, configs):
        configs.tn_enabled = False
        error, _ = _validate(configs, {"use-tn": _b("true")})
        assert error is not None

    def test_tn_disabled_request_rejected_when_tn_enabled(self, configs):
        configs.tn_enabled = True
        error, _ = _validate(configs, {"use-tn": _b("false")})
        assert error is not None

    def test_tn_enabled_matches_deployment(self, configs):
        configs.tn_enabled = True
        error, _ = _validate(configs, {"use-tn": _b("true")})
        assert error is None

    def test_tn_disabled_matches_deployment(self, configs):
        configs.tn_enabled = False
        error, _ = _validate(configs, {"use-tn": _b("false")})
        assert error is None

    def test_bytes_are_decoded_to_strings(self, configs):
        _, decoded = _validate(configs, {"lcg": _b("LCG_105")})
        assert decoded["lcg"] == ["LCG_105"]

    def test_files_added_with_file_suffix(self, configs):
        fake_file = object()
        _, decoded = _validate(configs, {}, files={"script": [fake_file]})
        assert decoded["script_file"] == [fake_file]


# ---------------------------------------------------------------------------
# TestSentrySetSpawnTags
# ---------------------------------------------------------------------------

class TestSentrySetSpawnTags:
    def test_non_empty_values_are_set_as_tags(self, monkeypatch):
        tags = {}
        monkeypatch.setattr("swanhub.spawn_handler.sentry_sdk.set_tag", lambda k, v: tags.update({k: v}))

        sentry_set_spawn_tags({"lcg": "LCG_105", "clusters": "none"})

        assert tags == {"spawn_form.lcg": "LCG_105", "spawn_form.clusters": "none"}

    def test_empty_values_are_skipped(self, monkeypatch):
        tags = {}
        monkeypatch.setattr("swanhub.spawn_handler.sentry_sdk.set_tag", lambda k, v: tags.update({k: v}))

        sentry_set_spawn_tags({"lcg": "LCG_105", "file": ""})

        assert "spawn_form.file" not in tags
