"""DeepSeek-only model registry and availability checks."""

from __future__ import annotations

from typing import cast

from app.config import MODEL_REGISTRY, Settings

_MODEL_INDEX: dict[str, dict] = {
    cast(str, entry["id"]): entry for entry in MODEL_REGISTRY
}


def validate_model(model_id: str) -> bool:
    """Return ``True`` if *model_id* exists in the model registry."""
    return model_id in _MODEL_INDEX


def get_model_info(model_id: str) -> dict | None:
    """Return the registry metadata dict for *model_id*, or ``None`` if unknown."""
    return _MODEL_INDEX.get(model_id)


def is_model_available(model_id: str, settings: Settings) -> bool:
    """Return whether *model_id* is registered and DeepSeek is configured."""
    return model_id in _MODEL_INDEX and bool(settings.deepseek_api_key)


def list_available_models(settings: Settings) -> list[dict]:
    """Return registered models annotated with an ``available`` flag."""
    return [
        {
            "id": entry["id"],
            "label": entry["label"],
            "provider": cast(str, entry["provider"]),
            "supports_files": entry.get("supports_files", False),
            "supports_images": entry.get("supports_images", False),
            "available": bool(settings.deepseek_api_key),
        }
        for entry in MODEL_REGISTRY
    ]
