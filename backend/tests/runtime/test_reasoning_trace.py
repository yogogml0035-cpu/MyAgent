from __future__ import annotations

from typing import Any, cast

import pytest

from app.agent_activity import build_deep_agent_activity_payload
from app.reasoning_trace import build_reasoning_trace_payload
from app.storage import TaskStorage


def test_reasoning_trace_payload_validates_and_normalizes_safe_fields() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="subagent-quotation",
        phase="observe",
        summary="发现 2 条结构化证据。",
        confidence="medium",
        evidence_refs=["quotation_similarity", {"unsafe": True}, "bidder-a.md"],
        source_event_id="event-1",
    )

    assert payload == {
        "agent_id": "subagent-quotation",
        "phase": "observe",
        "summary": "发现 2 条结构化证据。",
        "confidence": "medium",
        "evidence_refs": ["quotation_similarity", "bidder-a.md"],
        "source_event_id": "event-1",
    }


def test_reasoning_trace_payload_rejects_invalid_phase_or_confidence() -> None:
    with pytest.raises(ValueError, match="phase"):
        build_reasoning_trace_payload(
            agent_id="agent",
            phase=cast(Any, "thinking"),
            summary="摘要",
        )
    with pytest.raises(ValueError, match="confidence"):
        build_reasoning_trace_payload(
            agent_id="agent",
            phase="plan",
            summary="摘要",
            confidence=cast(Any, "certain"),
        )


def test_reasoning_trace_payload_redacts_paths_secrets_and_canaries() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="agent",
        phase="decide",
        summary=(
            "路径 /mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a 和 "
            "C:\\Users\\0325\\secret.txt 包含 SECRET_DOC_CANARY_123，"
            "Authorization: Bearer abcdefghijklmnop，sk-abcdefghijklmnop。"
        ),
        evidence_refs=[
            "/mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a/uploads/a.md",
            "RAW_PROMPT_CANARY_456",
        ],
    )
    serialized = str(payload)

    assert "/mnt/d/AgentProject" not in serialized
    assert "C:\\Users" not in serialized
    assert "SECRET_DOC_CANARY_123" not in serialized
    assert "RAW_PROMPT_CANARY_456" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "<absolute-path>" in serialized
    assert "<redacted-canary>" in serialized


def test_reasoning_trace_payload_truncates_overlong_summary() -> None:
    payload = build_reasoning_trace_payload(
        agent_id="agent",
        phase="final_summary",
        summary="x" * 800,
    )

    assert len(payload["summary"]) <= 360
    assert payload["summary"].endswith("…")


def test_deep_agent_activity_payload_redacts_and_truncates_safe_fields() -> None:
    payload = build_deep_agent_activity_payload(
        activity_kind="progress",
        phase="tool_use",
        status="running",
        title="工具调用准备",
        summary=(
            "路径 /mnt/d/AgentProject/MyAgent/backend/storage/sessions/task-a 和 "
            "C:\\Users\\0325\\secret.txt 包含 SECRET_DOC_CANARY_123，"
            "Authorization: Bearer abcdefghijklmnop，sk-abcdefghijklmnop。"
        ),
        tool_name="read_file",
        parameter_summary="/conversation_history/raw prompt " + "x" * 400,
        result_summary="CUSTOMER_SAFE_METADATA_ONLY",
        subgraph_path=["agent", "file-record-agent", "/mnt/d/private/path"],
        source_event_id="event-1",
    )
    serialized = str(payload)

    assert payload["schema_version"] == 1
    assert payload["source"] == "deepagents"
    assert payload["truncated"] is True
    assert "/mnt/d/AgentProject" not in serialized
    assert "C:\\Users" not in serialized
    assert "SECRET_DOC_CANARY_123" not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert "conversation_history/raw" not in serialized
    assert "<absolute-path>" in serialized
    assert "<redacted-canary>" in serialized
    assert "<deepagents-internal>" in serialized


def test_deep_agent_activity_payload_requires_summary() -> None:
    with pytest.raises(ValueError, match="summary"):
        build_deep_agent_activity_payload(
            activity_kind="progress",
            phase="tool_use",
            status="running",
            title="工具调用准备",
        )


def test_task_storage_appends_fixed_reasoning_trace_event(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="hello",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    _, run_id = started

    event = storage.append_reasoning_trace(
        state.task_id,
        run_id,
        agent_id="agent",
        phase="plan",
        summary="开始规划。",
        evidence_refs=["uploads/a.md"],
    )

    assert event.type == "reasoning_trace"
    assert event.run_id == run_id
    assert event.payload["phase"] == "plan"
    assert event.payload["evidence_refs"] == ["uploads/a.md"]
