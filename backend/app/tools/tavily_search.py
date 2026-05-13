"""Tavily web search tool integration.

Wraps the tavily-python client as a LangChain ``@tool`` so agents can search
the web for current information.  If no API key is configured the tool returns
a human-readable error string instead of crashing.
"""

from __future__ import annotations

from langchain_core.tools import tool
from tavily import TavilyClient


def create_tavily_search_tool(api_key: str, *, cache=None, task_id: str | None = None, ttl_seconds: int = 600):
    """Create a Tavily search tool bound to the configured settings key."""

    @tool("tavily_search")
    def settings_tavily_search(query: str, *, max_results: int = 5, topic: str = "general") -> str:
        """Search the web for current information using the Tavily search API."""
        normalized_query = " ".join(query.split())
        if cache is not None and task_id and not _asks_for_refresh(normalized_query):
            cached = cache.get_fresh_tool_cache(
                task_id,
                tool_name="tavily_search",
                query=normalized_query,
            )
            if cached is not None:
                return (
                    f"[Cached within this conversation at {cached.created_at}; "
                    "ask to refresh for a new search]\n"
                    f"{cached.result_text}"
                )
        result = _run_tavily_search(api_key, normalized_query, max_results=max_results, topic=topic)
        if cache is not None and task_id and not result.startswith("Error:"):
            cache.cache_tool_result(
                task_id,
                tool_name="tavily_search",
                query=normalized_query,
                result_text=result,
                ttl_seconds=ttl_seconds,
            )
        return result

    return settings_tavily_search


@tool
def tavily_search(query: str, *, max_results: int = 5, topic: str = "general") -> str:
    """Search the web for current information using the Tavily search API.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (1-10, default 5).
        topic: Search topic — ``"general"`` or ``"news"``.

    Returns:
        Formatted search results with title, URL, and snippet, or an error
        message if the API key is not configured or the request fails.
    """
    api_key = _get_api_key()
    if not api_key:
        return (
            "Error: TAVILY_API_KEY is not configured. "
            "Set the TAVILY_API_KEY environment variable to enable web search."
        )

    return _run_tavily_search(api_key, query, max_results=max_results, topic=topic)


def _run_tavily_search(api_key: str, query: str, *, max_results: int, topic: str) -> str:
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max(1, min(max_results, 10)),
            topic=topic,
        )
    except Exception as exc:
        return f"Error: Tavily search failed — {exc}"

    results = response.get("results", [])
    if not results:
        return "No results found."

    formatted_parts: list[str] = []
    for idx, item in enumerate(results, start=1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        snippet = item.get("content", "")
        formatted_parts.append(f"[{idx}] {title}\n    URL: {url}\n    {snippet}")

    return "\n\n".join(formatted_parts)


def _get_api_key() -> str | None:
    # Lazy read so runtime env changes are picked up without restart.
    import os

    return os.getenv("TAVILY_API_KEY") or None


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
