from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.graph.state import CompiledStateGraph

from app.agent.factory import build_agent


def _mock_model():
    m = MagicMock()
    m.name = "test-model"
    return m


class TestBuildAgent:
    @patch("app.agent.factory._create_model", return_value=_mock_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_returns_compiled_graph(self, mock_create, mock_model_fn, test_settings):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        result = build_agent(test_settings)
        assert result is fake_graph
        mock_create.assert_called_once()

    @patch("app.agent.factory._create_model", return_value=_mock_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_with_custom_model(self, mock_create, mock_model_fn, test_settings):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        result = build_agent(test_settings, model="deepseek-v4-flash-thinking")
        assert result is fake_graph
        mock_model_fn.assert_called_once_with("deepseek-v4-flash-thinking", test_settings)

    @patch("app.agent.factory._create_model", return_value=_mock_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_passes_tools_and_skills(self, mock_create, mock_model_fn, test_settings):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        def dummy_tool(x):
            return x
        build_agent(
            test_settings,
            tools=[dummy_tool],
            skills=["./skills"],
        )
        call_kwargs = mock_create.call_args
        assert dummy_tool in call_kwargs.kwargs["tools"]
        assert call_kwargs.kwargs["skills"] == ["./skills"]

    @patch("app.agent.factory._create_model", return_value=_mock_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_passes_system_prompt(self, mock_create, mock_model_fn, test_settings):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        build_agent(test_settings, system_prompt="请使用资源工具。")

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["system_prompt"] == "请使用资源工具。"

    @patch("app.agent.factory._create_model", return_value=_mock_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_backend_uses_composite_memory_routes(self, mock_create, mock_model_fn, test_settings):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph
        store = object()

        build_agent(test_settings, store=store, workspace_dir=test_settings.workspace_root / "task-1")

        backend = mock_create.call_args.kwargs["backend"]
        assert backend.default.cwd == (test_settings.workspace_root / "task-1").resolve()
        assert "/scratch/" in backend.routes
        assert "/memories/" in backend.routes
        assert mock_create.call_args.kwargs["store"] is store
