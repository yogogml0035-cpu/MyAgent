from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .events import NewSessionEvent, SessionEvent, SessionSnapshot


@runtime_checkable
class SessionStore(Protocol):
    def create_session(self, metadata: dict[str, Any]) -> SessionSnapshot:
        ...

    def get_session(self, session_id: str) -> SessionSnapshot:
        ...

    def get_events(
        self,
        session_id: str,
        *,
        after_seq: int | None = None,
        limit: int | None = None,
        reverse: bool = False,
    ) -> list[SessionEvent]:
        ...

    def emit_event(self, session_id: str, event: NewSessionEvent) -> SessionEvent:
        ...
