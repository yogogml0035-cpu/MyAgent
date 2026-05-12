"""Task CRUD and lifecycle REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.models.registry import is_model_available, validate_model
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


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _get_existing_task(storage, task_id: str, **kwargs) -> TaskState:
    """Read task state; return 404 if the task directory does not exist."""
    try:
        return storage.get_task(task_id, **kwargs)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="任务不存在") from None


def _validate_registered_model(model: str) -> None:
    if not validate_model(model):
        raise HTTPException(status_code=400, detail="模型不在允许列表中")


def _validate_runnable_model(model: str, settings: Settings) -> None:
    _validate_registered_model(model)
    if not is_model_available(model, settings):
        raise HTTPException(status_code=400, detail="模型服务未配置，请先在后端配置对应 API Key")


@router.post("", response_model=TaskState, status_code=201)
async def create_task(body: TaskCreateRequest, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    settings = _settings(request)
    if body.message:
        _validate_runnable_model(body.model, settings)
    else:
        _validate_registered_model(body.model)
    state = storage.create_task(message=None, model=body.model)
    if body.message:
        run_result = storage.start_run(
            state.task_id,
            message=body.message,
            model=body.model,
            expected_statuses={"idle"},
        )
        if run_result is not None:
            _, run_id = run_result
            runner.start_background(state.task_id, body.message, model=body.model, run_id=run_id)
    return storage.get_task(state.task_id)


@router.get("", response_model=list[TaskSummary])
def list_tasks(request: Request) -> list[TaskSummary]:
    return _storage(request).list_task_summaries()


@router.get("/{task_id}", response_model=TaskState)
def get_task(task_id: str, request: Request, include_events: bool = True) -> TaskState:
    return _get_existing_task(_storage(request), task_id, include_events=include_events)


@router.get("/{task_id}/events", response_model=list[EventRecord])
def get_events(task_id: str, request: Request, after_id: str | None = None) -> list[EventRecord]:
    storage = _storage(request)
    _get_existing_task(storage, task_id, include_events=False)
    return storage.read_events(task_id, after_id=after_id)


@router.post("/{task_id}/messages", response_model=TaskState)
async def send_message(task_id: str, body: MessageRequest, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    _validate_runnable_model(body.model, _settings(request))
    _get_existing_task(storage, task_id, include_events=False)
    if runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中，请等待完成后再发送消息")
    run_result = storage.start_run(
        task_id,
        message=body.message,
        model=body.model,
        expected_statuses={"idle", "complete", "failed", "cancelled", "needs_input", "interrupted"},
    )
    if run_result is None:
        raise HTTPException(status_code=409, detail="任务状态不允许发送消息")
    _, run_id = run_result
    runner.start_background(task_id, body.message, model=body.model, run_id=run_id)
    return storage.get_task(task_id)


@router.post("/{task_id}/cancel", response_model=TaskState)
async def cancel_task(task_id: str, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    _get_existing_task(storage, task_id, include_events=False)
    if not runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务未在运行中")
    await runner.cancel(task_id)
    return storage.get_task(task_id)
