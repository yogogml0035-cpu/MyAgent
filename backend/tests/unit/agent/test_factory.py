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

        result = build_agent(test_settings, model="openai:gpt-4o")
        assert result is fake_graph
        mock_model_fn.assert_called_once_with("openai:gpt-4o", test_settings)

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

        build_agent(test_settings, system_prompt="Use resource tools.")

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["system_prompt"] == "Use resource tools."
