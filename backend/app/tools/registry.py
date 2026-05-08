"""Tool registry: aggregate all platform tools for agent construction."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from app.config import Settings
from app.tools.filesystem_bridge import _make_fs_tools
from app.tools.tavily_search import tavily_search


def get_platform_tools(
    settings: Settings, *, task_workspace: Path | None = None
) -> list[BaseTool]:
    """Return all platform tools available for agent construction.

    Filesystem tools are always included.  The Tavily search tool is included
    only when ``settings.tavily_api_key`` is configured.

    Args:
        settings: Application settings.
        task_workspace: Optional task-specific workspace directory. When provided,
            filesystem tools are scoped to this directory instead of the global
            ``settings.workspace_root``.
    """
    tools: list[BaseTool] = []

    workspace = task_workspace or settings.workspace_root
    read_file, write_file, list_files = _make_fs_tools(workspace)
    tools.extend([read_file, write_file, list_files])

    if settings.tavily_api_key:
        tools.append(tavily_search)

    return tools
