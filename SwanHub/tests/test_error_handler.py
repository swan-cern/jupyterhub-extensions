from jupyterhub.handlers import pages
from swanhub.error_handler import ProxyErrorHandler


class _MockErrorHandler(ProxyErrorHandler):
    """Subclass so super() works inside ProxyErrorHandler.get; Tornado __init__ is skipped."""

    def __init__(self):
        self.rendered = None
        self.finished = None

    async def render_template(self, template, **kwargs):
        self.rendered = template
        return f"<html>{template}</html>"

    def finish(self, html):
        self.finished = html


class TestProxyErrorHandler:
    async def test_503_renders_unreachable_container_template(self):
        handler = _MockErrorHandler()
        await ProxyErrorHandler.get(handler, "503")
        assert handler.rendered == "unreachable_container.html"
        assert handler.finished is not None

    async def test_non_503_delegates_to_super(self, monkeypatch):
        super_calls = []
        monkeypatch.setattr(pages.ProxyErrorHandler, "get", lambda self, code: super_calls.append(code))

        handler = _MockErrorHandler()
        await ProxyErrorHandler.get(handler, "404")
        assert super_calls == ["404"]
