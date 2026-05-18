"""SearXNG web search tool integration.

Calls a local SearXNG instance through its JSON search endpoint and exposes the
result as a LangChain tool. The tool returns a readable error string instead of
crashing the agent when the local search service is unavailable.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx
from langchain_core.tools import tool

DEFAULT_SEARXNG_URL = "http://127.0.0.1:8181/"
SEARCH_TOOL_NAME = "searxng_search"


def create_searxng_search_tool(
    base_url: str,
    *,
    cache=None,
    task_id: str | None = None,
    ttl_seconds: int = 600,
    timeout_seconds: float = 15.0,
):
    """Create a SearXNG search tool bound to the configured engine URL."""

    @tool(SEARCH_TOOL_NAME)
    def settings_searxng_search(
        query: str,
        *,
        max_results: int = 5,
        topic: str = "general",
        language: str = "auto",
    ) -> str:
        """Search the web using the configured local SearXNG engine.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return (1-10, default 5).
            topic: SearXNG category such as ``"general"`` or ``"news"``.
            language: SearXNG language code, or ``"auto"`` for engine default.
        """
        normalized_query = " ".join(query.split())
        if not normalized_query:
            return "Error: search query is empty."

        cache_query = _cache_key(normalized_query, topic=topic, language=language)
        if cache is not None and task_id and not _asks_for_refresh(normalized_query):
            cached = cache.get_fresh_tool_cache(
                task_id,
                tool_name=SEARCH_TOOL_NAME,
                query=cache_query,
            )
            if cached is not None:
                return (
                    f"[Cached within this conversation at {cached.created_at}; "
                    "ask to refresh for a new search]\n"
                    f"{cached.result_text}"
                )
        result = _run_searxng_search(
            base_url,
            normalized_query,
            max_results=max_results,
            topic=topic,
            language=language,
            timeout_seconds=timeout_seconds,
        )
        if cache is not None and task_id and not result.startswith("Error:"):
            cache.cache_tool_result(
                task_id,
                tool_name=SEARCH_TOOL_NAME,
                query=cache_query,
                result_text=result,
                ttl_seconds=ttl_seconds,
            )
        return result

    return settings_searxng_search


@tool(SEARCH_TOOL_NAME)
def searxng_search(
    query: str,
    *,
    max_results: int = 5,
    topic: str = "general",
    language: str = "auto",
) -> str:
    """Search the web using a local SearXNG engine.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (1-10, default 5).
        topic: SearXNG category such as ``"general"`` or ``"news"``.
        language: SearXNG language code, or ``"auto"`` for engine default.

    Returns:
        Formatted search results with title, URL, and snippet, or an error
        message if the SearXNG service is unavailable or returns invalid data.
    """
    base_url = _get_base_url()
    return _run_searxng_search(
        base_url,
        " ".join(query.split()),
        max_results=max_results,
        topic=topic,
        language=language,
        timeout_seconds=15.0,
    )


def _run_searxng_search(
    base_url: str,
    query: str,
    *,
    max_results: int,
    topic: str,
    language: str,
    timeout_seconds: float,
) -> str:
    if not query:
        return "Error: search query is empty."

    try:
        response = httpx.get(
            _search_endpoint(base_url),
            params=_search_params(query, topic=topic, language=language),
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return f"Error: SearXNG search failed - {exc}"

    if not isinstance(payload, dict):
        return "No results found."

    direct_parts = _format_direct_results(payload)
    results = payload.get("results")
    limit = max(1, min(max_results, 10))
    formatted_parts: list[str] = []
    if isinstance(results, list):
        formatted_parts.extend(_format_result_items(results[:limit]))

    all_parts = [*direct_parts, *formatted_parts]
    return "\n\n".join(all_parts) if all_parts else "No results found."


def _format_result_items(results: list[Any]) -> list[str]:
    formatted_parts: list[str] = []
    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = _string_value(item.get("title")) or "Untitled"
        url = _string_value(item.get("url"))
        snippet = _string_value(item.get("content") or item.get("snippet"))
        metadata = _result_metadata(item)
        lines = [f"[{idx}] {title}"]
        if url:
            lines.append(f"    URL: {url}")
        if metadata:
            lines.append(f"    {metadata}")
        if snippet:
            lines.append(f"    {snippet}")
        formatted_parts.append("\n".join(lines))
    return formatted_parts


def _format_direct_results(payload: dict[str, Any]) -> list[str]:
    formatted_parts: list[str] = []
    answers = payload.get("answers")
    if isinstance(answers, list):
        for answer in answers:
            text = _string_value(answer)
            if text:
                formatted_parts.append(f"Answer: {text}")

    infoboxes = payload.get("infoboxes")
    if isinstance(infoboxes, list):
        for infobox in infoboxes:
            if not isinstance(infobox, dict):
                continue
            title = _string_value(infobox.get("infobox") or infobox.get("title")) or "Infobox"
            content = _string_value(infobox.get("content"))
            lines = [f"Infobox: {title}"]
            if content:
                lines.append(f"    {content}")
            urls = infobox.get("urls")
            if isinstance(urls, list):
                for url_item in urls[:3]:
                    if not isinstance(url_item, dict):
                        continue
                    url = _string_value(url_item.get("url"))
                    if url:
                        label = _string_value(url_item.get("title")) or "Source"
                        lines.append(f"    {label}: {url}")
            formatted_parts.append("\n".join(lines))
    return formatted_parts


def _search_endpoint(base_url: str) -> str:
    normalized = base_url if base_url.endswith("/") else f"{base_url}/"
    return urljoin(normalized, "search")


def _search_params(query: str, *, topic: str, language: str) -> dict[str, str]:
    params = {
        "q": query,
        "format": "json",
        "categories": _normalize_topic(topic),
    }
    normalized_language = language.strip() if language else ""
    if normalized_language and normalized_language.lower() != "auto":
        params["language"] = normalized_language
    return params


def _normalize_topic(topic: str) -> str:
    normalized = topic.strip().lower() if topic else "general"
    if normalized in {"finance", "financial"}:
        return "general"
    return normalized or "general"


def _result_metadata(item: dict[str, Any]) -> str:
    parts: list[str] = []
    published_at = _string_value(item.get("publishedDate") or item.get("published_at"))
    if published_at:
        parts.append(f"Published: {published_at}")
    engines = item.get("engines") or item.get("engine")
    if isinstance(engines, list):
        engine_text = ", ".join(str(engine) for engine in engines if str(engine).strip())
    else:
        engine_text = _string_value(engines)
    if engine_text:
        parts.append(f"Engine: {engine_text}")
    return " | ".join(parts)


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _cache_key(query: str, *, topic: str, language: str) -> str:
    normalized_topic = _normalize_topic(topic)
    normalized_language = language.strip().lower() if language else "auto"
    if normalized_topic == "general" and normalized_language == "auto":
        return query
    return f"{query} [topic={normalized_topic}; language={normalized_language}]"


def _get_base_url() -> str:
    return os.getenv("MYAGENT_SEARXNG_URL") or DEFAULT_SEARXNG_URL


def _asks_for_refresh(query: str) -> bool:
    normalized = query.lower()
    markers = (
        "刷新",
        "重新查",
        "再查",
        "最新",
        "现在",
        "实时",
        "latest",
        "refresh",
        "current",
        "now",
    )
    return any(marker in normalized for marker in markers)
