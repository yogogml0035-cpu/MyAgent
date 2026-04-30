from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from .events import SessionEvent, SessionSnapshot
from .execution import ToolSpec

ContextMessageRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ContextMessage:
    role: ContextMessageRole
    content: str
    event_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ContextEventRef:
    event_id: str
    type: str
    seq: int
    run_id: str | None = None


@dataclass(frozen=True)
class ContextView:
    session_id: str
    run_id: str | None
    messages: tuple[ContextMessage, ...] = ()
    visible_tools: tuple[ToolSpec, ...] = ()
    resource_manifest: tuple[dict[str, Any], ...] = ()
    event_refs: tuple[ContextEventRef, ...] = ()
    token_budget: int | None = None
    policy: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ContextManager(Protocol):
    def build_context(
        self,
        session: SessionSnapshot,
        events: list[SessionEvent],
        *,
        run_id: str | None,
        policy: dict[str, Any] | None = None,
    ) -> ContextView:
        ...
