"""Task-scoped resource execution tools.

This module keeps the LangChain tool surface thin.  The tools expose stable
resource-oriented names and delegate the actual work to a local execution
adapter that mirrors a future Provision/Execute boundary.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.storage import (
    UPLOAD_FORMATS,
    build_upload_resource_ref,
    file_sha256,
    source_format_for_upload,
)

RESOURCE_TOOL_SYSTEM_PROMPT = """Uploaded files are task Resources, not chat context.
Use the resource tools when a user asks about uploaded files. First inspect or list resources, then read only the needed text page or table range. Do not assume uploaded file contents are already visible in the conversation."""

DEFAULT_TEXT_LIMIT = 40
MAX_TEXT_LIMIT = 200
DEFAULT_TABLE_LIMIT = 25
MAX_TABLE_LIMIT = 100
MAX_TABLE_COLUMNS = 80


@dataclass(frozen=True)
class ProvisionRequest:
    task_id: str
    workspace_root: Path


@dataclass(frozen=True)
class ExecutionRequest:
    tool_name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str
    retryable: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    data: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    error: ExecutionError | None = None

    @classmethod
    def success(cls, data: dict[str, Any] | list[Any] | str | int | float | bool | None):
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str, *, retryable: bool = False):
        return cls(ok=False, error=ExecutionError(code, message, retryable))

    def to_payload(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "error": self.error.to_payload() if self.error else None}

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, default=str)


@dataclass(frozen=True)
class ResourceRecord:
    resource_id: str
    name: str
    path: Path
    format: str
    extension: str
    size_bytes: int
    digest: str

    def to_manifest_item(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "name": self.name,
            "format": self.format,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ProvisionedResourceUnit:
    task_id: str
    workspace_root: Path
    task_workspace: Path
    upload_dir: Path
    resources: tuple[ResourceRecord, ...]


class LocalResourceExecutionAdapter:
    """In-process Provision/Execute adapter for uploaded task resources."""

    def __init__(self, *, task_id: str, workspace_root: Path):
        self.request = ProvisionRequest(task_id=task_id, workspace_root=workspace_root)

    def provision(self) -> ProvisionedResourceUnit:
        task_workspace = _resolve_task_workspace(self.request.workspace_root, self.request.task_id)
        upload_dir = task_workspace / "uploads"
        resources = tuple(_resource_records(self.request.task_id, upload_dir))
        return ProvisionedResourceUnit(
            task_id=self.request.task_id,
            workspace_root=self.request.workspace_root.resolve(),
            task_workspace=task_workspace,
            upload_dir=upload_dir,
            resources=resources,
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            unit = self.provision()
        except ValueError as exc:
            return ExecutionResult.failure("invalid_task_workspace", str(exc))

        try:
            if request.tool_name == "list_uploaded_resources":
                return ExecutionResult.success(_list_uploaded_resources(unit))
            if request.tool_name == "inspect_resource":
                return _inspect_resource(unit, request.input)
            if request.tool_name == "read_resource_text":
                return _read_resource_text(unit, request.input)
            if request.tool_name == "read_resource_table":
                return _read_resource_table(unit, request.input)
            return ExecutionResult.failure(
                "unknown_tool",
                f"未知资源工具：{request.tool_name}",
            )
        except Exception as exc:  # pragma: no cover - safety net for tool-call isolation
            return ExecutionResult.failure("execution_error", str(exc), retryable=True)


def create_resource_tools(*, task_id: str, workspace_root: Path) -> list[BaseTool]:
    adapter = LocalResourceExecutionAdapter(task_id=task_id, workspace_root=workspace_root)

    @tool
    def list_uploaded_resources() -> str:
        """List task-scoped uploaded resources without reading file contents."""
        return adapter.execute(ExecutionRequest("list_uploaded_resources")).to_json()

    @tool
    def inspect_resource(resource: str) -> str:
        """Inspect a task resource by resource_id or filename and return structured metadata."""
        return adapter.execute(
            ExecutionRequest("inspect_resource", {"resource": resource})
        ).to_json()

    @tool
    def read_resource_text(resource: str, page: int = 1, limit: int = DEFAULT_TEXT_LIMIT) -> str:
        """Read paginated structured text blocks from a task resource."""
        return adapter.execute(
            ExecutionRequest(
                "read_resource_text",
                {"resource": resource, "page": page, "limit": limit},
            )
        ).to_json()

    @tool
    def read_resource_table(
        resource: str,
        sheet: str | None = None,
        range_ref: str | None = None,
        table_index: int | None = None,
        start_row: int = 1,
        limit: int = DEFAULT_TABLE_LIMIT,
    ) -> str:
        """Read a table/range from Excel or Word resources as structured rows."""
        return adapter.execute(
            ExecutionRequest(
                "read_resource_table",
                {
                    "resource": resource,
                    "sheet": sheet,
                    "range_ref": range_ref,
                    "table_index": table_index,
                    "start_row": start_row,
                    "limit": limit,
                },
            )
        ).to_json()

    return [list_uploaded_resources, inspect_resource, read_resource_text, read_resource_table]


def build_resource_manifest(task_id: str, workspace_root: Path) -> dict[str, Any]:
    unit = LocalResourceExecutionAdapter(task_id=task_id, workspace_root=workspace_root).provision()
    return _list_uploaded_resources(unit)


def format_resource_manifest_message(manifest: dict[str, Any]) -> str:
    resources = manifest.get("resources") if isinstance(manifest, dict) else []
    if not resources:
        return ""
    return "\n".join(
        [
            RESOURCE_TOOL_SYSTEM_PROMPT,
            "Current task resource manifest:",
            json.dumps(
                {
                    "schema_version": 1,
                    "resources": resources,
                },
                ensure_ascii=False,
            ),
        ]
    )


def _resolve_task_workspace(workspace_root: Path, task_id: str) -> Path:
    root = workspace_root.resolve()
    task_workspace = (root / task_id).resolve()
    if task_workspace != root and root not in task_workspace.parents:
        raise ValueError("任务工作区超出资源根目录")
    return task_workspace


def _resource_records(task_id: str, upload_dir: Path) -> list[ResourceRecord]:
    if not upload_dir.exists():
        return []
    records: list[ResourceRecord] = []
    for path in sorted(upload_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in UPLOAD_FORMATS:
            continue
        resource_ref = build_upload_resource_ref(
            session_id=task_id,
            filename=path.name,
            size_bytes=path.stat().st_size,
            digest=file_sha256(path),
            media_type=source_format_for_upload(path),
        )
        records.append(
            ResourceRecord(
                resource_id=resource_ref.id,
                name=path.name,
                path=path.resolve(),
                format=source_format_for_upload(path),
                extension=path.suffix.lower(),
                size_bytes=path.stat().st_size,
                digest=resource_ref.digest or "",
            )
        )
    return records


def _list_uploaded_resources(unit: ProvisionedResourceUnit) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": unit.task_id,
        "resources": [resource.to_manifest_item() for resource in unit.resources],
    }


def _resolve_resource(unit: ProvisionedResourceUnit, raw_resource: Any) -> ResourceRecord | None:
    resource = str(raw_resource or "").strip()
    if not resource:
        return None
    by_id = {item.resource_id: item for item in unit.resources}
    if resource in by_id:
        return by_id[resource]
    if resource.startswith(f"upload:{unit.task_id}:"):
        resource = resource.rsplit(":", 1)[-1]
    if Path(resource).name != resource:
        return None
    resource_key = resource.casefold()
    for item in unit.resources:
        if item.name.casefold() == resource_key:
            return item
    return None


def _inspect_resource(unit: ProvisionedResourceUnit, input_data: dict[str, Any]) -> ExecutionResult:
    resource = _resolve_resource(unit, input_data.get("resource"))
    if resource is None:
        return ExecutionResult.failure("resource_not_found", "未找到当前任务中的上传资源")
    data = {
        **resource.to_manifest_item(),
        "structure": _inspect_structure(resource),
    }
    return ExecutionResult.success(data)


def _inspect_structure(resource: ResourceRecord) -> dict[str, Any]:
    if resource.format in {"markdown", "text"}:
        text = _read_text_file(resource.path)
        lines = text.splitlines()
        return {
            "kind": resource.format,
            "line_count": len(lines),
            "char_count": len(text),
            "preview_lines": lines[: min(5, len(lines))],
        }
    if resource.format == "json":
        value = _load_json_file(resource.path)
        return {
            "kind": "json",
            "json_type": type(value).__name__,
            "top_level_keys": list(value.keys())[:50] if isinstance(value, dict) else None,
            "length": len(value) if isinstance(value, (dict, list)) else None,
        }
    if resource.format == "word":
        return _inspect_docx(resource.path)
    if resource.format == "excel":
        return _inspect_excel(resource.path)
    return {"kind": resource.format}


def _read_resource_text(unit: ProvisionedResourceUnit, input_data: dict[str, Any]) -> ExecutionResult:
    resource = _resolve_resource(unit, input_data.get("resource"))
    if resource is None:
        return ExecutionResult.failure("resource_not_found", "未找到当前任务中的上传资源")
    page = _positive_int(input_data.get("page"), 1)
    limit = min(_positive_int(input_data.get("limit"), DEFAULT_TEXT_LIMIT), MAX_TEXT_LIMIT)

    if resource.format in {"markdown", "text"}:
        return ExecutionResult.success(_paginate_lines(_read_text_file(resource.path), page, limit, resource))
    if resource.format == "json":
        text = json.dumps(_load_json_file(resource.path), ensure_ascii=False, indent=2)
        return ExecutionResult.success(_paginate_lines(text, page, limit, resource))
    if resource.format == "word":
        blocks = _docx_blocks(resource.path)
        return ExecutionResult.success(_paginate_blocks(blocks, page, limit, resource))
    if resource.format == "excel":
        return ExecutionResult.failure(
            "unsupported_operation",
            "Excel 资源请使用 read_resource_table 按 sheet 或 range 读取",
        )
    return ExecutionResult.failure("unsupported_resource_format", f"暂不支持读取 {resource.format}")


def _read_resource_table(unit: ProvisionedResourceUnit, input_data: dict[str, Any]) -> ExecutionResult:
    resource = _resolve_resource(unit, input_data.get("resource"))
    if resource is None:
        return ExecutionResult.failure("resource_not_found", "未找到当前任务中的上传资源")
    limit = min(_positive_int(input_data.get("limit"), DEFAULT_TABLE_LIMIT), MAX_TABLE_LIMIT)

    if resource.format == "excel":
        return ExecutionResult.success(
            _read_excel_table(
                resource,
                sheet=input_data.get("sheet"),
                range_ref=input_data.get("range_ref"),
                start_row=_positive_int(input_data.get("start_row"), 1),
                limit=limit,
            )
        )
    if resource.format == "word":
        table_index = _positive_int(input_data.get("table_index"), 0, allow_zero=True)
        return ExecutionResult.success(_read_docx_table(resource, table_index=table_index, limit=limit))
    return ExecutionResult.failure(
        "unsupported_operation",
        "该资源格式不包含可读取的表格范围",
    )


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _paginate_lines(text: str, page: int, limit: int, resource: ResourceRecord) -> dict[str, Any]:
    lines = text.splitlines()
    start = (page - 1) * limit
    end = start + limit
    return {
        "schema_version": 1,
        "resource": resource.to_manifest_item(),
        "page": page,
        "limit": limit,
        "total_items": len(lines),
        "total_pages": max(1, math.ceil(len(lines) / limit)) if limit else 1,
        "items": [
            {"line": index + 1, "text": line}
            for index, line in enumerate(lines[start:end], start=start)
        ],
    }


def _paginate_blocks(
    blocks: list[dict[str, Any]], page: int, limit: int, resource: ResourceRecord
) -> dict[str, Any]:
    start = (page - 1) * limit
    end = start + limit
    return {
        "schema_version": 1,
        "resource": resource.to_manifest_item(),
        "page": page,
        "limit": limit,
        "total_items": len(blocks),
        "total_pages": max(1, math.ceil(len(blocks) / limit)) if limit else 1,
        "items": blocks[start:end],
    }


def _inspect_docx(path: Path) -> dict[str, Any]:
    blocks = _docx_blocks(path)
    table_count = sum(1 for block in blocks if block["type"] == "table")
    headings = [
        {
            "order": block["order"],
            "level": block.get("level"),
            "text": block.get("text"),
        }
        for block in blocks
        if block["type"] == "heading"
    ][:50]
    return {
        "kind": "word",
        "block_count": len(blocks),
        "table_count": table_count,
        "headings": headings,
    }


def _docx_blocks(path: Path) -> list[dict[str, Any]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    blocks: list[dict[str, Any]] = []
    table_index = 0
    paragraph_index = 0

    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style_name = paragraph.style.name if paragraph.style is not None else ""
            block_type = "paragraph"
            level: int | None = None
            if style_name.lower().startswith("heading"):
                block_type = "heading"
                level = _heading_level(style_name)
            elif "list" in style_name.lower():
                block_type = "list_item"
            item: dict[str, Any] = {
                "order": len(blocks),
                "type": block_type,
                "paragraph_index": paragraph_index,
                "style": style_name,
                "text": text,
            }
            if level is not None:
                item["level"] = level
            blocks.append(item)
            paragraph_index += 1
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            blocks.append(
                {
                    "order": len(blocks),
                    "type": "table",
                    "table_index": table_index,
                    "row_count": len(rows),
                    "column_count": max((len(row) for row in rows), default=0),
                    "rows": rows[: min(len(rows), DEFAULT_TABLE_LIMIT)],
                    "truncated": len(rows) > DEFAULT_TABLE_LIMIT,
                }
            )
            table_index += 1
    return blocks


def _read_docx_table(resource: ResourceRecord, *, table_index: int, limit: int) -> dict[str, Any]:
    tables = [block for block in _docx_blocks(resource.path) if block["type"] == "table"]
    if table_index >= len(tables):
        return {
            "schema_version": 1,
            "resource": resource.to_manifest_item(),
            "table_index": table_index,
            "rows": [],
            "error": {"code": "table_not_found", "message": "Word 表格不存在"},
        }
    table = tables[table_index]
    rows = table.get("rows", [])
    return {
        "schema_version": 1,
        "resource": resource.to_manifest_item(),
        "table_index": table_index,
        "row_count": table.get("row_count", len(rows)),
        "column_count": table.get("column_count", 0),
        "rows": rows[:limit],
        "truncated": len(rows) > limit or bool(table.get("truncated")),
    }


def _inspect_excel(path: Path) -> dict[str, Any]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True, read_only=False)
    sheets = []
    for sheet in workbook.worksheets:
        sheets.append(
            {
                "name": sheet.title,
                "max_row": sheet.max_row,
                "max_column": sheet.max_column,
                "merged_ranges": [str(item) for item in list(sheet.merged_cells.ranges)[:50]],
                "header_guess": _guess_header(sheet),
            }
        )
    workbook.close()
    return {
        "kind": "excel",
        "sheet_count": len(sheets),
        "sheets": sheets,
    }


def _read_excel_table(
    resource: ResourceRecord,
    *,
    sheet: Any,
    range_ref: Any,
    start_row: int,
    limit: int,
) -> dict[str, Any]:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter, range_boundaries

    workbook = load_workbook(resource.path, data_only=True, read_only=False)
    sheet_name = str(sheet).strip() if sheet else workbook.sheetnames[0]
    if sheet_name not in workbook.sheetnames:
        workbook.close()
        return {
            "schema_version": 1,
            "resource": resource.to_manifest_item(),
            "sheet": sheet_name,
            "rows": [],
            "error": {"code": "sheet_not_found", "message": "Excel sheet 不存在"},
        }
    worksheet = workbook[sheet_name]
    if range_ref:
        min_col, min_row, max_col, max_row = range_boundaries(str(range_ref))
        max_row = min(max_row, min_row + limit - 1)
    else:
        min_row = start_row
        max_row = min(worksheet.max_row, start_row + limit - 1)
        min_col = 1
        max_col = min(worksheet.max_column, MAX_TABLE_COLUMNS)
    worksheet_max_row = worksheet.max_row
    rows = []
    for row in worksheet.iter_rows(
        min_row=min_row,
        max_row=max_row,
        min_col=min_col,
        max_col=max_col,
        values_only=True,
    ):
        rows.append([_cell_value(value) for value in row])
    workbook.close()
    return {
        "schema_version": 1,
        "resource": resource.to_manifest_item(),
        "sheet": sheet_name,
        "range": f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}",
        "start_row": min_row,
        "row_count": len(rows),
        "column_count": max_col - min_col + 1,
        "rows": rows,
        "truncated": max_row < worksheet_max_row if not range_ref else False,
    }


def _guess_header(sheet: Any) -> dict[str, Any] | None:
    for row_index, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20), values_only=True),
        start=1,
    ):
        values = [_cell_value(value) for value in row]
        non_empty = [value for value in values if value not in {"", None}]
        if len(non_empty) >= 2:
            return {"row": row_index, "values": values[:MAX_TABLE_COLUMNS]}
    return None


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _heading_level(style_name: str) -> int | None:
    parts = style_name.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _positive_int(value: Any, fallback: int, *, allow_zero: bool = False) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    minimum = 0 if allow_zero else 1
    return number if number >= minimum else fallback
