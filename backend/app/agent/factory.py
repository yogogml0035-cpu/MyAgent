"""Agent factory wrapping create_deep_agent() with platform defaults."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph.state import CompiledStateGraph

from app.config import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools.base import BaseTool

try:
    from deepagents import create_deep_agent
except ImportError as exc:
    raise ImportError(
        "deepagents is not installed. "
        "Install it with: uv add deepagents"
    ) from exc


def build_agent(
    settings: Settings,
    *,
    model: str | None = None,
    tools: list[BaseTool | Callable | dict] | None = None,
    skills: list[str] | None = None,
    subagents: Sequence | None = None,
    checkpointer=None,
    store=None,
) -> CompiledStateGraph:
    """Build a compiled DeepAgent graph with platform defaults.

    create_deep_agent() auto-injects TodoListMiddleware, FilesystemMiddleware,
    SummarizationMiddleware, and PatchToolCallsMiddleware. Skills and subagents
    are passed via their dedicated keyword arguments — not via the middleware
    parameter — so the framework handles assembly correctly.
    """
    model_id = model or settings.default_model
    chat_model = _create_model(model_id, settings)

    return create_deep_agent(
        model=chat_model,
        tools=tools or [],
        skills=skills,
        subagents=subagents,
        checkpointer=checkpointer,
        store=store,
    )


def _create_model(model_id: str, settings: Settings) -> BaseChatModel:
    """Resolve a model identifier to a BaseChatModel instance."""
    try:
        from app.models.provider import create_model
    except ImportError as exc:
        raise ImportError(
            "app.models.provider is not available. "
            "Ensure the model layer is implemented before building agents."
        ) from exc

    return create_model(model_id, settings=settings)
