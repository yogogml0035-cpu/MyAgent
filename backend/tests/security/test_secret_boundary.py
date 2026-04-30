from __future__ import annotations

import json

import pytest

from app.contracts import (
    ExecutionHandle,
    InMemorySecretVault,
    SecretVault,
    build_credential_ref,
    credential_ref_payload,
)
from app.schemas import ChatMessage
from app.security import (
    SecretScanViolation,
    assert_no_secret_scan_findings,
    collect_session_output_texts,
    scan_text_for_secrets,
)
from app.storage import TaskStorage


def test_credential_ref_payload_exposes_hash_and_label_without_secret() -> None:
    secret = "sk-super-secret-value"
    ref = build_credential_ref(provider="deepseek", name="chat", secret=secret)
    payload = credential_ref_payload(ref)
    serialized = json.dumps(payload, ensure_ascii=False)
    vault = InMemorySecretVault({ref.id: secret})

    assert isinstance(vault, SecretVault)
    assert vault.resolve(ref) == secret
    assert payload == {
        "id": "credential:deepseek:chat",
        "label": "deepseek:chat",
        "fingerprint": ref.fingerprint,
    }
    assert secret not in serialized
    assert "sk-" not in serialized


def test_execution_handle_carries_credential_refs_without_secret_values() -> None:
    ref = build_credential_ref(
        provider="tavily",
        name="search",
        secret="tvly-secret-token-value",
    )
    handle = ExecutionHandle(
        id="exec-1",
        executor="legacy",
        credential_refs=(ref,),
        metadata={"credential_refs": [ref.id]},
    )
    serialized = json.dumps(
        {
            "credential_refs": [credential_ref_payload(item) for item in handle.credential_refs],
            "metadata": handle.metadata,
        },
        ensure_ascii=False,
    )

    assert ref.id == "credential:tavily:search"
    assert "tvly-secret-token-value" not in serialized
    assert "credential:tavily:search" in serialized


def test_secret_scanner_detects_forbidden_credential_shapes() -> None:
    findings = scan_text_for_secrets(
        "Authorization: Bearer secret-token and api_key=sk-abcdefghijklmnop",
        source="events.jsonl",
    )

    assert [finding.pattern for finding in findings] == [
        "authorization-header",
        "bearer-token",
        "openai-style-secret",
        "api-key-field",
    ]
    with pytest.raises(SecretScanViolation, match="发现敏感凭据输出"):
        assert_no_secret_scan_findings({"events.jsonl": "refresh_token=secret"})


def test_session_secret_scan_covers_events_messages_artifacts_and_workspace(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="生成安全报告",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    task_id = state.task_id
    run_id = started[1]
    task_dir = storage.task_dir(task_id)

    storage.append_event(
        task_id,
        "tool.call.completed",
        "工具完成。",
        {
            "credential_ref": credential_ref_payload(
                build_credential_ref(provider="deepseek", name="chat", secret="safe-secret")
            ),
            "output_summary": "只记录引用，不记录密钥。",
        },
        run_id=run_id,
    )
    storage.write_run_manifest(task_id, run_id, {"credential_refs": ["credential:deepseek:chat"]})
    storage.write_run_text(task_id, run_id, "final-summary.md", "报告只包含安全摘要。")
    (task_dir / "agent_workspace" / "runs" / run_id / "records").mkdir(parents=True)
    (task_dir / "agent_workspace" / "runs" / run_id / "records" / "note.md").write_text(
        "只记录工具观察摘要。",
        encoding="utf-8",
    )
    storage.update_task(
        task_id,
        status="complete",
        append_message=ChatMessage(
            role="assistant",
            content="最终回答只包含安全摘要和产物引用。",
            created_at="2026-04-30T00:00:00Z",
            run_id=run_id,
        ),
        run_id=run_id,
        artifact_names=["final-summary.md"],
    )

    assert_no_secret_scan_findings(collect_session_output_texts(task_dir))


def test_session_secret_scan_fails_when_workspace_or_artifact_contains_secret(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    task_dir = storage.task_dir(state.task_id)
    (task_dir / "agent_workspace" / "runs" / "run-1" / "outputs").mkdir(parents=True)
    (task_dir / "agent_workspace" / "runs" / "run-1" / "outputs" / "leak.md").write_text(
        "Authorization: Bearer leaked",
        encoding="utf-8",
    )

    with pytest.raises(SecretScanViolation, match="authorization-header"):
        assert_no_secret_scan_findings(collect_session_output_texts(task_dir))
