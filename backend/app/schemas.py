from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 8_000

TaskStatus = Literal[
    "idle", "running", "complete", "failed", "cancelled", "needs_input", "interrupted"
]


class TaskCreateRequest(BaseModel):
    message: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    model: str = "deepseek-reasoner"


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    model: str = "deepseek-reasoner"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


class EventRecord(BaseModel):
    id: str
    type: str
    message: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    name: str
    type: Literal["html", "markdown", "json", "text"]
    url: str


class TaskState(BaseModel):
    task_id: str
    status: TaskStatus
    model: str
    created_at: str
    updated_at: str
    messages: list[ChatMessage] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    upload_count: int = 0
    error: str | None = None
    needs_input: dict[str, Any] | None = None


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
    supports_files: bool
    supports_images: bool
