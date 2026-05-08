"""File upload REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.schemas import TaskState

router = APIRouter(prefix="/api/tasks", tags=["files"])


def _storage(request: Request):
    return request.app.state.storage


def _runner(request: Request):
    return request.app.state.runner


@router.post("/{task_id}/files", response_model=TaskState, status_code=201)
def upload_files(task_id: str, files: list[UploadFile], request: Request) -> TaskState:
    storage = _storage(request)
    runner = _runner(request)
    state = storage.get_task(task_id, include_events=False)
    if state.status == "idle" and not state.messages:
        raise HTTPException(status_code=404, detail="任务不存在")
    if runner.is_running(task_id):
        raise HTTPException(status_code=409, detail="任务运行中不能上传文件")
    settings = request.app.state.settings
    storage.save_uploads(
        task_id,
        files,
        max_files=settings.max_upload_files,
        max_file_bytes=settings.max_upload_file_bytes,
        max_request_bytes=settings.max_upload_request_bytes,
    )
    return storage.get_task(task_id)
