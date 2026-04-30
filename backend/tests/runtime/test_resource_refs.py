from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts import ArtifactRef, ResourceRef, build_artifact_ref, build_upload_resource_ref
from app.main import create_app
from app.settings import Settings
from app.storage import TaskStorage


def make_client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                task_root=tmp_path / "sessions",
                deepseek_api_key=None,
                deepseek_base_url="https://api.deepseek.com",
                tavily_api_key=None,
                workspace_root=tmp_path / "sessions",
            )
        )
    )


def test_upload_event_includes_virtual_resource_ref_without_absolute_path(tmp_path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    body = b"# Customer Upload"

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("customer.md", body, "text/markdown"))],
    )

    assert response.status_code == 200
    state = response.json()
    event = next(event for event in state["events"] if event["type"] == "file_uploaded")
    payload = event["payload"]
    expected_digest = "sha256:" + sha256(body).hexdigest()

    assert payload["filename"] == "customer.md"
    assert payload["bytes"] == len(body)
    assert payload["resource_id"] == f"upload:{task_id}:customer.md"
    assert payload["digest"] == expected_digest
    assert payload["uri"] == f"myagent://sessions/{task_id}/resources/customer.md"
    assert payload["resource_ref"] == {
        "id": f"upload:{task_id}:customer.md",
        "kind": "upload",
        "uri": f"myagent://sessions/{task_id}/resources/customer.md",
        "name": "customer.md",
        "media_type": "markdown",
        "size_bytes": len(body),
        "digest": expected_digest,
        "metadata": {"session_id": task_id},
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "uploads/customer.md" not in serialized


def test_run_artifact_manifest_includes_artifact_ref_and_keeps_legacy_download(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="生成报告",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    task_id = state.task_id
    run_id = started[1]
    storage.write_run_manifest(task_id, run_id, {"started_at": "2026-04-30T00:00:00Z"})
    storage.write_run_text(task_id, run_id, "report.html", "<html>ok</html>")

    manifest = json.loads(
        (tmp_path / "sessions" / task_id / "artifacts" / "runs" / run_id / "run.json").read_text(
            encoding="utf-8"
        )
    )
    artifact_refs = manifest["artifact_refs"]
    expected_digest = "sha256:" + sha256(b"<html>ok</html>").hexdigest()

    assert len(artifact_refs) == 1
    assert artifact_refs[0]["id"] == f"artifact:{task_id}:{run_id}:report.html"
    assert artifact_refs[0]["name"] == "report.html"
    assert artifact_refs[0]["type"] == "html"
    assert artifact_refs[0]["uri"] == (
        f"myagent://sessions/{task_id}/runs/{run_id}/artifacts/report.html"
    )
    assert artifact_refs[0]["digest"] == expected_digest
    assert artifact_refs[0]["resource_ref"]["kind"] == "artifact"
    assert artifact_refs[0]["resource_ref"]["digest"] == expected_digest
    assert storage.resolve_run_artifact(task_id, run_id, "report.html").read_text(
        encoding="utf-8"
    ) == "<html>ok</html>"
    assert storage.get_task(task_id).runs[0].artifact_names == ["report.html"]
    serialized = json.dumps(artifact_refs, ensure_ascii=False)
    assert str(tmp_path) not in serialized


def test_record_run_artifact_backfills_ref_for_existing_promoted_file(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="生成附件",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    task_id = state.task_id
    run_id = started[1]
    storage.write_run_manifest(task_id, run_id, {"started_at": "2026-04-30T00:00:00Z"})
    output_path = storage.run_artifact_dir(task_id, run_id) / "final-summary.md"
    output_path.write_text("# Summary", encoding="utf-8")

    storage.record_run_artifact(task_id, run_id, "final-summary.md")

    manifest = json.loads(
        (tmp_path / "sessions" / task_id / "artifacts" / "runs" / run_id / "run.json").read_text(
            encoding="utf-8"
        )
    )
    refs = manifest["artifact_refs"]
    assert refs[0]["id"] == f"artifact:{task_id}:{run_id}:final-summary.md"
    assert refs[0]["type"] == "markdown"
    assert refs[0]["uri"] == (
        f"myagent://sessions/{task_id}/runs/{run_id}/artifacts/final-summary.md"
    )
    assert str(tmp_path) not in json.dumps(refs, ensure_ascii=False)


def test_task_storage_common_writes_reject_paths_outside_task_dir(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    task_id = storage.create_task(None, "deepseek-reasoner").task_id

    json_path = storage.write_json(task_id, "records/safe.json", {"ok": True})
    text_path = storage.write_text(task_id, "artifacts/safe.txt", "ok")

    assert json.loads(json_path.read_text(encoding="utf-8")) == {"ok": True}
    assert text_path.read_text(encoding="utf-8") == "ok"

    escaped_json = tmp_path / "sessions" / "escaped.json"
    escaped_text = tmp_path / "sessions" / "escaped.txt"
    with pytest.raises(ValueError, match="超出任务目录"):
        storage.write_json(task_id, "../escaped.json", {"bad": True})
    with pytest.raises(ValueError, match="超出任务目录"):
        storage.write_text(task_id, "../escaped.txt", "bad")

    assert not escaped_json.exists()
    assert not escaped_text.exists()


def test_task_storage_common_writes_reject_absolute_paths(tmp_path) -> None:
    storage = TaskStorage(tmp_path / "sessions")
    task_id = storage.create_task(None, "deepseek-reasoner").task_id
    outside_json = tmp_path / "outside.json"
    outside_text = tmp_path / "outside.txt"

    with pytest.raises(ValueError, match="绝对路径"):
        storage.write_json(task_id, str(outside_json), {"bad": True})
    with pytest.raises(ValueError, match="绝对路径"):
        storage.write_text(task_id, str(outside_text), "bad")

    assert not outside_json.exists()
    assert not outside_text.exists()


def test_resource_contract_helpers_create_virtual_refs() -> None:
    upload = build_upload_resource_ref(
        session_id="session-1",
        filename="../secret.md",
        size_bytes=12,
        digest="sha256:abc",
        media_type="markdown",
    )
    artifact = build_artifact_ref(
        session_id="session-1",
        run_id="run-1",
        name="../report.html",
        artifact_type="html",
        size_bytes=24,
        digest="sha256:def",
    )

    assert isinstance(upload, ResourceRef)
    assert isinstance(artifact, ArtifactRef)
    assert upload.id == "upload:session-1:secret.md"
    assert upload.uri == "myagent://sessions/session-1/resources/secret.md"
    assert artifact.id == "artifact:session-1:run-1:report.html"
    assert artifact.resource.uri == (
        "myagent://sessions/session-1/runs/run-1/artifacts/report.html"
    )
