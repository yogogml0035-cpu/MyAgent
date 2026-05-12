"""Tool registry: aggregate all platform tools for agent construction."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.config import Settings
from app.tools.tavily_search import create_tavily_search_tool


def get_platform_tools(settings: Settings) -> list[BaseTool]:
    """Return platform-specific tools beyond the deepagents built-in suite.

    deepagents auto-injects ``ls``, ``read_file``, ``write_file``, ``edit_file``,
    ``glob``, ``grep`` via ``FilesystemMiddleware`` — those are configured through
    the ``backend`` parameter (see ``agent/factory.py``).  This function only
    returns additional tools that deepagents does not provide natively.

    The Tavily search tool is included only when
    ``settings.tavily_api_key`` is configured.
    """
    tools: list[BaseTool] = []

    if settings.tavily_api_key:
        tools.append(create_tavily_search_tool(settings.tavily_api_key))

    return tools
