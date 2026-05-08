"""Tavily web search tool integration.

Wraps the tavily-python client as a LangChain ``@tool`` so agents can search
the web for current information.  If no API key is configured the tool returns
a human-readable error string instead of crashing.
"""

from __future__ import annotations

from langchain_core.tools import tool
from tavily import TavilyClient


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
