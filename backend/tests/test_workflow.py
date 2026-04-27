from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from threading import Event, Thread
from typing import cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis import (
    CancelledError,
    MarkdownDocument,
    classify_documents,
    inspect_quotation_similarity,
    inspect_template_traces,
    similar_paragraph_pairs,
)
from app.main import create_app
from app.model_provider import DeepSeekProvider, ProviderRouter
from app.permissions import PermissionPolicy
from app.runtime import CancellationController, run_cancellable_command
from app.schemas import MAX_MESSAGE_CHARS
from app.settings import Settings, load_env_file, read_list_env
from app.storage import MAX_FILENAME_BYTES, TaskStorage
from app.tools import WorkspaceTools


def make_client(
    tmp_path: Path,
    *,
    access_token: str | None = None,
    max_upload_files: int = 10,
    max_upload_file_bytes: int = 10 * 1024 * 1024,
    max_upload_request_bytes: int = 101 * 1024 * 1024,
    max_json_request_bytes: int = 64 * 1024,
    cors_origins: tuple[str, ...] = ("http://localhost:3001", "http://127.0.0.1:3001"),
    client_host: str | None = None,
) -> TestClient:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
        access_token=access_token,
        cors_origins=cors_origins,
        max_upload_files=max_upload_files,
        max_upload_file_bytes=max_upload_file_bytes,
        max_upload_request_bytes=max_upload_request_bytes,
        max_json_request_bytes=max_json_request_bytes,
    )
    if client_host:
        return TestClient(create_app(settings), client=(client_host, 50000))
    return TestClient(create_app(settings))


def wait_for_terminal_status(client: TestClient, task_id: str) -> dict:
    for _ in range(80):
        state = client.get(f"/api/tasks/{task_id}").json()
        if state["status"] in {"complete", "failed", "cancelled", "needs_input"}:
            return state
        time.sleep(0.05)
    raise AssertionError("Task did not finish")


def test_markdown_bid_analysis_workflow_creates_artifacts(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-reasoner"}).json()
    task_id = created["task_id"]

    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-c.md", BIDDER_C.encode("utf-8"), "text/markdown")),
    ]
    upload_response = client.post(f"/api/tasks/{task_id}/files", files=files)
    assert upload_response.status_code == 200
    assert upload_response.json()["upload_count"] == 4

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    assert response.status_code == 200
    state = wait_for_terminal_status(client, task_id)

    assert state["status"] == "complete", state.get("error")
    assert {artifact["name"] for artifact in state["artifacts"]} >= {
        "report.html",
        "final-summary.md",
        "evidence.json",
        "task-plan.md",
    }
    assert any(event["type"] == "plan_created" for event in state["events"])
    assert any(event["type"] == "subagents_started" for event in state["events"])
    assert any(event["type"] == "subagent_assigned" for event in state["events"])
    assert any(event["type"] == "tool_call" for event in state["events"])
    assert any(event["type"] == "tool_result" for event in state["events"])
    assert any(event["type"] == "model_call" for event in state["events"])
    assert any(event["type"] == "model_result" for event in state["events"])
    assert any(event["type"] == "task_completed" for event in state["events"])

    task_dir = tmp_path / "tasks" / task_id
    assert (task_dir / "plan.json").exists()
    plan = (task_dir / "plan.json").read_text(encoding="utf-8")
    assert "fetch_url" not in plan
    assert (task_dir / "subagents" / "quotation_similarity-task.json").exists()
    assert (task_dir / "subagents" / "quotation_similarity.json").exists()
    subagent_report = (task_dir / "subagents" / "quotation_similarity.json").read_text(
        encoding="utf-8"
    )
    assert "deepseek-reasoner" in subagent_report
    assert "reasoning" in subagent_report
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))
    assert [item["filename"] for item in run_manifest["inputs"]] == [
        "bidder-a.md",
        "bidder-b.md",
        "bidder-c.md",
        "tender.md",
    ]
    input_manifest = json.loads(
        (task_dir / "artifacts" / "input-manifest.json").read_text(encoding="utf-8")
    )
    assert {item["filename"] for item in input_manifest} == {
        "tender.md",
        "bidder-a.md",
        "bidder-b.md",
        "bidder-c.md",
    }
    assert sum(1 for item in input_manifest if item["role"] == "bidder") == 3

    report = client.get(f"/api/tasks/{task_id}/artifacts/report.html")
    assert report.status_code == 200
    assert "Three-Bidder Comparison View" in report.text
    assert 'data-severity="high"' in report.text or 'data-severity="medium"' in report.text


def test_follow_up_task_run_preserves_existing_artifacts_and_reuses_uploads(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    first_state = wait_for_terminal_status(client, task_id)
    assert first_state["status"] == "complete"
    first_run_id = first_state["runs"][0]["id"]
    first_run_dir = tmp_path / "tasks" / task_id / "artifacts" / "runs" / first_run_id
    report_before = (first_run_dir / "report.html").read_bytes()
    evidence_before = (first_run_dir / "evidence.json").read_bytes()

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "请重新总结当前报告", "model": "deepseek-reasoner"},
    )
    second_state = wait_for_terminal_status(client, task_id)
    second_run_id = second_state["runs"][1]["id"]
    second_manifest = json.loads(
        (tmp_path / "tasks" / task_id / "artifacts" / "runs" / second_run_id / "run.json").read_text(
            encoding="utf-8"
        )
    )

    assert response.status_code == 200
    assert second_state["status"] == "complete"
    assert second_state["run_count"] == 2
    assert second_run_id != first_run_id
    assert (first_run_dir / "report.html").read_bytes() == report_before
    assert (first_run_dir / "evidence.json").read_bytes() == evidence_before
    assert [item["filename"] for item in second_manifest["inputs"]] == [
        "bidder-a.md",
        "bidder-b.md",
        "tender.md",
    ]
    assert all(message["run_id"] for message in second_state["messages"])


def test_bidder_only_documents_are_not_reclassified_as_tender() -> None:
    documents = [
        MarkdownDocument(
            "alpha.md",
            "unknown",
            None,
            "# Alpha\n根据招标文件要求提交响应。\n报价：1000000元",
            ["# Alpha", "根据招标文件要求提交响应。", "报价：1000000元"],
        ),
        MarkdownDocument(
            "beta.md",
            "unknown",
            None,
            "# Beta\n根据招标文件要求提交响应。\n报价：1000000元",
            ["# Beta", "根据招标文件要求提交响应。", "报价：1000000元"],
        ),
    ]

    classified = classify_documents(documents)

    assert [doc.role for doc in classified] == ["bidder", "bidder"]
    assert [doc.bidder_name for doc in classified] == ["Alpha", "Beta"]


def test_bidder_only_uploads_complete_with_all_files_as_bidders(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    alpha = """# Alpha Construction

投标人：Alpha Construction
本项目采用三级质量控制机制，采用每日巡检、周报复核和问题闭环整改方式，确保施工质量满足合同目标。
总价：1000000元
"""
    beta = """# Beta Construction

投标人：Beta Construction
本项目采用三级质量控制机制，采用每日巡检、周报复核和问题闭环整改方式，确保施工质量满足合同目标。
总价：1000000元
"""
    files = [
        ("files", ("alpha.md", alpha.encode("utf-8"), "text/markdown")),
        ("files", ("beta.md", beta.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    plan = json.loads((tmp_path / "tasks" / task_id / "plan.json").read_text(encoding="utf-8"))

    assert state["status"] == "complete", state.get("error")
    assert [item["role"] for item in plan["input_material_roles"]] == ["bidder", "bidder"]


def test_upload_while_task_is_running_returns_conflict_without_persisting(
    tmp_path: Path,
) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    async def slow_chat(_message: str, _model: str) -> str:
        await asyncio.sleep(10)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_async", side_effect=slow_chat):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        time.sleep(0.2)
        response = client.post(
            f"/api/tasks/{task_id}/files",
            files=[("files", ("late.md", b"# Late", "text/markdown"))],
        )
        assert response.status_code == 409
        state = client.get(f"/api/tasks/{task_id}").json()
        assert state["upload_count"] == 0
        assert not (tmp_path / "tasks" / task_id / "uploads" / "late.md").exists()
        assert not any(
            event["type"] == "file_uploaded"
            and event.get("payload", {}).get("filename") == "late.md"
            for event in state["events"]
        )
        client.post(f"/api/tasks/{task_id}/cancel")


def test_follow_up_message_is_rejected_while_run_is_active(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    async def slow_chat(_message: str, _model: str) -> str:
        await asyncio.sleep(10)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_async", side_effect=slow_chat):
        started = client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        time.sleep(0.2)
        rejected = client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "第二条", "model": "deepseek-reasoner"},
        )
        state = client.get(f"/api/tasks/{task_id}").json()
        client.post(f"/api/tasks/{task_id}/cancel")

    assert started.status_code == 200
    assert rejected.status_code == 409
    assert state["status"] == "running"
    assert state["run_count"] == 1
    assert len([message for message in state["messages"] if message["role"] == "user"]) == 1


def test_startup_marks_persisted_running_task_as_interrupted(tmp_path: Path) -> None:
    task_root = tmp_path / "tasks"
    storage = TaskStorage(task_root)
    task_id = storage.create_task(None, "deepseek-reasoner").task_id
    storage.update_task(task_id, status="running")
    settings = Settings(
        task_root=task_root,
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=task_root,
    )

    client = TestClient(create_app(settings))
    state = client.get(f"/api/tasks/{task_id}").json()

    assert state["status"] == "interrupted"
    assert "startup or reload" in state["error"]
    assert any(event["type"] == "task_interrupted" for event in state["events"])
    assert not cast(FastAPI, client.app).state.runner.is_running(task_id)


def test_orphan_running_task_allows_upload_after_cancel_recovery(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    cast(FastAPI, client.app).state.storage.update_task(task_id, status="running")

    cancelled = client.post(f"/api/tasks/{task_id}/cancel")
    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("after-recovery.md", b"# Recovered", "text/markdown"))],
    )

    assert cancelled.json()["status"] == "interrupted"
    assert response.status_code == 200
    assert response.json()["upload_count"] == 1
    assert (tmp_path / "tasks" / task_id / "uploads" / "after-recovery.md").exists()


def test_task_api_rejects_nonlocal_client_without_token(tmp_path: Path) -> None:
    local_client = make_client(tmp_path)
    task_id = local_client.post("/api/tasks", json={}).json()["task_id"]
    remote_client = make_client(tmp_path, client_host="203.0.113.10")

    response = remote_client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 403


def test_task_api_accepts_valid_access_token_and_rejects_wrong_token(tmp_path: Path) -> None:
    token = "test-token"
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
        access_token=token,
    )
    app = create_app(settings)
    storage = app.state.storage
    task_id = storage.create_task(None, "deepseek-reasoner").task_id
    client = TestClient(app, client=("203.0.113.10", 50000))

    wrong = client.get(f"/api/tasks/{task_id}", headers={"Authorization": "Bearer wrong"})
    right = client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})

    assert wrong.status_code == 401
    assert right.status_code == 200
    assert right.json()["task_id"] == task_id


def test_task_list_summaries_are_sorted_and_titled_from_first_user_message(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    first_id = client.post("/api/tasks", json={}).json()["task_id"]
    second_id = client.post("/api/tasks", json={}).json()["task_id"]

    first_response = client.post(
        f"/api/tasks/{first_id}/messages",
        json={"message": "abcdefg", "model": "deepseek-reasoner"},
    )
    first_state = wait_for_terminal_status(client, first_id)
    time.sleep(1.05)
    second_response = client.post(
        f"/api/tasks/{second_id}/messages",
        json={"message": "你好世界测试文本", "model": "deepseek-reasoner"},
    )
    second_state = wait_for_terminal_status(client, second_id)
    empty_id = client.post("/api/tasks", json={}).json()["task_id"]

    summaries = client.get("/api/tasks").json()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_state["status"] == "complete"
    assert second_state["status"] == "complete"
    assert [summary["task_id"] for summary in summaries[:2]] == [second_id, first_id]
    assert {summary["task_id"]: summary["title"] for summary in summaries} == {
        second_id: "你好世界测",
        first_id: "abcde",
    }
    assert empty_id not in {summary["task_id"] for summary in summaries}


def test_task_summaries_respect_access_token_enforcement(tmp_path: Path) -> None:
    token = "test-token"
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
        access_token=token,
    )
    app = create_app(settings)
    storage = app.state.storage
    state = storage.create_task(None, "deepseek-reasoner")
    started = storage.start_run(
        state.task_id,
        message="hello",
        model="deepseek-reasoner",
        expected_statuses={"idle"},
    )
    assert started is not None
    _, run_id = started
    storage.update_task_if_status(state.task_id, {"running"}, status="complete", run_id=run_id)
    client = TestClient(app, client=("203.0.113.10", 50000))

    missing = client.get("/api/tasks")
    wrong = client.get("/api/tasks", headers={"X-MyAgent-Token": "wrong"})
    right = client.get("/api/tasks", headers={"X-MyAgent-Token": token})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert right.status_code == 200
    assert right.json()[0]["title"] == "hello"


def test_cors_allows_default_local_frontend_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.options(
        "/api/tasks",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-MyAgent-Token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"
    assert "x-myagent-token" in response.headers["access-control-allow-headers"].lower()


def test_cors_allows_configured_lan_frontend_origin(tmp_path: Path) -> None:
    origin = "http://10.11.148.97:3001"
    client = make_client(tmp_path, access_token="test-token", cors_origins=(origin,))

    response = client.options(
        "/api/tasks",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-MyAgent-Token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unconfigured_lan_frontend_origin(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.options(
        "/api/tasks",
        headers={
            "Origin": "http://10.11.148.97:3001",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_origin_env_parser_trims_empty_items_and_trailing_slashes(monkeypatch) -> None:
    monkeypatch.setenv(
        "MYAGENT_CORS_ORIGINS",
        " http://localhost:3001/, , http://10.11.148.97:3001/ ",
    )

    origins = read_list_env("MYAGENT_CORS_ORIGINS", ("http://127.0.0.1:3001",))

    assert origins == ("http://localhost:3001", "http://10.11.148.97:3001")


def test_artifact_download_requires_and_accepts_access_token(tmp_path: Path) -> None:
    token = "test-token"
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
        access_token=token,
    )
    app = create_app(settings)
    storage = app.state.storage
    task_id = storage.create_task(None, "deepseek-reasoner").task_id
    storage.write_text(task_id, "artifacts/report.html", "<html>ok</html>")
    client = TestClient(app, client=("203.0.113.10", 50000))

    missing = client.get(f"/api/tasks/{task_id}/artifacts/report.html")
    wrong = client.get(
        f"/api/tasks/{task_id}/artifacts/report.html",
        headers={"X-Agent-Chat-Token": "wrong"},
    )
    right = client.get(
        f"/api/tasks/{task_id}/artifacts/report.html",
        headers={"X-MyAgent-Token": token},
    )
    right_legacy = client.get(
        f"/api/tasks/{task_id}/artifacts/report.html",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert right.status_code == 200
    assert "ok" in right.text
    assert right_legacy.status_code == 200


def test_run_scoped_artifact_endpoint_is_allowlisted_and_path_safe(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    run_id = state["runs"][0]["id"]

    allowed = client.get(f"/api/tasks/{task_id}/runs/{run_id}/artifacts/report.html")
    unlisted = client.get(f"/api/tasks/{task_id}/runs/{run_id}/artifacts/run.json")
    traversal = client.get(
        f"/api/tasks/{task_id}/runs/{run_id}/artifacts/%2e%2e%2freport.html"
    )
    latest = client.get(f"/api/tasks/{task_id}/artifacts/report.html")

    assert allowed.status_code == 200
    assert "Three-Bidder Comparison View" in allowed.text
    assert unlisted.status_code == 404
    assert traversal.status_code in {400, 404}
    assert latest.status_code == 200
    assert latest.text == allowed.text


def test_run_history_and_artifacts_persist_across_app_restart(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    before_restart = wait_for_terminal_status(client, task_id)
    run_id = before_restart["runs"][0]["id"]
    report_before = client.get(
        f"/api/tasks/{task_id}/runs/{run_id}/artifacts/report.html"
    ).text

    restarted = TestClient(create_app(settings))
    summaries = restarted.get("/api/tasks").json()
    restored = restarted.get(f"/api/tasks/{task_id}").json()
    report_after = restarted.get(
        f"/api/tasks/{task_id}/runs/{run_id}/artifacts/report.html"
    )

    assert summaries[0]["task_id"] == task_id
    assert summaries[0]["run_count"] == 1
    assert restored["run_count"] == 1
    assert restored["runs"][0]["id"] == run_id
    assert restored["messages"][0]["run_id"] == run_id
    assert report_after.status_code == 200
    assert report_after.text == report_before


def test_message_over_length_limit_is_rejected_without_starting_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "x" * (MAX_MESSAGE_CHARS + 1), "model": "deepseek-reasoner"},
    )
    state = client.get(f"/api/tasks/{task_id}").json()

    assert response.status_code == 422
    assert state["status"] == "idle"
    assert state["messages"] == []
    assert not (tmp_path / "tasks" / task_id / "run.json").exists()
    assert not cast(FastAPI, client.app).state.runner.is_running(task_id)


def test_create_task_rejects_initial_message_over_length_limit(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/tasks",
        json={"message": "x" * (MAX_MESSAGE_CHARS + 1), "model": "deepseek-reasoner"},
    )

    assert response.status_code == 422
    assert list((tmp_path / "tasks").iterdir()) == []


def test_create_task_rejects_initial_message_without_persisting(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/tasks",
        json={"message": "hello", "model": "deepseek-reasoner"},
    )

    assert response.status_code == 400
    assert "without an initial message" in response.json()["detail"]
    assert client.get("/api/tasks").json() == []
    assert list((tmp_path / "tasks").iterdir()) == []


def test_json_request_byte_limit_is_rejected_before_task_starts(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_json_request_bytes=64)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "x" * 100, "model": "deepseek-reasoner"},
    )

    assert response.status_code == 413
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "idle"


def test_model_reasoning_failure_does_not_block_deterministic_evidence(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    with patch("app.model_provider.ProviderRouter.reason", side_effect=RuntimeError("rate limit")):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    evidence = json.loads(
        (tmp_path / "tasks" / task_id / "artifacts" / "evidence.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "complete", state.get("error")
    assert evidence
    assert any(event["type"] == "model_warning" for event in state["events"])


def test_case_insensitive_template_trace_locations_are_recorded() -> None:
    documents = [
        MarkdownDocument(
            "alpha.md",
            "bidder",
            "Alpha",
            "# Alpha\nlower todo marker",
            ["# Alpha", "lower todo marker"],
        ),
        MarkdownDocument(
            "beta.md",
            "bidder",
            "Beta",
            "# Beta\nmixed ToDo marker",
            ["# Beta", "mixed ToDo marker"],
        ),
    ]

    evidence = inspect_template_traces([], documents)
    todo_evidence = next(item for item in evidence if item["details"]["marker"] == "TODO")

    assert {location["file"] for location in todo_evidence["locations"]} == {
        "alpha.md",
        "beta.md",
    }
    assert {location["line"] for location in todo_evidence["locations"]} == {2}


def test_quotation_similarity_ignores_shared_non_price_numbers() -> None:
    left = MarkdownDocument(
        "alpha.md",
        "bidder",
        "Alpha",
        "",
        [
            "# Alpha",
            "第12章 项目概况，服务期限90天，计划于2026年05月01日启动。",
            "联系人电话：13800138000",
            "报价：1000000元",
        ],
    )
    right = MarkdownDocument(
        "beta.md",
        "bidder",
        "Beta",
        "",
        [
            "# Beta",
            "第12章 项目概况，服务期限90天，计划于2026年05月01日启动。",
            "联系人电话：13800138000",
            "报价：1100000元",
        ],
    )

    evidence = inspect_quotation_similarity([], [left, right])

    assert evidence == []


def test_similarity_comparison_observes_cancelled_controller() -> None:
    controller = CancellationController()
    controller.cancel()
    left = MarkdownDocument(
        "left.md",
        "bidder",
        "Left",
        "",
        ["A sufficiently long paragraph for comparison."],
    )
    right = MarkdownDocument(
        "right.md",
        "bidder",
        "Right",
        "",
        ["A sufficiently long paragraph for comparison."],
    )

    with pytest.raises(CancelledError):
        similar_paragraph_pairs(left, right, controller)


def test_upload_rejects_non_markdown_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("notes.txt", b"not markdown", "text/plain"))],
    )
    assert response.status_code == 400
    assert "Only Markdown" in response.json()["detail"]


def test_uppercase_markdown_upload_is_discoverable(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("BID.MD", b"# Bid", "text/markdown"))],
    )

    assert response.status_code == 200
    assert response.json()["upload_count"] == 1
    assert (tmp_path / "tasks" / task_id / "uploads" / "BID.md").exists()


def test_duplicate_upload_name_is_rejected_without_overwrite(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    first = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("bid.md", b"original", "text/markdown"))],
    )
    second = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("bid.md", b"replacement", "text/markdown"))],
    )

    stored = (tmp_path / "tasks" / task_id / "uploads" / "bid.md").read_text(encoding="utf-8")
    assert first.status_code == 200
    assert second.status_code == 409
    assert stored == "original"


def test_invalid_upload_batch_is_atomic(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[
            ("files", ("good.md", b"# Good", "text/markdown")),
            ("files", ("bad.txt", b"bad", "text/plain")),
        ],
    )
    state = client.get(f"/api/tasks/{task_id}").json()

    assert response.status_code == 400
    assert state["upload_count"] == 0
    assert list((tmp_path / "tasks" / task_id / "uploads").iterdir()) == []


def test_upload_count_limit_is_rejected(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_upload_files=1)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[
            ("files", ("first.md", b"# First", "text/markdown")),
            ("files", ("second.md", b"# Second", "text/markdown")),
        ],
    )

    assert response.status_code == 413
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0


def test_upload_size_limit_is_rejected_without_partial_file(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_upload_file_bytes=4)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("large.md", b"12345", "text/markdown"))],
    )

    assert response.status_code == 413
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "tasks" / task_id / "uploads").iterdir()) == []


def test_upload_request_size_limit_is_rejected_before_persisting(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        max_upload_file_bytes=1024,
        max_upload_request_bytes=32,
    )
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("large.md", b"12345", "text/markdown"))],
    )

    assert response.status_code == 413
    assert "Upload request exceeds" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "tasks" / task_id / "uploads").iterdir()) == []


def test_upload_request_size_limit_is_enforced_from_streamed_bytes(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        max_upload_file_bytes=1024,
        max_upload_request_bytes=8,
    )
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[
            ("files", ("first.md", b"12345", "text/markdown")),
            ("files", ("second.md", b"67890", "text/markdown")),
        ],
        headers={"content-length": "not-a-number"},
    )

    assert response.status_code == 413
    assert "Upload request exceeds" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "tasks" / task_id / "uploads").iterdir()) == []


def test_upload_rejects_overlong_filename_without_persisting(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    filename = f"{'a' * MAX_FILENAME_BYTES}.md"

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", (filename, b"# Too long", "text/markdown"))],
    )

    assert response.status_code == 400
    assert "filename exceeds" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "tasks" / task_id / "uploads").iterdir()) == []


def test_upload_accepts_filename_at_length_limit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    filename = f"{'a' * (MAX_FILENAME_BYTES - len('.md'))}.md"

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", (filename, b"# Limit", "text/markdown"))],
    )

    assert response.status_code == 200
    assert response.json()["upload_count"] == 1
    assert (tmp_path / "tasks" / task_id / "uploads" / filename).exists()


def test_message_without_uploads_requests_input(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    assert state["status"] == "needs_input"
    assert state["needs_input"]["required_file_type"] == "markdown"
    assert state["runs"][0]["status"] == "needs_input"
    assert state["runs"][0]["needs_input"]["required_file_type"] == "markdown"
    assert state["messages"][0]["run_id"] == state["runs"][0]["id"]


def test_simple_chat_uses_deepseek_extension_point(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    assert state["status"] == "complete"
    assert "DEEPSEEK_API_KEY" in state["messages"][-1]["content"]


def test_messages_and_events_from_new_runs_carry_run_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    run_id = state["runs"][0]["id"]
    run_events = [
        event
        for event in state["events"]
        if event["type"] in {"user_message_received", "run_manifest_created", "chat_completed"}
    ]

    assert state["active_run_id"] is None
    assert state["run_count"] == 1
    assert {message["run_id"] for message in state["messages"]} == {run_id}
    assert run_events
    assert {event["run_id"] for event in run_events} == {run_id}


def test_env_file_loader_reads_backend_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY='from-file'\n", encoding="utf-8")

    load_env_file(env_path)

    assert os.environ["DEEPSEEK_API_KEY"] == "from-file"


def test_workspace_run_tests_rejects_unlisted_commands(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path, PermissionPolicy(tmp_path), None)

    with pytest.raises(PermissionError, match="allowlist"):
        tools.run_tests([sys.executable, "-c", "print('outside allowlist')"])


def test_runtime_command_cancel_terminates_process(tmp_path: Path) -> None:
    controller = CancellationController()
    outcome: dict[str, str] = {}

    def run_command() -> None:
        try:
            run_cancellable_command(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                cwd=str(tmp_path),
                timeout=120,
                controller=controller,
            )
        except RuntimeError as exc:
            outcome["error"] = str(exc)

    thread = Thread(target=run_command)
    thread.start()
    time.sleep(0.2)
    controller.cancel()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert "cancel" in outcome["error"].lower()


def test_fetch_url_tool_is_not_exposed(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path, PermissionPolicy(tmp_path), None)

    assert not hasattr(tools, "fetch_url")


def test_tavily_search_observes_cancelled_controller_before_http_request(tmp_path: Path) -> None:
    controller = CancellationController()
    controller.cancel()
    tools = WorkspaceTools(tmp_path, PermissionPolicy(tmp_path), "test-key", controller)

    with patch("app.tools.httpx.post") as post, pytest.raises(RuntimeError, match="cancelled"):
        tools.tavily_search("query")

    post.assert_not_called()


def test_task_events_endpoint_supports_incremental_reads(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    events = client.get(f"/api/tasks/{task_id}/events").json()
    first_id = events[0]["id"]
    cast(FastAPI, client.app).state.storage.append_event(task_id, "second", "Second event", {})

    summary = client.get(f"/api/tasks/{task_id}?include_events=false").json()
    incremental = client.get(f"/api/tasks/{task_id}/events?after_id={first_id}").json()

    assert summary["events"] == []
    assert [event["type"] for event in incremental] == ["second"]


def test_read_events_ignores_partial_jsonl_tail(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    storage = app.state.storage
    second = storage.append_event(task_id, "second", "Second event", {})
    events_path = tmp_path / "tasks" / task_id / "logs" / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write('{"id": "partial"')

    events = storage.read_events(task_id)
    response = client.get(f"/api/tasks/{task_id}/events?after_id={second.id}")

    assert [event.type for event in events][-1] == "second"
    assert response.status_code == 200
    assert response.json() == []


def test_legacy_task_without_runs_synthesizes_readable_legacy_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    storage = app.state.storage
    state = storage.create_task(None, "deepseek-reasoner")
    task_id = state.task_id
    storage.write_text(task_id, "artifacts/report.html", "<html>legacy</html>")
    state_path = tmp_path / "tasks" / task_id / "state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["status"] = "complete"
    data["messages"] = [
        {"role": "user", "content": "旧任务消息", "created_at": data["created_at"]}
    ]
    data.pop("runs", None)
    data.pop("active_run_id", None)
    data.pop("run_count", None)
    state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    restored = client.get(f"/api/tasks/{task_id}").json()
    artifact = client.get(f"/api/tasks/{task_id}/runs/legacy/artifacts/report.html")

    assert restored["runs"][0]["id"] == "legacy"
    assert restored["runs"][0]["artifact_names"] == ["report.html"]
    assert restored["messages"][0]["run_id"] == "legacy"
    assert artifact.status_code == 200
    assert "legacy" in artifact.text


def test_task_storage_resolves_relative_task_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    storage = TaskStorage(Path("tasks"))

    state = storage.create_task(None, "deepseek-reasoner")

    assert storage.task_root == (tmp_path / "tasks").resolve()
    assert storage.task_dir(state.task_id).exists()


def test_provider_router_rejects_unimplemented_registry_provider(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    monkeypatch.setattr(
        "app.model_provider.MODEL_REGISTRY",
        [
            {
                "id": "other-model",
                "label": "Other Model",
                "provider": "other",
                "supports_files": False,
                "supports_images": False,
            }
        ],
    )

    with pytest.raises(ValueError, match="Unsupported model providers"):
        ProviderRouter(settings)


def test_create_app_rejects_explicit_multi_worker_runtime(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    with pytest.raises(RuntimeError, match="in-process task runners"):
        create_app(settings)


def test_model_reasoning_observes_cancellation(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    provider = DeepSeekProvider(settings)
    controller = CancellationController()
    outcome: dict[str, str] = {}

    async def slow_chat(_prompt: str, _model: str) -> str:
        await asyncio.sleep(10)
        return "late"

    def run_reasoning() -> None:
        try:
            with patch.object(provider, "_chat_http_async", side_effect=slow_chat):
                provider.reason("prompt", "deepseek-reasoner", controller)
        except RuntimeError as exc:
            outcome["error"] = str(exc)

    thread = Thread(target=run_reasoning)
    thread.start()
    time.sleep(0.2)
    controller.cancel()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert "cancel" in outcome["error"].lower()


def test_simple_chat_cancel_does_not_overwrite_cancelled_state(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "tasks",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "tasks",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    async def slow_chat(_message: str, _model: str) -> str:
        await asyncio.sleep(10)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_async", side_effect=slow_chat):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        time.sleep(0.2)
        cancelled = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"
        time.sleep(0.4)
        state = client.get(f"/api/tasks/{task_id}").json()

    assert state["status"] == "cancelled"


def test_cancel_racing_with_completion_preserves_complete_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    storage = app.state.storage
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    complete_event = Event()
    release_event = Event()
    original_append_event = storage.append_event

    def delayed_append_event(
        event_task_id: str,
        event_type: str,
        message: str,
        payload: dict | None = None,
        **kwargs,
    ):
        if event_task_id == task_id and event_type == "chat_completed":
            complete_event.set()
            release_event.wait(timeout=3)
        return original_append_event(event_task_id, event_type, message, payload, **kwargs)

    with patch.object(storage, "append_event", side_effect=delayed_append_event):
        response = client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        assert response.status_code == 200
        assert complete_event.wait(timeout=2)
        cancelled = client.post(f"/api/tasks/{task_id}/cancel")
        release_event.set()

    state = wait_for_terminal_status(client, task_id)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "complete"
    assert state["status"] == "complete"
    assert state["messages"][-1]["role"] == "assistant"


def test_cancel_complete_task_preserves_terminal_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    assert state["status"] == "complete"

    cancelled = client.post(f"/api/tasks/{task_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "complete"


def test_cancel_idle_task_preserves_idle_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    cancelled = client.post(f"/api/tasks/{task_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "idle"


TENDER_DOC = """# 招标文件

本项目要求投标人必须具备市政工程资质。
投标方案应说明质量保证措施、工期计划、人员配置和主要设备。
报价不得出现异常一致的分项报价。
"""

BIDDER_A = """# 甲方建设有限公司投标文件

投标人：甲方建设有限公司
作者：shared-user

## 技术方案
本项目将建立三级质量控制机制，采用每日巡检、周报复核和问题闭环整改方式，确保施工质量满足招标要求。

## 报价
总价：1000000元
分项一：230000元
分项二：450000元

联系人：张伟
目录
"""

BIDDER_B = """# 乙方建设有限公司投标文件

投标人：乙方建设有限公司
作者：shared-user

## 技术方案
本项目将建立三级质量控制机制，采用每日巡检、周报复核和问题闭环整改方式，确保施工质量满足招标要求。

## 报价
总价：1000000元
分项一：230000元
分项二：450000元

联系人：张伟
目录
"""

BIDDER_C = """# 丙方建设有限公司投标文件

投标人：丙方建设有限公司
作者：third-user

## 技术方案
本项目采用独立实施方案，强调人员安全培训和材料进场验收。

## 报价
总价：1130000元
分项一：250000元
分项二：470000元

联系人：李雷
未响应
"""
