"""DeepSeek-only model provider."""

from __future__ import annotations

from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr

from app.config import MODEL_REGISTRY, Settings
from app.models.deepseek_thinking import DeepSeekThinkingChatModel

_MODEL_RUNTIME_INDEX: dict[str, dict[str, Any]] = {
    cast(str, entry["id"]): entry for entry in MODEL_REGISTRY
}


class ModelProviderError(Exception):
    """Raised when a model cannot be created due to bad configuration."""


def _get_model_config(model_id: str) -> dict[str, Any]:
    entry = _MODEL_RUNTIME_INDEX.get(model_id)
    if entry is None:
        supported = ", ".join(sorted(_MODEL_RUNTIME_INDEX))
        raise ModelProviderError(
            f"Unsupported model ID '{model_id}'. Supported models: {supported}"
        )
    return entry


def create_model(
    model_id: str,
    settings: Settings,
    *,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Create a DeepSeek chat model from one of the safe app-level model IDs."""
    if not settings.deepseek_api_key:
        raise ModelProviderError(
            "DeepSeek API key is not configured. "
            "Set DEEPSEEK_API_KEY in backend/.env or environment variables."
        )

    entry = _get_model_config(model_id)
    thinking_mode = cast(str, entry.get("thinking_mode", "disabled"))
    provider_model = cast(str, entry.get("provider_model", "deepseek-v4-flash"))
    model_class = (
        DeepSeekThinkingChatModel if thinking_mode == "enabled" else ChatDeepSeek
    )

    return model_class(
        model=provider_model,
        api_key=SecretStr(settings.deepseek_api_key),
        api_base=settings.deepseek_base_url,
        temperature=temperature,
        extra_body={"thinking": {"type": thinking_mode}},
    )
