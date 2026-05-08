"""Task CRUD and lifecycle REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import (
    EventRecord,
    MessageRequest,
    TaskCreateRequest,
    TaskState,
    TaskSummary,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


@router.post("", response_model=TaskState, status_code=201)
def create_task(body: TaskCreateRequest, request: Request) -> TaskState:
    storage = _storage(request)
    state = storage.create_task(message=None, model=body.model)
    if body.message:
        runner = _runner(request)
        runner.start_background(state.task_id, body.message, model=body.model)
    return storage.get_task(state.task_id)


@router.get("", response_model=list[TaskSummary])
def list_tasks(request: Request) -> list[TaskSummary]:
    return _storage(request).list_task_summaries()


@router.get("/{task_id}", response_model=TaskState)
def get_task(task_id: str, request: Request) -> TaskState:
    storage = _storage(request)
    state = storage.get_task(task_id)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state


@router.get("/{task_id}/events", response_model=list[EventRecord])
def get_events(task_id: str, after_id: str | None = None, request: Request | None = None) -> list[EventRecord]:
    assert request is not None  # FastAPI always provides the request
    storage = _storage(request)
    state = storage.get_task(task_id, include_events=False)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    return storage.read_events(task_id, after_id=after_id)


@router.post("/{task_id}/messages", response_model=TaskState)
def send_message(task_id: str, body: MessageRequest, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    state = storage.get_task(task_id, include_events=False)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    if runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中，请等待完成后再发送消息")
    runner.start_background(task_id, body.message, model=body.model)
    return storage.get_task(task_id)


@router.post("/{task_id}/cancel", response_model=TaskState)
async def cancel_task(task_id: str, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    state = storage.get_task(task_id, include_events=False)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务未在运行中")
    await runner.cancel(task_id)
    return storage.get_task(task_id)
