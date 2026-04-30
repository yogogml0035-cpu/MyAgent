from __future__ import annotations

from app.contracts import HarnessEngine, SessionStore
from app.session import ProjectedSessionState, TaskStateProjector


class ProjectingHarnessEngine(HarnessEngine):
    """Read-only engine skeleton that projects current Session events.

    This is intentionally not wired into TaskRunner yet. It gives the Harness
    split a testable boundary without changing production scheduling behavior.
    """

    def __init__(
        self,
        session_store: SessionStore,
        projector: TaskStateProjector | None = None,
    ) -> None:
        self.session_store = session_store
        self.projector = projector or TaskStateProjector()

    def run_once(self, session_id: str, *, run_id: str | None = None) -> ProjectedSessionState:
        events = self.session_store.get_events(session_id)
        if run_id is not None:
            events = [
                event
                for event in events
                if event.run_id is None or event.run_id == run_id
            ]
        return self.projector.project(events)
