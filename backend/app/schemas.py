from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 8_000

TaskMode = Literal["auto", "chat", "analysis"]
InputScope = Literal["auto", "documents_only", "chat_only"]
TaskStatus = Literal[
    "idle", "running", "complete", "failed", "cancelled", "needs_input", "interrupted"
]


class TaskCreateRequest(BaseModel):
    message: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    model: str = "deepseek:deepseek-chat"


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    model: str = "deepseek:deepseek-chat"
    mode: TaskMode = "auto"
    input_scope: InputScope = "auto"


class TaskRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str
    run_id: str | None = None
    level: Literal["info", "warning", "error"] | None = None


class EventRecord(BaseModel):
    id: str
    session_id: str | None = None
    seq: int | None = None
    type: str
    message: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    level: Literal["info", "success", "warning", "error"] | None = None
    idempotency_key: str | None = None


class ArtifactRecord(BaseModel):
    id: str | None = None
    name: str
    type: Literal["html", "markdown", "json", "text"]
    url: str
    run_id: str | None = None


class TaskRunRecord(BaseModel):
    id: str
    status: TaskStatus
    message: str
    model: str
    started_at: str
    completed_at: str | None = None
    error: str | None = None
    needs_input: dict[str, Any] | None = None
    artifact_base_path: str
    artifact_names: list[str] = Field(default_factory=list)


class TaskState(BaseModel):
    task_id: str
    title: str | None = None
    status: TaskStatus
    model: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    runs: list[TaskRunRecord] = Field(default_factory=list)
    active_run_id: str | None = None
    run_count: int = 0
    upload_count: int = 0
    error: str | None = None
    needs_input: dict[str, Any] | None = None


class TaskSummary(BaseModel):
    task_id: str
    title: str
    status: TaskStatus
    model: str
    created_at: str
    updated_at: str
    run_count: int = 0
    last_message_at: str | None = None


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
    supports_files: bool
    supports_images: bool
    available: bool = False
