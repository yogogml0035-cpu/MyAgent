"""Middleware stack assembly for DeepAgents platform.

create_deep_agent() already injects TodoListMiddleware, FilesystemMiddleware,
and PatchToolCallsMiddleware by default. This module only builds the additional
middleware that should be layered on top.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentMiddleware

    from app.config import Settings

try:
    from deepagents.backends import StateBackend
    from deepagents.middleware.skills import SkillsMiddleware
    from deepagents.middleware.subagents import SubAgentMiddleware
    from deepagents.middleware.summarization import create_summarization_middleware
except ImportError as exc:
    raise ImportError(
        "deepagents or langchain is not installed. "
        "Install with: uv add deepagents langchain langgraph"
    ) from exc


def build_middleware(
    settings: Settings,
    *,
    skills_sources: list[str] | None = None,
    subagents: list | None = None,
) -> list[AgentMiddleware]:
    """Assemble extra middleware on top of create_deep_agent defaults.

    create_deep_agent() already adds TodoListMiddleware, FilesystemMiddleware,
    and PatchToolCallsMiddleware automatically. This function returns only the
    additional middleware the platform needs.
    """
    stack: list[AgentMiddleware] = []
    backend = StateBackend()

    if skills_sources:
        stack.append(
            cast(
                AgentMiddleware,
                SkillsMiddleware(
                    backend=backend,
                    sources=skills_sources,
                ),
            )
        )

    if subagents:
        stack.append(
            cast(
                AgentMiddleware,
                SubAgentMiddleware(
                    backend=backend,
                    subagents=subagents,
                ),
            )
        )

    return stack


def build_full_middleware(
    settings: Settings,
    *,
    model: object | None = None,
    skills_sources: list[str] | None = None,
    subagents: list | None = None,
) -> list[AgentMiddleware]:
    """Build the full extra middleware stack including summarization."""
    stack = build_middleware(settings, skills_sources=skills_sources, subagents=subagents)

    if model is not None:
        from langchain_core.language_models.chat_models import BaseChatModel

        stack.append(create_summarization_middleware(model=cast(BaseChatModel, model), backend=StateBackend()))

    return stack
