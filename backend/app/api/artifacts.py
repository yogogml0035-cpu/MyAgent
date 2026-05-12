"""Task artifact download endpoints."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse

router = APIRouter(prefix="/api/tasks", tags=["artifacts"])


def _storage(request: Request):
    return request.app.state.storage


def _artifact_response(path: Path) -> FileResponse:
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream", filename=path.name)


def _resolve_or_404(resolve) -> Path:
    try:
        return resolve()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="产物不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{task_id}/artifacts/{artifact_name}")
def download_artifact(task_id: str, artifact_name: str, request: Request) -> FileResponse:
    storage = _storage(request)
    path = _resolve_or_404(lambda: storage.resolve_artifact(task_id, artifact_name))
    return _artifact_response(path)


@router.get("/{task_id}/runs/{run_id}/artifacts/{artifact_name}")
def download_run_artifact(
    task_id: str,
    run_id: str,
    artifact_name: str,
    request: Request,
) -> FileResponse:
    storage = _storage(request)
    path = _resolve_or_404(lambda: storage.resolve_run_artifact(task_id, run_id, artifact_name))
    return _artifact_response(path)

