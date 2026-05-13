"""Agent factory wrapping create_deep_agent() with platform defaults."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.graph.state import CompiledStateGraph

from app.agent.middleware import build_full_middleware
from app.config import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools.base import BaseTool

logger = logging.getLogger(__name__)

try:
    from deepagents import create_deep_agent
    from deepagents.backends import (
        BackendProtocol,
        CompositeBackend,
        FilesystemBackend,
        StateBackend,
        StoreBackend,
    )
except ImportError as exc:
    raise ImportError(
        "deepagents is not installed. "
        "Install it with: uv add deepagents"
    ) from exc


def _make_backend(workspace_dir: Path | None, *, store=None) -> CompositeBackend:
    root = workspace_dir.resolve() if workspace_dir else Path.cwd()
    logger.debug("Creating CompositeBackend with workspace root_dir=%s", root)
    routes: dict[str, BackendProtocol] = {"/scratch/": StateBackend()}
    if store is not None:
        routes["/memories/"] = StoreBackend(store=store)
    return CompositeBackend(
        default=FilesystemBackend(root_dir=root, virtual_mode=True),
        routes=routes,
    )


def build_agent(
    settings: Settings,
    *,
    model: str | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    system_prompt: str | None = None,
    skills: list[str] | None = None,
    subagents: Sequence | None = None,
    workspace_dir: Path | None = None,
    checkpointer=None,
    store=None,
) -> CompiledStateGraph:
    model_id = model or settings.default_model
    chat_model = _create_model(model_id, settings)
    backend = _make_backend(workspace_dir, store=store)

    return create_deep_agent(
        model=chat_model,
        tools=tools or [],
        system_prompt=system_prompt,
        skills=skills,
        subagents=subagents,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
    )


def build_agent_with_middleware(
    settings: Settings,
    *,
    model: str | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    system_prompt: str | None = None,
    skills: list[str] | None = None,
    subagents: Sequence | None = None,
    workspace_dir: Path | None = None,
    checkpointer=None,
    store=None,
) -> CompiledStateGraph:
    model_id = model or settings.default_model
    chat_model = _create_model(model_id, settings)
    backend = _make_backend(workspace_dir, store=store)

    extra_middleware = _build_extra_middleware(
        settings,
        model=chat_model,
        skills_sources=skills,
        subagents=subagents,
    )

    return create_deep_agent(
        model=chat_model,
        tools=tools or [],
        system_prompt=system_prompt,
        middleware=extra_middleware,
        skills=skills,
        subagents=subagents,
        backend=backend,
        checkpointer=checkpointer,
        store=store,
    )


def _build_extra_middleware(
    settings: Settings,
    *,
    model,
    skills_sources: list[str] | None = None,
    subagents: Sequence | None = None,
) -> list:
    return build_full_middleware(
        settings,
        model=model,
        skills_sources=skills_sources,
        subagents=list(subagents) if subagents is not None else None,
    )


def _create_model(model_id: str, settings: Settings) -> BaseChatModel:
    try:
        from app.models.provider import create_model
    except ImportError as exc:
        raise ImportError(
            "app.models.provider is not available. "
            "Ensure the model layer is implemented before building agents."
        ) from exc

    return create_model(model_id, settings=settings)
