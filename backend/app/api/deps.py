"""FastAPI dependency injection helpers for request-scoped services."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, load_settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()
