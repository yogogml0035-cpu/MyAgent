from __future__ import annotations

from threading import RLock

from app.contracts import HarnessEngine, Scheduler, WakeRequest
from app.session import ProjectedSessionState


class InlineScheduler(Scheduler):
    """Synchronous Scheduler skeleton for tests and future TaskRunner extraction."""

    def __init__(self, engine: HarnessEngine) -> None:
        self.engine = engine
        self._lock = RLock()
        self._running: set[str] = set()
        self._cancelled: set[tuple[str, str | None]] = set()

    def wake(self, request: WakeRequest) -> ProjectedSessionState:
        with self._lock:
            if request.session_id in self._running:
                raise RuntimeError("session 正在运行中")
            self._running.add(request.session_id)
        try:
            return self.engine.run_once(request.session_id, run_id=request.run_id)
        finally:
            with self._lock:
                self._running.discard(request.session_id)

    def cancel(self, session_id: str, run_id: str | None = None) -> None:
        with self._lock:
            self._cancelled.add((session_id, run_id))

    def is_running(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._running

    def is_cancel_requested(self, session_id: str, run_id: str | None = None) -> bool:
        with self._lock:
            return (session_id, run_id) in self._cancelled or (session_id, None) in self._cancelled
