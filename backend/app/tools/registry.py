"""Tool registry: aggregate all platform tools for agent construction."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.config import Settings
from app.tools.filesystem_bridge import _make_fs_tools
from app.tools.tavily_search import tavily_search


def get_platform_tools(settings: Settings) -> list[BaseTool]:
    """Return all platform tools available for agent construction.

    Filesystem tools are always included.  The Tavily search tool is included
    only when ``settings.tavily_api_key`` is configured.
    """
    tools: list[BaseTool] = []

    read_file, write_file, list_files = _make_fs_tools(settings.workspace_root)
    tools.extend([read_file, write_file, list_files])

    if settings.tavily_api_key:
        tools.append(tavily_search)

    return tools
