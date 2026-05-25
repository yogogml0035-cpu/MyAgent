"""Tool registry: aggregate all platform tools for agent construction."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.config import Settings
from app.execution.resources import create_resource_tools
from app.tools.searxng_search import create_searxng_search_tool


def get_platform_tools(
    settings: Settings,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    storage=None,
    include_artifact_tools: bool = True,
    searxng_max_calls_per_run: int | None = None,
) -> list[BaseTool]:
    """Return platform-specific tools beyond the deepagents built-in suite.

    deepagents auto-injects ``ls``, ``read_file``, ``write_file``, ``edit_file``,
    ``glob``, ``grep`` via ``FilesystemMiddleware`` — those are configured through
    the ``backend`` parameter (see ``agent/factory.py``).  This function only
    returns additional tools that deepagents does not provide natively.

    The SearXNG search tool is included when ``settings.searxng_url`` is
    configured. By default this points to the local engine at
    ``http://127.0.0.1:8181/``.
    """
    tools: list[BaseTool] = []

    if task_id:
        tools.extend(
            create_resource_tools(
                task_id=task_id,
                workspace_root=settings.workspace_root,
                run_id=run_id,
                storage=storage,
                include_artifact_tools=include_artifact_tools,
            )
        )

    if settings.searxng_url:
        tools.append(
            create_searxng_search_tool(
                settings.searxng_url,
                cache=storage,
                task_id=task_id,
                ttl_seconds=settings.fresh_tool_cache_seconds,
                max_calls_per_run=searxng_max_calls_per_run,
            )
        )

    return tools
