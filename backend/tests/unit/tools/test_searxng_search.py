from __future__ import annotations

import httpx
import pytest

from app.tools.searxng_search import _run_searxng_search, searxng_search


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_searxng_search_formats_infoboxes_when_regular_results_are_empty(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get(*args, **kwargs):
        captured["params"] = kwargs["params"]
        captured["trust_env"] = kwargs["trust_env"]
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
    assert captured["params"] == {
        "q": "OpenAI",
        "format": "json",
        "engines": "bing",
    }
    assert captured["trust_env"] is False


def test_searxng_search_allows_trusting_environment_proxy(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get(*args, **kwargs):
        captured["trust_env"] = kwargs["trust_env"]
        return FakeResponse({"results": []})

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    result = searxng_search.invoke(
        {"query": "OpenAI", "engine": "bing", "trust_env": True}
    )

    assert captured["trust_env"] is True
    assert result == "未找到结果。"


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


def test_searxng_search_retries_transient_bad_gateway(monkeypatch):
    calls: list[int] = []

    def fake_get(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            request = httpx.Request("GET", "http://127.0.0.1:8181/search")
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError("bad gateway", request=request, response=response)
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "OpenAI",
                        "url": "https://openai.com/",
                        "content": "Research lab",
                        "engine": "bing",
                    }
                ]
            }
        )

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)
    monkeypatch.setattr("app.tools.searxng_search.time.sleep", lambda _seconds: None)

    result = _run_searxng_search(
        "http://127.0.0.1:8181/",
        "OpenAI",
        max_results=5,
        topic="general",
        language="auto",
        timeout_seconds=1.0,
    )

    assert len(calls) == 2
    assert "https://openai.com/" in result


def test_searxng_search_reports_unresponsive_engine_when_results_are_empty(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({"results": [], "unresponsive_engines": [["bing", "timeout"]]})

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    result = _run_searxng_search(
        "http://127.0.0.1:8181/",
        "OpenAI",
        max_results=5,
        topic="general",
        language="auto",
        timeout_seconds=1.0,
    )

    assert result == "错误：SearXNG 搜索无结果，上游引擎不可用：bing(timeout)"


def test_searxng_search_allows_model_to_choose_bing_or_baidu(monkeypatch):
    calls: list[object] = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs["params"])
        return FakeResponse({"results": []})

    monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)

    with pytest.raises(Exception, match="Input should be 'bing' or 'baidu'"):
        searxng_search.invoke({"query": "OpenAI", "engine": "google"})
    valid = searxng_search.invoke({"query": "OpenAI", "engine": "baidu"})

    assert calls == [
        {
            "q": "OpenAI",
            "format": "json",
            "engines": "baidu",
        }
    ]
    assert valid == "未找到结果。"
