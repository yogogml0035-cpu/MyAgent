from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.graph.state import CompiledStateGraph

from app.agent.factory import build_agent
from app.config import Settings


def _fake_model():
    m = MagicMock()
    m.name = "test-model"
    return m


class TestFullAgentBuild:
    @patch("app.agent.factory._create_model", return_value=_fake_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_build_with_tools_and_skills(self, mock_create, mock_model_fn, tmp_path):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            tavily_api_key="tvly-test",
        )

        from app.tools.registry import get_platform_tools

        tools = get_platform_tools(settings)

        result = build_agent(settings, tools=tools, skills=["./skills"])
        assert result is fake_graph

        call_kwargs = mock_create.call_args.kwargs
        assert len(call_kwargs["tools"]) >= 3
        assert call_kwargs["skills"] == ["./skills"]

    @patch("app.agent.factory._create_model", return_value=_fake_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_build_with_subagents(self, mock_create, mock_model_fn, tmp_path):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )

        sub1 = MagicMock(name="sub-agent-1")
        sub2 = MagicMock(name="sub-agent-2")

        result = build_agent(settings, subagents=[sub1, sub2])
        assert result is fake_graph

        call_kwargs = mock_create.call_args.kwargs
        assert sub1 in call_kwargs["subagents"]
        assert sub2 in call_kwargs["subagents"]
