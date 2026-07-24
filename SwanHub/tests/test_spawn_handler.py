import pytest

from swanhub.handlers_configs import SpawnHandlersConfigs
from swanhub.spawn_handler import SpawnHandler, sentry_set_spawn_tags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockUser:
    name = "alice"


class _MockHandler:
    """Minimal stand-in for SpawnHandler — only request.files and _log_metric are accessed."""
    class request:
        files = {}

    def __init__(self):
        self.logged_metrics = []

    def _log_metric(self, user, host, metric, value):
        self.logged_metrics.append((metric, value))


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
    yield SpawnHandlersConfigs.instance()
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
# TestLogSpawnMetrics
# ---------------------------------------------------------------------------

class TestLogSpawnMetrics:
    @pytest.fixture(autouse=True)
    def _no_sentry(self, monkeypatch):
        self.sentry_captures = []
        monkeypatch.setattr(
            "swanhub.spawn_handler.sentry_sdk.capture_exception",
            lambda e: self.sentry_captures.append(e),
        )

    def _run(self, options, duration=1.0, exception=None):
        handler = _MockHandler()
        SpawnHandler._log_spawn_metrics(handler, _MockUser(), options, duration, exception)
        return handler.logged_metrics

    def test_success_logs_exception_class_none(self):
        metrics = self._run({"lcg": "LCG_105"})
        assert any(k.endswith("exception_class") and v == "None" for k, v in metrics)

    def test_success_logs_duration(self):
        metrics = self._run({"lcg": "LCG_105"}, duration=42.5)
        assert any(k.endswith("duration_sec") and v == 42.5 for k, v in metrics)

    def test_success_does_not_call_sentry(self):
        self._run({"lcg": "LCG_105"})
        assert self.sentry_captures == []

    def test_failure_logs_exception_class(self):
        exc = ValueError("bad option")
        metrics = self._run({}, exception=exc)
        assert any(k.endswith("exception_class") and v == "ValueError" for k, v in metrics)

    def test_failure_logs_exception_message(self):
        exc = ValueError("bad option")
        metrics = self._run({}, exception=exc)
        assert any(k.endswith("exception_message") and v == "bad option" for k, v in metrics)

    def test_failure_calls_sentry_capture(self):
        exc = RuntimeError("spawn failed")
        self._run({}, exception=exc)
        assert self.sentry_captures == [exc]

    def test_scriptenv_set_when_value_present(self):
        metrics = self._run({"scriptenv": "#!/bin/bash"})
        assert ("spawn_form.scriptenv", "set") in metrics

    def test_scriptenv_not_set_when_empty(self):
        metrics = self._run({"scriptenv": ""})
        assert ("spawn_form.scriptenv", "not_set") in metrics

    def test_slash_in_value_replaced_by_underscore(self):
        metrics = self._run({"lcg": "LCG/105"})
        assert ("spawn_form.lcg", "LCG_105") in metrics

    def test_spawn_context_key_uses_lcg_and_cluster(self):
        metrics = self._run({"lcg": "LCG_105", "clusters": "k8s"})
        assert any("LCG_105.k8s" in k for k, _ in metrics)

    def test_spawn_context_key_defaults_when_options_absent(self):
        metrics = self._run({})
        assert any("CustomEnv.none" in k for k, _ in metrics)


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
