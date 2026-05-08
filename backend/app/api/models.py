"""Model registry REST endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.registry import list_available_models
from app.schemas import ModelOption

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=list[ModelOption])
def get_models(request: Request) -> list[dict]:
    settings = request.app.state.settings
    return list_available_models(settings)
