from __future__ import annotations

from app.config import Settings
from app.tools.registry import get_platform_tools


class TestGetPlatformTools:
    def test_includes_filesystem_tools(self, test_settings):
        tools = get_platform_tools(test_settings)
        names = [t.name for t in tools]
        assert "read_file" in names
        assert "write_file" in names
        assert "list_files" in names

    def test_excludes_tavily_when_no_key(self, test_settings):
        tools = get_platform_tools(test_settings)
        names = [t.name for t in tools]
        assert "tavily_search" not in names

    def test_includes_tavily_when_key_set(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            tavily_api_key="tvly-test-key",
        )
        tools = get_platform_tools(settings)
        names = [t.name for t in tools]
        assert "tavily_search" in names

    def test_returns_at_least_three_tools(self, test_settings):
        tools = get_platform_tools(test_settings)
        assert len(tools) >= 3
