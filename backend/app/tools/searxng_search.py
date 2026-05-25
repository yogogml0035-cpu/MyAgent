"""SearXNG web search tool integration.

Calls a local SearXNG instance through its JSON search endpoint and exposes the
result as a LangChain tool. The tool returns a readable error string instead of
crashing the agent when the local search service is unavailable.
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from langchain_core.tools import tool

DEFAULT_SEARXNG_URL = "http://127.0.0.1:8181/"
SEARCH_TOOL_NAME = "searxng_search"
SEARCH_ERROR_PREFIX = "错误："
NO_RESULTS_TEXT = "未找到结果。"
ALLOWED_SEARCH_ENGINES = ("bing", "baidu")
DEFAULT_SEARCH_ENGINE = "bing"
SEARCH_RETRY_STATUS_CODES = {502, 503, 504}
SearchEngine = Literal["bing", "baidu"]


def create_searxng_search_tool(
    base_url: str,
    *,
    cache=None,
    task_id: str | None = None,
    ttl_seconds: int = 600,
    timeout_seconds: float = 15.0,
    max_calls_per_run: int | None = None,
):
    """Create a SearXNG search tool bound to the configured engine URL."""
    call_count = 0

    @tool(SEARCH_TOOL_NAME)
    def settings_searxng_search(
        query: str,
        *,
        max_results: int = 5,
        topic: str = "general",
        language: str = "auto",
        engine: SearchEngine = DEFAULT_SEARCH_ENGINE,
        trust_env: bool = False,
    ) -> str:
        """使用已配置的本地 SearXNG 搜索引擎进行联网搜索。

        参数：
            query: 搜索关键词。
            max_results: 返回结果上限（1-10，默认 5）。
            topic: SearXNG 分类，例如 ``"general"`` 或 ``"news"``。
            language: SearXNG 语言代码，或 ``"auto"`` 使用引擎默认设置。
            engine: 搜索引擎，只允许 ``"bing"`` 或 ``"baidu"``。
            trust_env: 是否信任系统代理等环境变量；默认关闭，遇到网络失败时可设为 true 重试。
        """
        normalized_query = " ".join(query.split())
        if not normalized_query:
            return f"{SEARCH_ERROR_PREFIX}搜索词不能为空。"
        normalized_engine = _normalize_engine(engine)
        if normalized_engine.startswith(SEARCH_ERROR_PREFIX):
            return normalized_engine

        nonlocal call_count
        if max_calls_per_run is not None and call_count >= max_calls_per_run:
            return (
                f"{SEARCH_ERROR_PREFIX}本次联网研究已达到搜索调用上限"
                f"（{max_calls_per_run} 次）。请基于已有搜索结果直接给出结论；"
                "如果证据不足，请明确说明不确定性，而不是继续搜索。"
            )
        call_count += 1

        cache_query = _cache_key(
            normalized_query,
            topic=topic,
            language=language,
            engine=normalized_engine,
            trust_env=trust_env,
        )
        if cache is not None and task_id and not _asks_for_refresh(normalized_query):
            cached = cache.get_fresh_tool_cache(
                task_id,
                tool_name=SEARCH_TOOL_NAME,
                query=cache_query,
            )
            if cached is not None:
                return (
                    f"[本会话缓存结果，生成时间 {cached.created_at}；如需最新结果，请明确要求刷新]\n"
                    f"{cached.result_text}"
                )
        result = _run_searxng_search(
            base_url,
            normalized_query,
            max_results=max_results,
            topic=topic,
            language=language,
            engine=normalized_engine,
            timeout_seconds=timeout_seconds,
            trust_env=trust_env,
        )
        if cache is not None and task_id and not result.startswith(SEARCH_ERROR_PREFIX):
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
    engine: SearchEngine = DEFAULT_SEARCH_ENGINE,
    trust_env: bool = False,
) -> str:
    """使用本地 SearXNG 搜索引擎进行联网搜索。

    参数：
        query: 搜索关键词。
        max_results: 返回结果上限（1-10，默认 5）。
        topic: SearXNG 分类，例如 ``"general"`` 或 ``"news"``。
        language: SearXNG 语言代码，或 ``"auto"`` 使用引擎默认设置。
        engine: 搜索引擎，只允许 ``"bing"`` 或 ``"baidu"``。
        trust_env: 是否信任系统代理等环境变量；默认关闭，遇到网络失败时可设为 true 重试。

    返回：
        格式化后的搜索结果，包含标题、链接和摘要；如果服务不可用或返回无效数据，
        则返回错误信息。
    """
    normalized_engine = _normalize_engine(engine)
    if normalized_engine.startswith(SEARCH_ERROR_PREFIX):
        return normalized_engine
    base_url = _get_base_url()
    return _run_searxng_search(
        base_url,
        " ".join(query.split()),
        max_results=max_results,
        topic=topic,
        language=language,
        engine=normalized_engine,
        timeout_seconds=15.0,
        trust_env=trust_env,
    )


def _run_searxng_search(
    base_url: str,
    query: str,
    *,
    max_results: int,
    topic: str,
    language: str,
    timeout_seconds: float,
    engine: str = DEFAULT_SEARCH_ENGINE,
    trust_env: bool = False,
) -> str:
    if not query:
        return f"{SEARCH_ERROR_PREFIX}搜索词不能为空。"
    normalized_engine = _normalize_engine(engine)
    if normalized_engine.startswith(SEARCH_ERROR_PREFIX):
        return normalized_engine

    try:
        payload = _request_searxng_payload(
            base_url,
            query,
            topic=topic,
            language=language,
            engine=normalized_engine,
            timeout_seconds=timeout_seconds,
            trust_env=trust_env,
        )
    except Exception as exc:
        return f"{SEARCH_ERROR_PREFIX}SearXNG 搜索失败 - {exc}"

    if not isinstance(payload, dict):
        return NO_RESULTS_TEXT

    direct_parts = _format_direct_results(payload)
    results = payload.get("results")
    limit = max(1, min(max_results, 10))
    formatted_parts: list[str] = []
    if isinstance(results, list):
        formatted_parts.extend(_format_result_items(results[:limit]))

    all_parts = [*direct_parts, *formatted_parts]
    if all_parts:
        return "\n\n".join(all_parts)

    unresponsive = _format_unresponsive_engines(payload)
    if unresponsive:
        return f"{SEARCH_ERROR_PREFIX}SearXNG 搜索无结果，上游引擎不可用：{unresponsive}"
    return NO_RESULTS_TEXT


def _request_searxng_payload(
    base_url: str,
    query: str,
    *,
    topic: str,
    language: str,
    engine: str,
    timeout_seconds: float,
    trust_env: bool,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = httpx.get(
                _search_endpoint(base_url),
                params=_search_params(
                    query,
                    topic=topic,
                    language=language,
                    engine=engine,
                ),
                headers={"Accept": "application/json"},
                timeout=timeout_seconds,
                trust_env=trust_env,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status_code = exc.response.status_code
            if status_code not in SEARCH_RETRY_STATUS_CODES or attempt > 0:
                raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt > 0:
                raise
        if attempt == 0:
            time.sleep(0.5)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("SearXNG request failed")


def _format_result_items(results: list[Any]) -> list[str]:
    formatted_parts: list[str] = []
    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = _string_value(item.get("title")) or "未命名"
        url = _string_value(item.get("url"))
        snippet = _string_value(item.get("content") or item.get("snippet"))
        metadata = _result_metadata(item)
        lines = [f"[{idx}] {title}"]
        if url:
            lines.append(f"    链接：{url}")
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
                formatted_parts.append(f"直接答案：{text}")

    infoboxes = payload.get("infoboxes")
    if isinstance(infoboxes, list):
        for infobox in infoboxes:
            if not isinstance(infobox, dict):
                continue
            title = _string_value(infobox.get("infobox") or infobox.get("title")) or "信息框"
            content = _string_value(infobox.get("content"))
            lines = [f"信息框：{title}"]
            if content:
                lines.append(f"    {content}")
            urls = infobox.get("urls")
            if isinstance(urls, list):
                for url_item in urls[:3]:
                    if not isinstance(url_item, dict):
                        continue
                    url = _string_value(url_item.get("url"))
                    if url:
                        label = _string_value(url_item.get("title")) or "来源"
                        lines.append(f"    {label}: {url}")
            formatted_parts.append("\n".join(lines))
    return formatted_parts


def _search_endpoint(base_url: str) -> str:
    normalized = base_url if base_url.endswith("/") else f"{base_url}/"
    return urljoin(normalized, "search")


def _search_params(
    query: str,
    *,
    topic: str,
    language: str,
    engine: str,
) -> dict[str, str]:
    params = {
        "q": query,
        "format": "json",
        "engines": engine,
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
        parts.append(f"发布时间：{published_at}")
    engines = item.get("engines") or item.get("engine")
    if isinstance(engines, list):
        engine_text = ", ".join(str(engine) for engine in engines if str(engine).strip())
    else:
        engine_text = _string_value(engines)
    if engine_text:
        parts.append(f"来源引擎：{engine_text}")
    return " | ".join(parts)


def _format_unresponsive_engines(payload: dict[str, Any]) -> str:
    entries = payload.get("unresponsive_engines")
    if not isinstance(entries, list):
        return ""
    parts: list[str] = []
    for entry in entries:
        if isinstance(entry, list) and entry:
            engine = _string_value(entry[0])
            reason = _string_value(entry[1]) if len(entry) > 1 else ""
        else:
            engine = _string_value(entry)
            reason = ""
        if engine and reason:
            parts.append(f"{engine}({reason})")
        elif engine:
            parts.append(engine)
    return ", ".join(parts)


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalize_engine(engine: str | None) -> str:
    normalized = (engine or DEFAULT_SEARCH_ENGINE).strip().lower()
    if normalized not in ALLOWED_SEARCH_ENGINES:
        allowed = ", ".join(ALLOWED_SEARCH_ENGINES)
        received = normalized or "<empty>"
        return f"{SEARCH_ERROR_PREFIX}只允许使用搜索引擎：{allowed}。收到：{received}"
    return normalized


def _cache_key(
    query: str,
    *,
    topic: str,
    language: str,
    engine: str,
    trust_env: bool,
) -> str:
    normalized_topic = _normalize_topic(topic)
    normalized_language = language.strip().lower() if language else "auto"
    if (
        normalized_topic == "general"
        and normalized_language == "auto"
        and engine == DEFAULT_SEARCH_ENGINE
        and not trust_env
    ):
        return query
    return (
        f"{query} [topic={normalized_topic}; language={normalized_language}; "
        f"engine={engine}; trust_env={str(trust_env).lower()}]"
    )


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
