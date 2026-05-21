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
            searxng_url="http://127.0.0.1:8181/",
        )

        from app.tools.registry import get_platform_tools

        tools = get_platform_tools(settings)

        result = build_agent(settings, tools=tools, skills=["./skills"])
        assert result is fake_graph

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["skills"] == ["/skills/"]
        assert call_kwargs["backend"] is not None

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

    @patch("app.agent.factory._create_model", return_value=_fake_model())
    @patch("app.agent.factory.create_deep_agent")
    def test_workspace_dir_creates_backend(self, mock_create, mock_model_fn, tmp_path):
        fake_graph = MagicMock(spec=CompiledStateGraph)
        mock_create.return_value = fake_graph

        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
        )

        workspace = tmp_path / "tasks" / "test-task"
        build_agent(settings, workspace_dir=workspace)

        call_kwargs = mock_create.call_args.kwargs
        backend = call_kwargs["backend"]
        assert backend is not None
        assert backend.default.cwd == workspace.resolve()
        assert "/scratch/" in backend.routes
