import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.model_provider import DeepSeekProvider
from app.runtime import CancellationController
from app.settings import Settings


def _test_settings() -> Settings:
    return Settings(
        task_root=Path("/tmp/test-tasks"),
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.test.com",
        tavily_api_key=None,
        workspace_root=Path("/tmp/test-workspace"),
        deepseek_timeout_seconds=5,
    )


class TestChatHttpCancellableEventLoop:
    """Regression tests for Issue #25: asyncio.run() crash in running event loop."""

    def test_chat_http_cancellable_no_running_loop(self) -> None:
        """When no event loop is running, _chat_http_cancellable should work normally."""
        provider = DeepSeekProvider(_test_settings())
        controller = CancellationController()

        with patch.object(
            provider, "_chat_http_cancellable_async", return_value="hello"
        ) as mock_async:
            result = provider._chat_http_cancellable("msg", "model", controller)

        assert result == "hello"
        mock_async.assert_called_once_with("msg", "model", controller)

    def test_chat_http_cancellable_with_running_loop(self) -> None:
        """When an event loop is already running, _chat_http_cancellable should not crash."""
        provider = DeepSeekProvider(_test_settings())
        controller = CancellationController()

        async def inner() -> str:
            with patch.object(
                provider, "_chat_http_cancellable_async", return_value="hello"
            ) as mock_async:
                result = provider._chat_http_cancellable("msg", "model", controller)
                mock_async.assert_called_once_with("msg", "model", controller)
            return result

        # Simulate being called from a thread that already has an event loop
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(inner())
            assert result == "hello"
        finally:
            loop.close()

    def test_chat_http_cancellable_already_cancelled(self) -> None:
        """If controller is already cancelled, should raise RuntimeError immediately."""
        provider = DeepSeekProvider(_test_settings())
        controller = CancellationController()
        controller.cancel()

        with pytest.raises(RuntimeError, match="模型调用已取消"):
            provider._chat_http_cancellable("msg", "model", controller)
