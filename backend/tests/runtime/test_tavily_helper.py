"""Tests for the shared _raw_tavily_search helper and DeepAgent tavily tool."""
from unittest.mock import MagicMock, patch

import pytest

from app.tools import _raw_tavily_search


class TestRawTavilySearch:
    """Tests for _raw_tavily_search helper."""

    def test_returns_empty_when_no_key(self):
        result = _raw_tavily_search("test query", "")
        assert result == {"results": [], "warning": "未配置 TAVILY_API_KEY"}

    def test_returns_empty_when_key_is_none(self):
        result = _raw_tavily_search("test query", None)  # type: ignore[arg-type]
        assert result == {"results": [], "warning": "未配置 TAVILY_API_KEY"}

    @patch("app.tools.httpx.post")
    def test_calls_tavily_api(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"title": "test", "url": "https://example.com"}]}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = _raw_tavily_search("test query", "fake-key", max_results=3)

        mock_post.assert_called_once_with(
            "https://api.tavily.com/search",
            json={"api_key": "fake-key", "query": "test query", "max_results": 3},
            timeout=20,
        )
        assert result == {"results": [{"title": "test", "url": "https://example.com"}]}

    @patch("app.tools.httpx.post")
    def test_passes_max_results(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        _raw_tavily_search("q", "key", max_results=10)

        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["max_results"] == 10


class TestDeepAgentTavilyTool:
    """Tests for tavily_search in DeepAgentRuntime.build_tools()."""

    def _make_runtime(self, tavily_key: str = "fake-key"):
        from unittest.mock import MagicMock
        from app.deep_agent_runtime import DeepAgentRuntime

        mock_file_tools = MagicMock()
        mock_file_tools.controller = MagicMock()
        return DeepAgentRuntime(
            mock_file_tools,
            agent_factory=MagicMock(),  # prevent deepagents import
            tavily_api_key=tavily_key,
        )

    def test_build_tools_includes_tavily(self):
        runtime = self._make_runtime()
        tools = runtime.build_tools()
        tool_names = [t.__name__ for t in tools]
        assert "tavily_search" in tool_names

    @patch("app.deep_agent_runtime._raw_tavily_search")
    def test_tavily_tool_delegates_to_helper(self, mock_search):
        mock_search.return_value = {"results": [{"title": "found"}]}
        runtime = self._make_runtime(tavily_key="test-key")
        tools = runtime.build_tools()
        tavily = next(t for t in tools if t.__name__ == "tavily_search")

        result = tavily("test query", max_results=5)

        mock_search.assert_called_once_with("test query", "test-key", 5)
        assert result == {"results": [{"title": "found"}]}

    def test_tavily_tool_checks_cancellation(self):
        from unittest.mock import MagicMock

        mock_file_tools = MagicMock()
        mock_controller = MagicMock()
        mock_file_tools.controller = mock_controller

        from app.deep_agent_runtime import DeepAgentRuntime
        runtime = DeepAgentRuntime(
            mock_file_tools,
            agent_factory=MagicMock(),
            tavily_api_key="key",
        )
        tools = runtime.build_tools()
        tavily = next(t for t in tools if t.__name__ == "tavily_search")

        # First raise_if_cancelled call raises
        mock_controller.raise_if_cancelled.side_effect = RuntimeError("cancelled")

        with pytest.raises(RuntimeError, match="cancelled"):
            tavily("query")

    def test_runtime_default_tavily_key_empty(self):
        from unittest.mock import MagicMock
        from app.deep_agent_runtime import DeepAgentRuntime

        runtime = DeepAgentRuntime(MagicMock(), agent_factory=MagicMock())
        assert runtime._tavily_api_key == ""
