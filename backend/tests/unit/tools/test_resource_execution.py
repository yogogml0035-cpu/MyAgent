from __future__ import annotations

import json

from docx import Document
from openpyxl import Workbook

from app.execution.resources import (
    ExecutionRequest,
    LocalResourceExecutionAdapter,
    build_resource_manifest,
    create_resource_tools,
    format_resource_manifest_message,
)


def _task_upload_dir(tmp_path, task_id: str):
    upload_dir = tmp_path / task_id / "uploads"
    upload_dir.mkdir(parents=True)
    return upload_dir


def _write_docx(path):
    document = Document()
    document.add_heading("项目概览", level=1)
    document.add_paragraph("这是一段 Word 正文。")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "字段"
    table.cell(0, 1).text = "值"
    table.cell(1, 0).text = "预算"
    table.cell(1, 1).text = "100"
    document.save(path)


def _write_xlsx(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "明细"
    sheet.append(["名称", "金额"])
    sheet.append(["A", 10])
    sheet.append(["B", 20])
    workbook.save(path)


class TestLocalResourceExecutionAdapter:
    def test_lists_manifest_without_reading_contents(self, tmp_path):
        task_id = "task-1"
        upload_dir = _task_upload_dir(tmp_path, task_id)
        (upload_dir / "notes.txt").write_text("secret body", encoding="utf-8")

        manifest = build_resource_manifest(task_id, tmp_path)

        assert manifest["resources"][0]["name"] == "notes.txt"
        assert manifest["resources"][0]["format"] == "text"
        assert "secret body" not in json.dumps(manifest, ensure_ascii=False)

    def test_reads_text_resource_as_paginated_json(self, tmp_path):
        task_id = "task-1"
        upload_dir = _task_upload_dir(tmp_path, task_id)
        (upload_dir / "notes.txt").write_text("alpha\nbeta\ngamma", encoding="utf-8")
        adapter = LocalResourceExecutionAdapter(task_id=task_id, workspace_root=tmp_path)

        result = adapter.execute(
            ExecutionRequest(
                "read_resource_text",
                {"resource": "notes.txt", "page": 1, "limit": 2},
            )
        ).to_payload()

        assert result["ok"] is True
        assert result["data"]["total_items"] == 3
        assert [item["text"] for item in result["data"]["items"]] == ["alpha", "beta"]

    def test_inspects_docx_structure_and_reads_table(self, tmp_path):
        task_id = "task-1"
        upload_dir = _task_upload_dir(tmp_path, task_id)
        _write_docx(upload_dir / "brief.docx")
        adapter = LocalResourceExecutionAdapter(task_id=task_id, workspace_root=tmp_path)

        inspected = adapter.execute(
            ExecutionRequest("inspect_resource", {"resource": "brief.docx"})
        ).to_payload()
        table = adapter.execute(
            ExecutionRequest("read_resource_table", {"resource": "brief.docx", "table_index": 0})
        ).to_payload()

        assert inspected["ok"] is True
        assert inspected["data"]["structure"]["kind"] == "word"
        assert inspected["data"]["structure"]["headings"][0]["text"] == "项目概览"
        assert table["ok"] is True
        assert table["data"]["rows"][1] == ["预算", "100"]

    def test_inspects_xlsx_structure_and_reads_sheet_range(self, tmp_path):
        task_id = "task-1"
        upload_dir = _task_upload_dir(tmp_path, task_id)
        _write_xlsx(upload_dir / "data.xlsx")
        adapter = LocalResourceExecutionAdapter(task_id=task_id, workspace_root=tmp_path)

        inspected = adapter.execute(
            ExecutionRequest("inspect_resource", {"resource": "data.xlsx"})
        ).to_payload()
        table = adapter.execute(
            ExecutionRequest(
                "read_resource_table",
                {"resource": "data.xlsx", "sheet": "明细", "range_ref": "A1:B2"},
            )
        ).to_payload()

        assert inspected["ok"] is True
        assert inspected["data"]["structure"]["sheets"][0]["header_guess"]["values"] == ["名称", "金额"]
        assert table["ok"] is True
        assert table["data"]["rows"] == [["名称", "金额"], ["A", 10]]

    def test_missing_resource_returns_tool_call_error_payload(self, tmp_path):
        adapter = LocalResourceExecutionAdapter(task_id="task-1", workspace_root=tmp_path)

        result = adapter.execute(
            ExecutionRequest("inspect_resource", {"resource": "../outside.txt"})
        ).to_payload()

        assert result == {
            "ok": False,
            "error": {
                "code": "resource_not_found",
                "message": "未找到当前任务中的上传资源",
                "retryable": False,
            },
        }

    def test_langchain_tools_delegate_to_execution_adapter(self, tmp_path):
        task_id = "task-1"
        upload_dir = _task_upload_dir(tmp_path, task_id)
        (upload_dir / "data.json").write_text('{"name": "MyAgent"}', encoding="utf-8")
        tools = {tool.name: tool for tool in create_resource_tools(task_id=task_id, workspace_root=tmp_path)}

        result = json.loads(tools["inspect_resource"].invoke({"resource": "data.json"}))

        assert result["ok"] is True
        assert result["data"]["format"] == "json"
        assert result["data"]["structure"]["top_level_keys"] == ["name"]

    def test_resource_manifest_message_omits_empty_manifest(self, tmp_path):
        assert format_resource_manifest_message(build_resource_manifest("task-1", tmp_path)) == ""
