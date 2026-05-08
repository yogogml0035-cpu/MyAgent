"""Model registry: available models, provider resolution, validation."""

from __future__ import annotations

from typing import cast

from app.config import MODEL_REGISTRY, Settings
from app.models.provider import _PROVIDER_KEY_ATTR

_MODEL_INDEX: dict[str, dict] = {
    cast(str, entry["id"]): entry for entry in MODEL_REGISTRY
}


def validate_model(model_id: str) -> bool:
    """Return ``True`` if *model_id* exists in the model registry."""
    return model_id in _MODEL_INDEX


def get_model_info(model_id: str) -> dict | None:
    """Return the registry metadata dict for *model_id*, or ``None`` if unknown."""
    return _MODEL_INDEX.get(model_id)


def list_available_models(settings: Settings) -> list[dict]:
    """Return registry entries annotated with an ``available`` flag.

    A model is considered *available* when the corresponding provider API key
    is configured in *settings*.
    """
    results: list[dict] = []
    for entry in MODEL_REGISTRY:
        provider = cast(str, entry["provider"])
        key_attr = _PROVIDER_KEY_ATTR.get(provider)
        has_key = bool(key_attr and getattr(settings, key_attr, None))
        results.append({
            "id": entry["id"],
            "label": entry["label"],
            "provider": provider,
            "supports_files": entry.get("supports_files", False),
            "supports_images": entry.get("supports_images", False),
            "available": has_key,
        })
    return results
