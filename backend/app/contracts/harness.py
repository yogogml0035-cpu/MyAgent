from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.session import ProjectedSessionState

WakeReason = Literal["user_message", "retry", "resume", "scheduled", "tool_callback"]


@dataclass(frozen=True)
class WakeRequest:
    session_id: str
    reason: WakeReason
    run_id: str | None = None


@runtime_checkable
class Scheduler(Protocol):
    def wake(self, request: WakeRequest) -> ProjectedSessionState:
        ...

    def cancel(self, session_id: str, run_id: str | None = None) -> None:
        ...

    def is_running(self, session_id: str) -> bool:
        ...


@runtime_checkable
class HarnessEngine(Protocol):
    def run_once(self, session_id: str, *, run_id: str | None = None) -> ProjectedSessionState:
        ...
