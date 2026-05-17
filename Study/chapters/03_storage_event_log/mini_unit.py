from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Event:
    id: str
    seq: int
    type: str
    message: str


class EventLog:
    def __init__(self) -> None:
        self._seq = 0
        self._events: list[Event] = []

    def append_event(self, event_type: str, message: str) -> Event:
        self._seq += 1
        event = Event(id=uuid4().hex, seq=self._seq, type=event_type, message=message)
        self._events.append(event)
        return event

    def read_events(self, after_id: str | None = None) -> list[Event]:
        if after_id is None:
            return list(self._events)
        for index, event in enumerate(self._events):
            if event.id == after_id:
                return list(self._events[index + 1 :])
        return list(self._events)


def assert_source_contracts() -> None:
    storage = (REPO_ROOT / "backend/app/storage.py").read_text(encoding="utf-8")
    fake = (REPO_ROOT / "backend/tests/fakes.py").read_text(encoding="utf-8")

    assert "def start_run(" in storage
    assert "def append_event(" in storage
    assert "def read_events(self, task_id: str, *, after_id: str | None = None)" in storage
    assert "ORDER BY seq ASC" in storage
    assert "if after_row is None:" in storage
    assert "return [self._event_record_from_row(row) for row in cur.fetchall()]" in storage

    assert "def read_events(self, task_id: str, *, after_id: str | None = None)" in fake
    assert "return copy.deepcopy(events)" in fake


if __name__ == "__main__":
    log = EventLog()
    first = log.append_event("task_created", "任务已创建")
    second = log.append_event("assistant_answer_delta", "你好")
    third = log.append_event("task_completed", "任务完成")

    assert [event.seq for event in log.read_events()] == [1, 2, 3]
    assert log.read_events(after_id=first.id) == [second, third]
    assert log.read_events(after_id="missing-event-id") == [first, second, third], (
        "未知游标要 fail open 返回完整事件流，避免前端恢复时漏掉终态事件"
    )
    assert_source_contracts()

    print("events:", log.read_events())
    print("OK: 你已经理解了 append-only 事件日志和 after_id 恢复语义。")
