from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.deep_agent_runtime as deep_agent_runtime
from app.agent_profiles import BID_MULTI_AGENT_PROFILE_ID, DEFAULT_AGENT_PROFILE_ID
from app.analysis import (
    CancelledError,
    MarkdownDocument,
    classify_documents,
    inspect_quotation_similarity,
    inspect_template_traces,
    normalize_evidence,
    similar_paragraph_pairs,
)
from app.main import create_app
from app.model_provider import DeepSeekProvider, ProviderRouter
from app.permissions import PermissionPolicy
from app.runner import summarize_search_sources
from app.runtime import CancellationController, run_cancellable_command
from app.schemas import MAX_MESSAGE_CHARS
from app.settings import Settings, load_env_file, read_list_env
from app.storage import MAX_FILENAME_BYTES, TaskStorage
from app.tools import WorkspaceTools


def make_client(
    tmp_path: Path,
    *,
    access_token: str | None = None,
    tavily_api_key: str | None = None,
    max_upload_files: int = 10,
    max_upload_file_bytes: int = 10 * 1024 * 1024,
    max_upload_request_bytes: int = 101 * 1024 * 1024,
    max_json_request_bytes: int = 64 * 1024,
    cors_origins: tuple[str, ...] = ("http://localhost:3001", "http://127.0.0.1:3001"),
    client_host: str | None = None,
) -> TestClient:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=tavily_api_key,
        workspace_root=tmp_path / "sessions",
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


class StubHTTPResponse:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.data


def wait_for_terminal_status(client: TestClient, task_id: str) -> dict:
    for _ in range(80):
        state = client.get(f"/api/tasks/{task_id}").json()
        if state["status"] in {"complete", "failed", "cancelled", "needs_input"}:
            runner = cast(FastAPI, client.app).state.runner
            if runner.is_running(task_id):
                time.sleep(0.05)
                continue
            return client.get(f"/api/tasks/{task_id}").json()
        time.sleep(0.05)
    raise AssertionError("Task did not finish")


def tool_names(tools: list[Any]) -> set[str]:
    return {tool.__name__ for tool in tools}


def reasoning_events_for_run(
    state: dict[str, Any],
    run_id: str,
    *,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    events = [
        event
        for event in state["events"]
        if event["type"] == "reasoning_trace" and event.get("run_id") == run_id
    ]
    if phase is not None:
        events = [event for event in events if event["payload"].get("phase") == phase]
    return events


def assert_run_has_reasoning(
    state: dict[str, Any],
    *,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    run_id = state["runs"][0]["id"]
    events = reasoning_events_for_run(state, run_id, phase=phase)
    assert events
    return events


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
    reasoning_events = [event for event in state["events"] if event["type"] == "reasoning_trace"]
    assert reasoning_events
    assert {event["run_id"] for event in reasoning_events} == {state["runs"][0]["id"]}
    reasoning_phases = {event["payload"]["phase"] for event in reasoning_events}
    assert {"plan", "observe", "decide", "final_summary"}.issubset(reasoning_phases)
    assert not any(
        event["payload"].get("agent_id") == "task-run"
        and event["payload"].get("phase") == "final_summary"
        for event in reasoning_events
    )
    assert any(event["type"] == "task_completed" for event in state["events"])
    assert any(
        event["type"] == "plan_created" and event["message"] == "已生成执行计划。"
        for event in state["events"]
    )
    assert any(
        event["type"] == "task_completed" and event["message"] == "任务已完成。"
        for event in state["events"]
    )

    task_dir = tmp_path / "sessions" / task_id
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
    expected_selected_uploads = [
        "bidder-a.md",
        "bidder-b.md",
        "bidder-c.md",
        "tender.md",
    ]
    assert run_manifest["mode"] == "auto"
    assert run_manifest["intent"]["name"] == "document_analysis"
    assert run_manifest["intent"]["route"] == "document_analysis"
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "task_uploads"}
    assert run_manifest["selected_uploads"] == expected_selected_uploads
    assert [item["filename"] for item in run_manifest["inputs"]] == expected_selected_uploads
    assert {item["source_format"] for item in run_manifest["inputs"]} == {"markdown"}
    assert all(item["size_bytes"] == item["bytes"] for item in run_manifest["inputs"])
    input_manifest = json.loads(
        (task_dir / "artifacts" / "input-manifest.json").read_text(encoding="utf-8")
    )
    assert {item["filename"] for item in input_manifest} == {
        "tender.md",
        "bidder-a.md",
        "bidder-b.md",
        "bidder-c.md",
    }
    assert {item["source_format"] for item in input_manifest} == {"markdown"}
    assert sum(1 for item in input_manifest if item["role"] == "bidder") == 3
    evidence = json.loads((task_dir / "artifacts" / "evidence.json").read_text(encoding="utf-8"))
    required_evidence_keys = {
        "category",
        "severity",
        "title",
        "description",
        "bidders",
        "pair",
        "locations",
        "requirement_reference",
        "confidence",
        "source_agent",
        "rationale_summary",
    }
    assert evidence
    assert all(required_evidence_keys.issubset(item) for item in evidence)
    assert all(len(item["pair"]) == 2 for item in evidence)
    assert all(0 <= item["confidence"] <= 1 for item in evidence)
    expected_pairs = {
        tuple(sorted(("甲方建设有限公司", "乙方建设有限公司"))),
        tuple(sorted(("甲方建设有限公司", "丙方建设有限公司"))),
        tuple(sorted(("乙方建设有限公司", "丙方建设有限公司"))),
    }
    assert {tuple(item["pair"]) for item in evidence} >= expected_pairs
    orchestration_events = [
        event for event in state["events"] if event["type"] == "orchestration_decision"
    ]
    assert orchestration_events
    assert orchestration_events[-1]["payload"]["strategy"] == "multi_agent"
    assert orchestration_events[-1]["payload"]["bidder_count"] == 3
    assert "execution_mode" not in orchestration_events[-1]["payload"]

    report = client.get(f"/api/tasks/{task_id}/artifacts/report.html")
    assert report.status_code == 200
    assert "投标人对比视图" in report.text
    assert 'data-severity="high"' in report.text or 'data-severity="medium"' in report.text


def test_normalized_evidence_adds_no_finding_records_for_uncovered_pairs() -> None:
    bidder_docs = [
        MarkdownDocument("a.md", "bidder", "甲公司", "", []),
        MarkdownDocument("b.md", "bidder", "乙公司", "", []),
        MarkdownDocument("c.md", "bidder", "丙公司", "", []),
    ]

    evidence = normalize_evidence([], bidder_docs)

    assert {tuple(item["pair"]) for item in evidence} == {
        tuple(sorted(("甲公司", "乙公司"))),
        tuple(sorted(("甲公司", "丙公司"))),
        tuple(sorted(("乙公司", "丙公司"))),
    }
    assert all(item["category"] == "pair_comparison_coverage" for item in evidence)
    assert all(item["source_agent"] == "deterministic-normalizer" for item in evidence)


def test_reasoning_trace_does_not_expose_prompt_upload_content_or_private_paths(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-reasoner"}).json()
    task_id = created["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        (
            "files",
            (
                "bidder-a.md",
                (BIDDER_A + "\nSECRET_DOC_CANARY_123").encode("utf-8"),
                "text/markdown",
            ),
        ),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={
            "message": (
                "帮我检查是否有串标围标嫌疑 RAW_PROMPT_CANARY_456 "
                "Authorization: Bearer AUTH_HEADER_CANARY_789"
            ),
            "model": "deepseek-reasoner",
        },
    )
    assert response.status_code == 200
    state = wait_for_terminal_status(client, task_id)
    reasoning_events = [event for event in state["events"] if event["type"] == "reasoning_trace"]
    serialized_reasoning = json.dumps(
        [{"message": event["message"], "payload": event["payload"]} for event in reasoning_events],
        ensure_ascii=False,
    )

    assert reasoning_events
    assert "SECRET_DOC_CANARY_123" not in serialized_reasoning
    assert "RAW_PROMPT_CANARY_456" not in serialized_reasoning
    assert "AUTH_HEADER_CANARY_789" not in serialized_reasoning
    assert str(tmp_path) not in serialized_reasoning


def test_document_analysis_tool_results_do_not_persist_upload_body(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)
    created = client.post("/api/tasks", json={"model": "deepseek-reasoner"}).json()
    task_id = created["task_id"]
    canary = "SECRET_DOC_CANARY_TOOL_RESULT_123"
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", (BIDDER_A + f"\n{canary}").encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    assert response.status_code == 200
    state = wait_for_terminal_status(client, task_id)
    tool_result_events = [event for event in state["events"] if event["type"] == "tool_result"]
    serialized_events = json.dumps(state["events"], ensure_ascii=False)

    assert state["status"] == "complete"
    assert tool_result_events
    assert canary not in serialized_events
    for event in tool_result_events:
        summary = event["payload"]["summary"]
        assert "preview" not in summary


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
    first_run_dir = tmp_path / "sessions" / task_id / "artifacts" / "runs" / first_run_id
    report_before = (first_run_dir / "report.html").read_bytes()
    evidence_before = (first_run_dir / "evidence.json").read_bytes()

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "请重新总结当前报告", "model": "deepseek-reasoner"},
    )
    second_state = wait_for_terminal_status(client, task_id)
    second_run_id = second_state["runs"][1]["id"]
    second_manifest = json.loads(
        (tmp_path / "sessions" / task_id / "artifacts" / "runs" / second_run_id / "run.json").read_text(
            encoding="utf-8"
        )
    )

    assert response.status_code == 200
    assert second_state["status"] == "complete"
    assert second_state["run_count"] == 2
    assert second_run_id != first_run_id
    assert (first_run_dir / "report.html").read_bytes() == report_before
    assert (first_run_dir / "evidence.json").read_bytes() == evidence_before
    expected_selected_uploads = [
        "bidder-a.md",
        "bidder-b.md",
        "tender.md",
    ]
    assert second_manifest["intent"]["name"] == "continue_with_uploads"
    assert second_manifest["intent"]["route"] == "document_analysis"
    assert second_manifest["input_scope"] == {"requested": "auto", "resolved": "task_uploads"}
    assert second_manifest["selected_uploads"] == expected_selected_uploads
    assert [item["filename"] for item in second_manifest["inputs"]] == expected_selected_uploads
    assert {item["source_format"] for item in second_manifest["inputs"]} == {"markdown"}
    assert all(message["run_id"] for message in second_state["messages"])


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("今天天气怎么样？", "weather"),
        ("帮我搜索一下本周建筑行业新闻", "search"),
        ("你好，帮我写一句欢迎语", "chat"),
    ],
)
def test_auto_with_existing_uploads_routes_non_document_messages_to_chat(
    tmp_path: Path, message: str, expected_intent: str
) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": message, "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    state = client.get(f"/api/tasks/{task_id}").json()
    task_dir = tmp_path / "sessions" / task_id
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert state["artifacts"] == []
    assert run_manifest["intent"]["name"] == expected_intent
    assert run_manifest["intent"]["route"] in {"chat", "search"}
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "none"}
    assert run_manifest["inputs"] == []
    assert run_manifest["selected_uploads"] == []
    assert [item["filename"] for item in run_manifest["available_uploads"]] == [
        "bidder-a.md",
        "bidder-b.md",
        "tender.md",
    ]
    assert any(event["type"] in {"chat_completed", "search_completed"} for event in state["events"])
    assert not any(event["type"] == "plan_created" for event in state["events"])
    assert not (task_dir / "plan.json").exists()


def test_search_with_document_words_does_not_reuse_existing_uploads(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我搜索最新招标公告", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    state = client.get(f"/api/tasks/{task_id}").json()
    task_dir = tmp_path / "sessions" / task_id
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert run_manifest["intent"]["route"] == "search"
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "none"}
    assert run_manifest["selected_uploads"] == []
    assert run_manifest["inputs"] == []
    assert any(event["type"] == "search_completed" for event in state["events"])
    assert not any(event["type"] == "plan_created" for event in state["events"])
    assert not any(event["type"] == "file_tool_audit" for event in state["events"])
    assert not (task_dir / "plan.json").exists()


def test_search_synthesizes_final_answer_after_tool_result(tmp_path: Path) -> None:
    client = make_client(tmp_path, tavily_api_key="test-tavily-key")
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    source_url = "http://www.weather.com.cn/weather15d/101121701.shtml"
    model_markdown_url = "https://example.com/home/user/page"
    unsafe_model_url = "http://%31%32%37.0.0.1/internal"
    localhost_model_url = "http://localhost/internal"
    tavily_payload = {
        "results": [
            {
                "title": "上海天气实况",
                "url": source_url,
                "content": "上海今天多云，午后有短时小雨，气温 18 到 23 摄氏度。",
                "raw_content": "RAW_TAVILY_JSON_CANARY_SHOULD_NOT_APPEAR",
            },
            {
                "title": "上海空气质量",
                "url": "https://weather.example/air",
                "content": "空气质量良，东北风 3 级。",
            },
        ]
    }

    with (
        patch("app.tools.httpx.post", return_value=StubHTTPResponse(tavily_payload)),
        patch(
            "app.model_provider.ProviderRouter.chat",
            return_value=(
                "上海今天以多云为主，午后可能有短时小雨，出门建议带伞。\n\n"
                f"关键来源：[上海天气实况]({source_url})；"
                f"[路径形式来源]({model_markdown_url})；"
                f"[本机来源]({unsafe_model_url})；[localhost]({localhost_model_url})；"
                "www.localhost/admin；www.example.com/weather?token=secret；admin@example.com；"
                "[引用式本机][local-ref]\n\n[local-ref]: http://localhost/ref"
            ),
        ) as provider_chat,
    ):
        response = client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "上海今天的天气怎么样？", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    run_id = state["runs"][0]["id"]
    run_event_types = [
        event["type"] for event in state["events"] if event.get("run_id") == run_id
    ]
    positions = {event_type: run_event_types.index(event_type) for event_type in run_event_types}
    serialized_events = json.dumps(state["events"], ensure_ascii=False)

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
    assert "上海今天以多云为主" in state["messages"][-1]["content"]
    assert source_url in state["messages"][-1]["content"]
    assert model_markdown_url in state["messages"][-1]["content"]
    assert unsafe_model_url not in state["messages"][-1]["content"]
    assert localhost_model_url not in state["messages"][-1]["content"]
    assert "http://localhost/ref" not in state["messages"][-1]["content"]
    assert "www.localhost/admin" not in state["messages"][-1]["content"]
    assert "www.example.com/weather?token=secret" not in state["messages"][-1]["content"]
    assert "admin@example.com" not in state["messages"][-1]["content"]
    assert "[local-ref]:" not in state["messages"][-1]["content"]
    assert "<redacted-url>" in state["messages"][-1]["content"]
    assert "(<redacted-url>)" not in state["messages"][-1]["content"]
    assert "htt<absolute-path>" not in state["messages"][-1]["content"]
    assert "https://example.com<absolute-path>" not in state["messages"][-1]["content"]
    assert "参考来源" not in state["messages"][-1]["content"]
    assert "RAW_TAVILY_JSON_CANARY_SHOULD_NOT_APPEAR" not in state["messages"][-1]["content"]
    assert "RAW_TAVILY_JSON_CANARY_SHOULD_NOT_APPEAR" not in serialized_events
    assert "<absolute-path>" not in serialized_events
    assert positions["search_tool_call"] < positions["search_tool_result"]
    assert positions["search_tool_result"] < positions["answer_generation_started"]
    assert positions["answer_generation_started"] < positions["search_synthesis_completed"]
    assert positions["search_tool_result"] < positions["search_synthesis_completed"]
    assert positions["search_synthesis_completed"] < positions["search_completed"]
    final_reasoning = reasoning_events_for_run(state, run_id, phase="final_summary")
    assert final_reasoning
    assert (
        positions["search_synthesis_completed"]
        < run_event_types.index("reasoning_trace")
        < positions["search_completed"]
    )
    assert "2 个安全来源" in final_reasoning[-1]["payload"]["summary"]
    assert final_reasoning[-1]["payload"]["agent_id"] == "task-run"
    synthesis_events = [
        event for event in state["events"] if event["type"] == "search_synthesis_completed"
    ]
    run_manifest_event = next(
        event for event in state["events"] if event["type"] == "run_manifest_created"
    )
    orchestration_event = next(
        event for event in state["events"] if event["type"] == "orchestration_decision"
    )
    search_call_event = next(event for event in state["events"] if event["type"] == "search_tool_call")
    search_result_event = next(
        event for event in state["events"] if event["type"] == "search_tool_result"
    )
    answer_started_event = next(
        event for event in state["events"] if event["type"] == "answer_generation_started"
    )
    assert run_manifest_event["payload"]["live"]["kind"] == "status"
    assert run_manifest_event["payload"]["live"]["stage"] == "analyzing_intent"
    assert orchestration_event["payload"]["live"]["kind"] == "status"
    assert orchestration_event["payload"]["live"]["stage"] == "selecting_tool"
    assert search_call_event["payload"]["live"] == {
        "schema_version": 1,
        "kind": "tool_call",
        "stage": "using_tool",
        "agent_name": "search_agent",
        "tool_name": "tavily_search",
        "tool_call_id": "search_tool_1",
        "parameter_items": [
            {"key": "query", "value": "上海今天的天气怎么样？"},
            {"key": "max_results", "value": 5},
            {"key": "use_uploads", "value": False},
        ],
    }
    assert search_result_event["payload"]["live"] == {
        "schema_version": 1,
        "kind": "tool_result",
        "stage": "completed",
        "agent_name": "search_agent",
        "tool_name": "tavily_search",
        "tool_call_id": "search_tool_1",
        "result_status": "success",
        "result_count": 2,
    }
    assert answer_started_event["payload"]["live"] == {
        "schema_version": 1,
        "kind": "answer_status",
        "stage": "generating_answer",
        "agent_name": "search_agent",
    }
    assert synthesis_events[-1]["payload"]["used_model"] is True
    assert synthesis_events[-1]["payload"]["source_count"] == 2
    assert synthesis_events[-1]["payload"]["live"]["kind"] == "answer_status"
    assert synthesis_events[-1]["payload"]["live"]["stage"] == "completed"
    assert len(synthesis_events[-1]["payload"]["sources"]) <= 5
    assert set(synthesis_events[-1]["payload"]["sources"][0]) == {"title", "url", "snippet"}
    assert synthesis_events[-1]["payload"]["sources"][0]["url"] == source_url
    prompt = provider_chat.call_args.args[0]
    assert "上海天气实况" in prompt
    assert source_url in prompt
    assert "htt<absolute-path>" not in prompt
    assert "RAW_TAVILY_JSON_CANARY_SHOULD_NOT_APPEAR" not in prompt


def test_search_safe_url_summary_preserves_public_sources_and_drops_unsafe_links() -> None:
    safe_url = "https://weather.example/shanghai?day=today"
    safe_path_urls = [
        "https://example.com/home/user/page",
        "https://example.com/tmp/report",
        "https://example.com/C:/file.txt",
    ]
    sources = summarize_search_sources(
        {
            "results": [
                {
                    "title": "公共天气来源",
                    "url": safe_url,
                    "content": "公开天气摘要。",
                },
                {
                    "title": "本机来源",
                    "url": "http://localhost/internal",
                    "content": "不应保留链接。",
                },
                {
                    "title": "回环地址",
                    "url": "http://127.0.0.1/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "IPv6 回环",
                    "url": "http://[::1]/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "未指定地址",
                    "url": "http://0.0.0.0/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "整数回环地址",
                    "url": "http://2130706433/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "缩写回环地址",
                    "url": "http://127.1/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "十六进制回环地址",
                    "url": "http://0x7f.0.0.1/secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "单标签内网名",
                    "url": "http://intranet/secret",
                    "content": "不应保留链接。",
                },
            ]
        }
    )
    unsafe_sources = summarize_search_sources(
        {
            "results": [
                {
                    "title": "本地文件",
                    "url": "file:///C:/secret.txt",
                    "content": "不应保留链接。",
                },
                {
                    "title": "带凭据",
                    "url": "https://user:pass@example.com/weather",
                    "content": "不应保留链接。",
                },
                {
                    "title": "空用户名",
                    "url": "https://@example.com/weather",
                    "content": "不应保留链接。",
                },
                {
                    "title": "空用户名密码",
                    "url": "https://:@example.com/weather",
                    "content": "不应保留链接。",
                },
                {
                    "title": "带密钥参数",
                    "url": "https://example.com/weather?api_key=secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "分号查询参数",
                    "url": "https://example.com/weather?day=today;token=secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "分号路径参数",
                    "url": "https://example.com/weather;token=secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "片段密钥参数",
                    "url": "https://example.com/weather#access_token=secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "编码片段密钥参数",
                    "url": "https://example.com/weather#access%5Ftoken=secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "脚本链接",
                    "url": "javascript:alert(1)",
                    "content": "不应保留链接。",
                },
                {
                    "title": "数据链接",
                    "url": "data:text/plain,secret",
                    "content": "不应保留链接。",
                },
                {
                    "title": "夹带换行链接",
                    "url": "https://example.com/public\nhttp://localhost/admin",
                    "content": "不应保留链接。",
                },
            ]
        }
    )

    assert sources[0].url == safe_url
    assert all(source.url == "" for source in sources[1:])
    assert len(sources) == 5
    assert all(source.url == "" for source in unsafe_sources)

    for unsafe_local_url in [
        "http://2130706433/secret",
        "http://127.1/secret",
        "http://0x7f.0.0.1/secret",
        "http://intranet/secret",
        "http://%31%32%37.0.0.1/secret",
        "http://127.%30.0.1/secret",
        "http://%31%32%37.%30.%30.%31/secret",
        "https://example.com/public http://localhost/admin",
        "https://example.com/public\tpath",
    ]:
        [source] = summarize_search_sources(
            {"results": [{"title": "本地别名", "url": unsafe_local_url, "content": "不应保留链接。"}]}
        )
        assert source.url == "", unsafe_local_url

    for safe_path_url in safe_path_urls:
        [source] = summarize_search_sources(
            {"results": [{"title": "路径像本地目录", "url": safe_path_url, "content": "公开摘要。"}]}
        )
        assert source.url == safe_path_url
        assert "<absolute-path>" not in source.url

    for sensitive_key in [
        "authorization",
        "auth",
        "auth_token",
        "access_token",
        "api-key",
        "apikey",
        "key",
        "secret",
        "password",
        "credential",
    ]:
        [source] = summarize_search_sources(
            {
                "results": [
                    {
                        "title": "敏感查询参数",
                        "url": f"https://example.com/weather?{sensitive_key}=secret",
                        "content": "不应保留链接。",
                    }
                ]
            }
        )
        assert source.url == "", sensitive_key


def test_search_missing_provider_uses_bounded_source_summary(tmp_path: Path) -> None:
    client = make_client(tmp_path, tavily_api_key="test-tavily-key")
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    tavily_payload = {
        "results": [
            {
                "title": "上海天气",
                "url": "https://weather.example/shanghai",
                "content": "上海今日阴到多云，最高 22 摄氏度。",
                "raw_content": "RAW_PROVIDER_FALLBACK_CANARY",
            }
        ]
    }

    with patch("app.tools.httpx.post", return_value=StubHTTPResponse(tavily_payload)):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "查一下上海天气", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    synthesis_event = next(
        event for event in state["events"] if event["type"] == "search_synthesis_completed"
    )
    final_message = state["messages"][-1]
    serialized = json.dumps(state["events"], ensure_ascii=False)

    assert state["status"] == "complete"
    assert final_message["level"] == "warning"
    assert "模型合成未启用" in final_message["content"]
    assert "上海今日阴到多云" in final_message["content"]
    assert "RAW_PROVIDER_FALLBACK_CANARY" not in final_message["content"]
    assert "RAW_PROVIDER_FALLBACK_CANARY" not in serialized
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert "模型合成=未使用" in risk_events[-1]["payload"]["summary"]
    assert synthesis_event["payload"]["used_model"] is False
    assert synthesis_event["payload"]["warning_code"] == "missing_provider_key"


def test_search_model_failure_uses_bounded_source_summary(tmp_path: Path) -> None:
    client = make_client(tmp_path, tavily_api_key="test-tavily-key")
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    tavily_payload = {
        "results": [
            {
                "title": "上海天气",
                "url": "https://weather.example/shanghai",
                "content": "上海今日小雨转多云，最高 21 摄氏度。",
            }
        ]
    }

    with (
        patch("app.tools.httpx.post", return_value=StubHTTPResponse(tavily_payload)),
        patch("app.model_provider.ProviderRouter.chat", side_effect=ValueError("provider down")),
    ):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "查一下上海天气", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    synthesis_event = next(
        event for event in state["events"] if event["type"] == "search_synthesis_completed"
    )

    assert state["status"] == "complete"
    assert state["messages"][-1]["level"] == "warning"
    assert "模型合成暂不可用" in state["messages"][-1]["content"]
    assert "上海今日小雨转多云" in state["messages"][-1]["content"]
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert risk_events[-1]["payload"]["evidence_refs"] == ["model_synthesis_failed"]
    assert synthesis_event["payload"]["used_model"] is False
    assert synthesis_event["payload"]["warning_code"] == "model_synthesis_failed"


def test_search_without_tavily_key_has_risk_reasoning_trace(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "查一下上海天气", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)

    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert state["status"] == "complete"
    assert state["messages"][-1]["level"] == "warning"
    assert "联网搜索未启用" in state["messages"][-1]["content"]
    assert "missing_tavily_key" in risk_events[-1]["payload"]["evidence_refs"]


def test_search_without_results_has_risk_reasoning_trace(tmp_path: Path) -> None:
    client = make_client(tmp_path, tavily_api_key="test-tavily-key")
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    with patch("app.tools.httpx.post", return_value=StubHTTPResponse({"results": []})):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "查一下上海天气", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert state["status"] == "complete"
    assert "没有检索到可用结果" in state["messages"][-1]["content"]
    assert "安全来源数 0" in risk_events[-1]["payload"]["summary"]


def test_legacy_input_scope_none_no_longer_overrides_model_owned_file_routing(
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

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={
            "message": "帮我检查是否有串标围标嫌疑",
            "model": "deepseek-reasoner",
            "input_scope": "none",
        },
    )
    state = wait_for_terminal_status(client, task_id)
    state = client.get(f"/api/tasks/{task_id}").json()
    task_dir = tmp_path / "sessions" / task_id
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert {artifact["name"] for artifact in state["artifacts"]} >= {"report.html"}
    assert run_manifest["intent"]["route"] == "document_analysis"
    assert run_manifest["intent"]["reason"] == "document_analysis_marker_deep_agent_unavailable_fallback"
    assert run_manifest["input_scope"] == {"requested": "none", "resolved": "task_uploads"}
    assert [item["filename"] for item in run_manifest["inputs"]] == [
        "bidder-a.md",
        "bidder-b.md",
        "tender.md",
    ]
    assert run_manifest["selected_uploads"] == [
        "bidder-a.md",
        "bidder-b.md",
        "tender.md",
    ]
    assert any(event["type"] == "deep_agent_fallback" for event in state["events"])
    assert any(event["type"] == "plan_created" for event in state["events"])
    assert (task_dir / "plan.json").exists()


def test_auto_file_aware_prompt_uses_deep_agent_available_uploads_without_forced_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_factory(
        *,
        model: str,
        tools: list[Any],
        system_prompt: str,
        subagents: list[dict[str, Any]],
        backend: Any,
    ) -> Any:
        assert model == "deepseek-reasoner"
        assert "是否列出、检索或读取" in system_prompt
        assert "任务需要时才读取" in subagents[0]["system_prompt"]
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(payload: dict[str, Any], **_kwargs: Any) -> dict[str, str]:
            assert payload["messages"][0]["content"] == "帮我检查是否有串标围标嫌疑"
            tool_map["write_file"]("outputs/summary.md", "未读取上传文件")
            return {"content": "已按任务判断，本轮没有读取上传文件。"}

        return fake_agent

    monkeypatch.setattr(deep_agent_runtime, "_DEFAULT_AGENT_FACTORY", fake_factory)
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    state = client.get(f"/api/tasks/{task_id}").json()
    task_dir = tmp_path / "sessions" / task_id
    run_id = state["runs"][0]["id"]
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))
    audit_payloads = [
        event["payload"] for event in state["events"] if event["type"] == "file_tool_audit"
    ]
    activity_events = [
        event for event in state["events"] if event["type"] == "deep_agent_activity"
    ]
    serialized_events = json.dumps(
        [{"message": event["message"], "payload": event["payload"]} for event in state["events"]],
        ensure_ascii=False,
    )

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert state["messages"][-1]["content"] == "已按任务判断，本轮没有读取上传文件。"
    assert run_manifest["intent"]["route"] == "deep_agent"
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "task_uploads"}
    assert run_manifest["selected_uploads"] == ["bidder-a.md", "tender.md"]
    assert (task_dir / "agent_workspace" / "runs" / run_id / "uploads" / "tender.md").exists()
    assert [payload["operation"] for payload in audit_payloads] == ["write"]
    assert not any(payload["operation"] == "read" for payload in audit_payloads)
    assert activity_events
    assert {event["run_id"] for event in activity_events} == {run_id}
    assert all(event["payload"]["schema_version"] == 1 for event in activity_events)
    assert any(event["payload"]["phase"] == "file_operation" for event in activity_events)
    assert "DeepAgent 输出" not in serialized_events
    assert str(tmp_path) not in serialized_events
    assert any(event["type"] == "deep_agent_completed" for event in state["events"])
    assert not any(event["type"] == "deep_agent_fallback" for event in state["events"])


@pytest.mark.parametrize(
    "message",
    [
        "帮我检查是否有串标围标嫌疑",
        "继续根据刚才这些文件检查串标",
    ],
)
def test_auto_bid_prompt_selects_bid_multi_agent_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    captured_subagents: list[str] = []
    captured_subagent_tool_names: list[set[str]] = []

    def fake_factory(
        *,
        model: str,
        tools: list[Any],
        system_prompt: str,
        subagents: list[dict[str, Any]],
        backend: Any,
    ) -> Any:
        assert model == "deepseek-reasoner"
        assert "招投标多 Agent 分析" in system_prompt
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        captured_subagents.extend(str(item["name"]) for item in subagents)
        captured_subagent_tool_names.extend(tool_names(item["tools"]) for item in subagents)
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(payload: dict[str, Any], **_kwargs: Any) -> dict[str, str]:
            assert payload["messages"][0]["content"] == message
            tool_map["write_file"]("outputs/final-summary.md", "多 Agent 汇总")
            return {"content": "已使用多 Agent Profile 完成分析。"}

        return fake_agent

    monkeypatch.setattr(deep_agent_runtime, "_DEFAULT_AGENT_FACTORY", fake_factory)
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("tender.md", TENDER_DOC.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-a.md", BIDDER_A.encode("utf-8"), "text/markdown")),
        ("files", ("bidder-b.md", BIDDER_B.encode("utf-8"), "text/markdown")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": message, "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    task_dir = tmp_path / "sessions" / task_id
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))
    orchestration_payloads = [
        event["payload"] for event in state["events"] if event["type"] == "orchestration_decision"
    ]
    completion_payloads = [
        event["payload"] for event in state["events"] if event["type"] == "deep_agent_completed"
    ]

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert captured_subagents == [
        "document-classification-agent",
        "requirement-matching-agent",
        "bidder-pair-comparison-agent",
        "evidence-normalization-agent",
        "report-writing-agent",
    ]
    assert all(
        names == {"list_dir", "read_file", "write_file"}
        for names in captured_subagent_tool_names
    )
    assert run_manifest["agent_profile"]["id"] == BID_MULTI_AGENT_PROFILE_ID
    assert orchestration_payloads[-1]["chosen_profile_id"] == BID_MULTI_AGENT_PROFILE_ID
    assert orchestration_payloads[-1]["strategy"] == "multi_agent"
    assert orchestration_payloads[-1]["planned_subagents"] == captured_subagents
    assert completion_payloads[-1]["chosen_profile_id"] == BID_MULTI_AGENT_PROFILE_ID
    assert completion_payloads[-1]["agent_profile"]["id"] == BID_MULTI_AGENT_PROFILE_ID


def test_explicit_deep_agent_mode_uses_audited_runtime_without_document_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_factory(
        *,
        model: str,
        tools: list[Any],
        system_prompt: str,
        subagents: list[dict[str, Any]],
        backend: Any,
    ) -> Any:
        assert model == "deepseek-reasoner"
        assert "uploads/" in system_prompt
        assert subagents[0]["name"] == "file-record-agent"
        assert isinstance(backend, deep_agent_runtime.AuditedDeepAgentBackend)
        assert backend.audited is True
        tool_map = {tool.__name__: tool for tool in tools}

        def fake_agent(payload: dict[str, Any], **_kwargs: Any) -> dict[str, str]:
            assert payload["messages"][0]["content"] == "请用 DeepAgent 记录本轮输出"
            tool_map["write_file"]("outputs/summary.md", "DeepAgent 输出")
            return {"content": "DeepAgent 已完成本轮输出。"}

        return fake_agent

    monkeypatch.setattr(deep_agent_runtime, "_DEFAULT_AGENT_FACTORY", fake_factory)
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/messages",
        json={
            "message": "请用 DeepAgent 记录本轮输出",
            "model": "deepseek-reasoner",
            "mode": "deep_agent",
        },
    )
    state = wait_for_terminal_status(client, task_id)
    state = client.get(f"/api/tasks/{task_id}").json()
    task_dir = tmp_path / "sessions" / task_id
    run_id = state["runs"][0]["id"]
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert state["status"] == "complete"
    assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
    assert state["messages"][-1]["content"] == "DeepAgent 已完成本轮输出。"
    assert run_manifest["intent"]["route"] == "deep_agent"
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "none"}
    assert run_manifest["selected_uploads"] == []
    assert run_manifest["agent_profile"]["id"] == DEFAULT_AGENT_PROFILE_ID
    assert {artifact["name"] for artifact in state["artifacts"]} == {
        "deep-agent-summary.md"
    }
    assert (task_dir / "agent_workspace" / "runs" / run_id / "outputs" / "summary.md").exists()
    assert any(event["type"] == "file_tool_audit" for event in state["events"])
    deep_activity = [
        event for event in state["events"] if event["type"] == "deep_agent_activity"
    ]
    assert deep_activity
    assert {event["run_id"] for event in deep_activity} == {run_id}
    assert any(
        event["payload"].get("related_event_id")
        for event in deep_activity
        if event["payload"]["phase"] == "file_operation"
    )
    deep_reasoning = [
        event["payload"]
        for event in state["events"]
        if event["type"] == "reasoning_trace"
    ]
    assert {payload["phase"] for payload in deep_reasoning} >= {
        "plan",
        "observe",
        "final_summary",
    }
    assert not any(
        payload.get("agent_id") == "task-run" and payload.get("phase") == "final_summary"
        for payload in deep_reasoning
    )
    assert any(payload.get("source_event_id") for payload in deep_reasoning)
    assert any(event["type"] == "deep_agent_completed" for event in state["events"])
    assert not any(event["type"] == "plan_created" for event in state["events"])


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
    plan = json.loads((tmp_path / "sessions" / task_id / "plan.json").read_text(encoding="utf-8"))

    assert state["status"] == "complete", state.get("error")
    assert [item["role"] for item in plan["input_material_roles"]] == ["bidder", "bidder"]


def test_json_uploads_are_parsed_and_included_in_manifests(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    alpha = {
        "投标人": "Alpha Construction",
        "技术方案": "采用每日巡检、周报复核和问题闭环整改方式确保施工质量。",
        "报价": "1000000元",
        "分项一": "230000元",
    }
    beta = {
        "投标人": "Beta Construction",
        "技术方案": "采用每日巡检、周报复核和问题闭环整改方式确保施工质量。",
        "报价": "1000000元",
        "分项一": "230000元",
    }
    files = [
        ("files", ("alpha.json", json.dumps(alpha).encode("utf-8"), "application/json")),
        ("files", ("beta.json", json.dumps(beta).encode("utf-8"), "application/json")),
    ]
    upload = client.post(f"/api/tasks/{task_id}/files", files=files)
    assert upload.status_code == 200
    assert upload.json()["upload_count"] == 2

    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    task_dir = tmp_path / "sessions" / task_id
    run_manifest = json.loads((task_dir / "run.json").read_text(encoding="utf-8"))
    input_manifest = json.loads(
        (task_dir / "artifacts" / "input-manifest.json").read_text(encoding="utf-8")
    )
    plan = json.loads((task_dir / "plan.json").read_text(encoding="utf-8"))

    assert state["status"] == "complete", state.get("error")
    assert [item["filename"] for item in run_manifest["inputs"]] == ["alpha.json", "beta.json"]
    assert {item["source_format"] for item in run_manifest["inputs"]} == {"json"}
    assert all(item["relative_path"].startswith("uploads/") for item in run_manifest["inputs"])
    assert all(item["size_bytes"] == item["bytes"] for item in run_manifest["inputs"])
    assert {item["source_format"] for item in input_manifest} == {"json"}
    assert {item["relative_path"] for item in input_manifest} == {
        "uploads/alpha.json",
        "uploads/beta.json",
    }
    assert [item["source_format"] for item in plan["input_material_roles"]] == ["json", "json"]


def test_runtime_invalid_json_storage_drift_fails_with_filename(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    files = [
        ("files", ("alpha.json", b'{"bidder": "Alpha", "price": "1000000"}', "application/json")),
        ("files", ("beta.json", b'{"bidder": "Beta", "price": "1000000"}', "application/json")),
    ]
    assert client.post(f"/api/tasks/{task_id}/files", files=files).status_code == 200
    (tmp_path / "sessions" / task_id / "uploads" / "beta.json").write_text(
        '{"bidder": ', encoding="utf-8"
    )

    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)

    assert state["status"] == "failed"
    assert state["error"] == "JSON 文件 beta.json 无效：内容不是合法 JSON"
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert "JSON 文件 beta.json 无效" in risk_events[-1]["payload"]["summary"]


def test_failed_run_public_error_is_sanitized(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    private_path = f"{tmp_path}/secret.txt"
    raw_error = (
        f"provider failed at {private_path} with Authorization: Bearer AUTH_HEADER_CANARY_789"
    )

    with patch("app.model_provider.ProviderRouter.chat", side_effect=ValueError(raw_error)):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    failed_event = next(event for event in state["events"] if event["type"] == "task_failed")
    serialized_public_failure = json.dumps(
        {
            "error": state["error"],
            "event": failed_event,
            "reasoning": reasoning_events_for_run(state, state["runs"][0]["id"], phase="risk"),
        },
        ensure_ascii=False,
    )

    assert state["status"] == "failed"
    assert "AUTH_HEADER_CANARY_789" not in serialized_public_failure
    assert str(tmp_path) not in serialized_public_failure
    assert "Authorization:<redacted>" in serialized_public_failure
    assert "<absolute-path>/secret.txt" in serialized_public_failure


def test_upload_while_task_is_running_returns_conflict_without_persisting(
    tmp_path: Path,
) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    def slow_stream(_message: str, _model: str, _on_delta, _controller=None) -> str:
        for _ in range(200):
            if _controller is not None and _controller.is_cancelled():
                raise RuntimeError("模型调用已取消")
            time.sleep(0.05)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_stream", side_effect=slow_stream):
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
        assert not (tmp_path / "sessions" / task_id / "uploads" / "late.md").exists()
        assert not any(
            event["type"] == "file_uploaded"
            and event.get("payload", {}).get("filename") == "late.md"
            for event in state["events"]
        )
        client.post(f"/api/tasks/{task_id}/cancel")


def test_follow_up_message_is_rejected_while_run_is_active(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    def slow_stream(_message: str, _model: str, _on_delta, _controller=None) -> str:
        for _ in range(200):
            if _controller is not None and _controller.is_cancelled():
                raise RuntimeError("模型调用已取消")
            time.sleep(0.05)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_stream", side_effect=slow_stream):
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
    task_root = tmp_path / "sessions"
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
    assert "后端启动或重载" in state["error"]
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
    assert (tmp_path / "sessions" / task_id / "uploads" / "after-recovery.md").exists()


def test_task_api_rejects_nonlocal_client_without_token(tmp_path: Path) -> None:
    local_client = make_client(tmp_path)
    task_id = local_client.post("/api/tasks", json={}).json()["task_id"]
    remote_client = make_client(tmp_path, client_host="203.0.113.10")

    response = remote_client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 403


def test_task_api_accepts_valid_access_token_and_rejects_wrong_token(tmp_path: Path) -> None:
    token = "test-token"
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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
    origin = "http://192.0.2.10:3001"
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
            "Origin": "http://192.0.2.10:3001",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_origin_env_parser_trims_empty_items_and_trailing_slashes(monkeypatch) -> None:
    monkeypatch.setenv(
        "MYAGENT_CORS_ORIGINS",
        " http://localhost:3001/, , http://192.0.2.10:3001/ ",
    )

    origins = read_list_env("MYAGENT_CORS_ORIGINS", ("http://127.0.0.1:3001",))

    assert origins == ("http://localhost:3001", "http://192.0.2.10:3001")


def test_artifact_download_requires_and_accepts_access_token(tmp_path: Path) -> None:
    token = "test-token"
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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
    assert "投标人对比视图" in allowed.text
    assert unlisted.status_code == 404
    assert traversal.status_code in {400, 404}
    assert latest.status_code == 200
    assert latest.text == allowed.text


def test_run_history_and_artifacts_persist_across_app_restart(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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
    assert response.json()["detail"] == "请求参数校验失败，请检查输入内容。"
    assert state["status"] == "idle"
    assert state["messages"] == []
    assert not (tmp_path / "sessions" / task_id / "run.json").exists()
    assert not cast(FastAPI, client.app).state.runner.is_running(task_id)


def test_create_task_rejects_initial_message_over_length_limit(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/tasks",
        json={"message": "x" * (MAX_MESSAGE_CHARS + 1), "model": "deepseek-reasoner"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "请求参数校验失败，请检查输入内容。"
    assert list((tmp_path / "sessions").iterdir()) == []


def test_create_task_rejects_initial_message_without_persisting(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/tasks",
        json={"message": "hello", "model": "deepseek-reasoner"},
    )

    assert response.status_code == 400
    assert "不含初始消息" in response.json()["detail"]
    assert client.get("/api/tasks").json() == []
    assert list((tmp_path / "sessions").iterdir()) == []


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

    raw_error = (
        f"rate limit at {tmp_path}/private/customer.md with "
        "Authorization: Bearer AUTH_HEADER_CANARY_789 and SECRET_DOC_CANARY_123"
    )

    with patch("app.model_provider.ProviderRouter.reason", side_effect=RuntimeError(raw_error)):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    evidence = json.loads(
        (tmp_path / "sessions" / task_id / "artifacts" / "evidence.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "complete", state.get("error")
    assert evidence
    warning_events = [event for event in state["events"] if event["type"] == "model_warning"]
    assert warning_events
    serialized_warning = json.dumps(warning_events, ensure_ascii=False)
    assert "AUTH_HEADER_CANARY_789" not in serialized_warning
    assert "SECRET_DOC_CANARY_123" not in serialized_warning
    assert str(tmp_path) not in serialized_warning
    assert warning_events[-1]["payload"]["error_type"] == "RuntimeError"
    assert "<redacted-canary>" in serialized_warning
    assert "<absolute-path>/customer.md" in serialized_warning


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


def test_upload_rejects_unsupported_file_type(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("notes.txt", b"not markdown", "text/plain"))],
    )
    assert response.status_code == 400
    assert "仅支持上传 Markdown 或 JSON 文件" in response.json()["detail"]


def test_uppercase_markdown_upload_is_discoverable(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("BID.MD", b"# Bid", "text/markdown"))],
    )

    assert response.status_code == 200
    assert response.json()["upload_count"] == 1
    assert (tmp_path / "sessions" / task_id / "uploads" / "BID.md").exists()


def test_uppercase_json_upload_is_discoverable(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", ("DATA.JSON", b'{"ok": true}', "application/json"))],
    )

    assert response.status_code == 200
    assert response.json()["upload_count"] == 1
    assert (tmp_path / "sessions" / task_id / "uploads" / "DATA.json").exists()


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

    stored = (tmp_path / "sessions" / task_id / "uploads" / "bid.md").read_text(encoding="utf-8")
    assert first.status_code == 200
    assert second.status_code == 409
    assert stored == "original"


def test_duplicate_json_upload_name_is_rejected_case_insensitively(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[
            ("files", ("data.JSON", b'{"one": 1}', "application/json")),
            ("files", ("data.json", b'{"two": 2}', "application/json")),
        ],
    )

    assert response.status_code == 409
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


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
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


def test_invalid_json_upload_batch_is_atomic(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[
            ("files", ("good.md", b"# Good", "text/markdown")),
            ("files", ("bad.json", b'{"broken": ', "application/json")),
        ],
    )
    state = client.get(f"/api/tasks/{task_id}").json()

    assert response.status_code == 400
    assert response.json()["detail"] == "JSON 文件 bad.json 无效：内容不是合法 JSON"
    assert state["upload_count"] == 0
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


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
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


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
    assert "上传请求超过" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


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
    assert "上传请求超过" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


def test_upload_rejects_overlong_filename_without_persisting(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    filename = f"{'a' * MAX_FILENAME_BYTES}.md"

    response = client.post(
        f"/api/tasks/{task_id}/files",
        files=[("files", (filename, b"# Too long", "text/markdown"))],
    )

    assert response.status_code == 400
    assert "上传文件名超过" in response.json()["detail"]
    assert client.get(f"/api/tasks/{task_id}").json()["upload_count"] == 0
    assert list((tmp_path / "sessions" / task_id / "uploads").iterdir()) == []


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
    assert (tmp_path / "sessions" / task_id / "uploads" / filename).exists()


def test_message_without_uploads_requests_input(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "帮我检查是否有串标围标嫌疑", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    run_manifest = json.loads(
        (tmp_path / "sessions" / task_id / "run.json").read_text(encoding="utf-8")
    )

    assert state["status"] == "needs_input"
    assert run_manifest["intent"]["name"] == "document_analysis"
    assert run_manifest["intent"]["route"] == "document_analysis"
    assert run_manifest["input_scope"] == {"requested": "auto", "resolved": "none"}
    assert run_manifest["inputs"] == []
    assert run_manifest["selected_uploads"] == []
    assert state["needs_input"]["required_file_type"] == "markdown_or_json"
    assert state["runs"][0]["status"] == "needs_input"
    assert state["runs"][0]["needs_input"]["required_file_type"] == "markdown_or_json"
    assert state["messages"][0]["run_id"] == state["runs"][0]["id"]
    next_step_events = assert_run_has_reasoning(state, phase="next_step")
    assert next_step_events[-1]["payload"]["agent_id"] == "task-run"
    assert "补充输入" in next_step_events[-1]["payload"]["summary"]


def test_simple_chat_uses_deepseek_extension_point(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    client.post(
        f"/api/tasks/{task_id}/messages",
        json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
    )
    state = wait_for_terminal_status(client, task_id)
    assert state["status"] == "complete"
    assert "已选择 DeepSeek" in state["messages"][-1]["content"]
    assert "DEEPSEEK_API_KEY" in state["messages"][-1]["content"]
    assert state["messages"][-1]["level"] == "warning"
    warning_events = [event for event in state["events"] if event["type"] == "model_warning"]
    assert warning_events
    assert warning_events[-1]["level"] == "warning"
    assert warning_events[-1]["message"] == "模型服务配置提醒。"
    assert warning_events[-1]["payload"]["code"] == "missing_provider_key"
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert "实时模型回复未完成" in risk_events[-1]["payload"]["summary"]


def test_simple_chat_success_has_final_reasoning_trace(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    with patch("app.model_provider.ProviderRouter.chat", return_value="你好，我可以协助处理任务。"):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    final_events = assert_run_has_reasoning(state, phase="final_summary")
    assert state["status"] == "complete"
    assert "已完成模型回复" in final_events[-1]["payload"]["summary"]


def test_simple_chat_emits_streaming_answer_events_before_completion(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    def streamed_chat(_message: str, _model: str, _controller=None, *, on_delta=None) -> str:
        assert on_delta is not None
        on_delta("你好，")
        on_delta("我正在生成回答。")
        return "你好，我正在生成回答。"

    with patch("app.model_provider.ProviderRouter.chat", side_effect=streamed_chat):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        state = wait_for_terminal_status(client, task_id)

    run_id = state["runs"][0]["id"]
    run_event_types = [
        event["type"] for event in state["events"] if event.get("run_id") == run_id
    ]
    stream_events = [
        event
        for event in state["events"]
        if event["type"] == "assistant_answer_delta" and event.get("run_id") == run_id
    ]

    assert state["status"] == "complete"
    assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
    assert state["messages"][-1]["content"] == "你好，我正在生成回答。"
    assert stream_events
    assert stream_events[-1]["payload"]["schema_version"] == 1
    assert stream_events[-1]["payload"]["content"] == "你好，我正在生成回答。"
    assert stream_events[-1]["payload"]["live"]["kind"] == "answer_status"
    assert stream_events[-1]["payload"]["live"]["stage"] == "generating_answer"
    assert (
        run_event_types.index("answer_generation_started")
        < run_event_types.index("assistant_answer_delta")
        < run_event_types.index("chat_completed")
    )


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

    with pytest.raises(PermissionError, match="允许列表"):
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
    assert "取消" in outcome["error"]


def test_fetch_url_tool_is_not_exposed(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path, PermissionPolicy(tmp_path), None)

    assert not hasattr(tools, "fetch_url")


def test_tavily_search_observes_cancelled_controller_before_http_request(tmp_path: Path) -> None:
    controller = CancellationController()
    controller.cancel()
    tools = WorkspaceTools(tmp_path, PermissionPolicy(tmp_path), "test-key", controller)

    with patch("app.tools.httpx.post") as post, pytest.raises(RuntimeError, match="取消"):
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
    assert incremental[0]["session_id"] == task_id
    assert incremental[0]["seq"] == 2


def test_read_events_ignores_partial_jsonl_tail(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    storage = app.state.storage
    second = storage.append_event(task_id, "second", "Second event", {})
    events_path = tmp_path / "sessions" / task_id / "logs" / "events.jsonl"
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
    state_path = tmp_path / "sessions" / task_id / "state.json"
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
    storage = TaskStorage(Path("sessions"))

    state = storage.create_task(None, "deepseek-reasoner")

    assert storage.task_root == (tmp_path / "sessions").resolve()
    assert storage.task_dir(state.task_id).exists()


def test_provider_router_rejects_unimplemented_registry_provider(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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

    with pytest.raises(ValueError, match="不支持的模型服务提供方"):
        ProviderRouter(settings)


def test_create_app_rejects_explicit_multi_worker_runtime(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    with pytest.raises(RuntimeError, match="进程内任务运行器"):
        create_app(settings)


def test_model_reasoning_observes_cancellation(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
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
    assert "取消" in outcome["error"]


def test_simple_chat_cancel_does_not_overwrite_cancelled_state(tmp_path: Path) -> None:
    settings = Settings(
        task_root=tmp_path / "sessions",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        tavily_api_key=None,
        workspace_root=tmp_path / "sessions",
    )
    client = TestClient(create_app(settings))
    task_id = client.post("/api/tasks", json={}).json()["task_id"]

    def slow_stream(_message: str, _model: str, _on_delta, _controller=None) -> str:
        for _ in range(200):
            if _controller is not None and _controller.is_cancelled():
                raise RuntimeError("模型调用已取消")
            time.sleep(0.05)
        return "late"

    with patch("app.model_provider.DeepSeekProvider._chat_http_stream", side_effect=slow_stream):
        client.post(
            f"/api/tasks/{task_id}/messages",
            json={"message": "你好，请简单介绍你能做什么", "model": "deepseek-reasoner"},
        )
        time.sleep(0.2)
        cancelled = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancelled.json()["status"] == "cancelled"
        run_id = cancelled.json()["runs"][0]["id"]
        immediate_risk_events = reasoning_events_for_run(
            cancelled.json(), run_id, phase="risk"
        )
        assert immediate_risk_events
        state = wait_for_terminal_status(client, task_id)

    assert state["status"] == "cancelled"
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert "任务已取消" in risk_events[-1]["payload"]["summary"]


def test_cancel_racing_with_completion_preserves_complete_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    app = cast(FastAPI, client.app)
    storage = app.state.storage
    task_id = client.post("/api/tasks", json={}).json()["task_id"]
    complete_event = Event()
    release_event = Event()
    original_complete_update = storage.update_task_if_status_and_append_events

    def delayed_complete_update(
        event_task_id: str,
        *args,
        **kwargs,
    ):
        result = original_complete_update(event_task_id, *args, **kwargs)
        event_types = [event[0] for event in kwargs.get("events", [])]
        if event_task_id == task_id and "chat_completed" in event_types:
            complete_event.set()
            release_event.wait(timeout=3)
        return result

    with patch.object(
        storage,
        "update_task_if_status_and_append_events",
        side_effect=delayed_complete_update,
    ):
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
    risk_events = assert_run_has_reasoning(state, phase="risk")
    assert "实时模型回复未完成" in risk_events[-1]["payload"]["summary"]


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
