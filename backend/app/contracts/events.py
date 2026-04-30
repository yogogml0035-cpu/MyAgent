from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

EventLevel = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True)
class SessionEvent:
    id: str
    session_id: str
    seq: int
    type: str
    created_at: datetime
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    level: EventLevel | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class NewSessionEvent:
    type: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    level: EventLevel | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    created_at: datetime
    latest_seq: int
    metadata: dict[str, Any] = field(default_factory=dict)
