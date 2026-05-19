from __future__ import annotations

from app.tools.searxng_search import _run_searxng_search


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_searxng_search_formats_infoboxes_when_regular_results_are_empty(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse(
            {
                "results": [],
                "answers": ["Direct answer"],
                "infoboxes": [
                    {
                        "infobox": "OpenAI",
                        "content": "Research organization",
                        "urls": [{"title": "Wikipedia", "url": "https://example.test/reference"}],
                    }
                ],
            }
        )

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    result = _run_searxng_search(
        "http://127.0.0.1:8181/",
        "OpenAI",
        max_results=5,
        topic="general",
        language="auto",
        timeout_seconds=1.0,
    )

    assert "直接答案：Direct answer" in result
    assert "信息框：OpenAI" in result
    assert "Wikipedia: https://example.test/reference" in result


def test_searxng_search_returns_error_string_when_request_fails(monkeypatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    result = _run_searxng_search(
        "http://127.0.0.1:8181/",
        "python",
        max_results=5,
        topic="general",
        language="auto",
        timeout_seconds=1.0,
    )

    assert result == "错误：SearXNG 搜索失败 - connection refused"
