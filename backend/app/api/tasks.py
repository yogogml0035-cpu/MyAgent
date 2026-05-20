"""Task CRUD and lifecycle REST endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.models.registry import is_model_available, validate_model
from app.schemas import (
    EventRecord,
    MessageRequest,
    TaskCreateRequest,
    TaskRenameRequest,
    TaskState,
    TaskSummary,
)
from app.skills.project import format_message_with_skill_refs, validate_project_skill_names

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _title_generator(request: Request):
    return request.app.state.title_generator


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


def _resolve_request_model(model: str | None, settings: Settings) -> str:
    resolved_model = model or settings.default_model
    _validate_registered_model(resolved_model)
    return resolved_model


async def _set_auto_title_if_empty(
    request: Request,
    task_id: str,
    message: str,
    model: str,
    settings: Settings,
) -> None:
    storage = _storage(request)
    try:
        title = await _title_generator(request)(message, model, settings)
        storage.set_task_title_if_empty(task_id, title)
    except Exception:
        logger.warning("Failed to set automatic task title for task %s", task_id, exc_info=True)


@router.post("", response_model=TaskState, status_code=201)
async def create_task(body: TaskCreateRequest, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    settings = _settings(request)
    model = _resolve_request_model(body.model, settings)
    if body.message:
        _validate_runnable_model(model, settings)
    else:
        _validate_registered_model(model)
    state = storage.create_task(message=None, model=model)
    if body.message:
        run_result = storage.start_run(
            state.task_id,
            message=body.message,
            model=model,
            expected_statuses={"idle"},
        )
        if run_result is not None:
            _, run_id = run_result
            await _set_auto_title_if_empty(request, state.task_id, body.message, model, settings)
            runner.start_background(state.task_id, body.message, model=model, run_id=run_id)
    return storage.get_task(state.task_id)


@router.get("", response_model=list[TaskSummary])
def list_tasks(request: Request) -> list[TaskSummary]:
    return _storage(request).list_task_summaries()


@router.get("/{task_id}", response_model=TaskState)
def get_task(task_id: str, request: Request, include_events: bool = True) -> TaskState:
    return _get_existing_task(_storage(request), task_id, include_events=include_events)


@router.patch("/{task_id}", response_model=TaskState)
def rename_task(task_id: str, body: TaskRenameRequest, request: Request) -> TaskState:
    storage = _storage(request)
    _get_existing_task(storage, task_id, include_events=False)
    try:
        return storage.rename_task(task_id, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, request: Request) -> None:
    storage = _storage(request)
    runner = _runner(request)
    state = _get_existing_task(storage, task_id, include_events=False)
    if state.status == "running" or runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中，不能删除")
    try:
        storage.delete_task(task_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="任务不存在") from None


@router.get("/{task_id}/events", response_model=list[EventRecord])
def get_events(task_id: str, request: Request, after_id: str | None = None) -> list[EventRecord]:
    storage = _storage(request)
    _get_existing_task(storage, task_id, include_events=False)
    return storage.read_events(task_id, after_id=after_id)


@router.post("/{task_id}/messages", response_model=TaskState)
async def send_message(task_id: str, body: MessageRequest, request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    settings = _settings(request)
    model = _resolve_request_model(body.model, settings)
    _validate_runnable_model(model, settings)
    _get_existing_task(storage, task_id, include_events=False)
    unknown_skills = validate_project_skill_names(body.skills)
    if unknown_skills:
        raise HTTPException(status_code=400, detail=f"未知 skill：{', '.join(unknown_skills)}")
    effective_message = format_message_with_skill_refs(body.message, body.skills)
    if runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中，请等待完成后再发送消息")
    run_result = storage.start_run(
        task_id,
        message=effective_message,
        model=model,
        expected_statuses={"idle", "complete", "failed", "cancelled", "needs_input", "interrupted"},
    )
    if run_result is None:
        raise HTTPException(status_code=409, detail="任务状态不允许发送消息")
    _, run_id = run_result
    await _set_auto_title_if_empty(request, task_id, effective_message, model, settings)
    runner.start_background(task_id, effective_message, model=model, run_id=run_id)
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
