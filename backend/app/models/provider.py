"""Multi-model provider using langchain init_chat_model."""

from __future__ import annotations

from langchain.chat_models.base import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config import Settings

# Map provider prefix to the API key attribute name on Settings.
_PROVIDER_KEY_ATTR: dict[str, str] = {
    "deepseek": "deepseek_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
}

# Map provider prefix to the base_url attribute name on Settings (optional).
_PROVIDER_BASE_URL_ATTR: dict[str, str] = {
    "deepseek": "deepseek_base_url",
}


class ModelProviderError(Exception):
    """Raised when a model cannot be created due to missing keys or bad format."""


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse ``provider:model-name`` into (provider, model_name).

    Raises :class:`ModelProviderError` on invalid format.
    """
    if ":" not in model_id:
        raise ModelProviderError(
            f"Invalid model ID '{model_id}': expected format 'provider:model-name'"
        )
    provider, model_name = model_id.split(":", 1)
    if not provider or not model_name:
        raise ModelProviderError(
            f"Invalid model ID '{model_id}': both provider and model-name must be non-empty"
        )
    return provider, model_name


def create_model(
    model_id: str,
    settings: Settings,
    *,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Create a :class:`BaseChatModel` instance from a ``provider:model-name`` identifier.

    Args:
        model_id: Model identifier in ``provider:model-name`` format
            (e.g. ``deepseek:deepseek-chat``, ``openai:gpt-4o``).
        settings: Application settings containing API keys and base URLs.
        temperature: Sampling temperature. Defaults to ``0.0`` for deterministic agent use.

    Returns:
        A configured :class:`BaseChatModel` ready for chat completions.

    Raises:
        ModelProviderError: If the model ID format is invalid, the provider is
            unsupported, or the required API key is missing.
    """
    provider, model_name = _parse_model_id(model_id)

    key_attr = _PROVIDER_KEY_ATTR.get(provider)
    if key_attr is None:
        supported = ", ".join(sorted(_PROVIDER_KEY_ATTR))
        raise ModelProviderError(
            f"Unsupported provider '{provider}' in model ID '{model_id}'. "
            f"Supported providers: {supported}"
        )

    api_key: str | None = getattr(settings, key_attr, None)
    if not api_key:
        env_hint = key_attr.upper()
        raise ModelProviderError(
            f"API key for provider '{provider}' is not configured. "
            f"Set {env_hint} in backend/.env or environment variables."
        )

    kwargs: dict = {
        "model": model_name,
        "model_provider": provider,
        "temperature": temperature,
        "api_key": api_key,
    }

    base_url_attr = _PROVIDER_BASE_URL_ATTR.get(provider)
    if base_url_attr is not None:
        base_url: str | None = getattr(settings, base_url_attr, None)
        if base_url:
            kwargs["base_url"] = base_url

    return init_chat_model(**kwargs)
