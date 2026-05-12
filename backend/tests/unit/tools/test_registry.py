from __future__ import annotations

from app.config import Settings
from app.tools.registry import get_platform_tools


class TestGetPlatformTools:
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

    def test_no_custom_filesystem_tools(self, test_settings):
        tools = get_platform_tools(test_settings)
        names = [t.name for t in tools]
        assert "read_file" not in names
        assert "write_file" not in names
        assert "list_files" not in names

    def test_tavily_tool_uses_settings_key_not_runtime_environment(self, tmp_path, monkeypatch):
        captured: dict[str, str] = {}

        class FakeTavilyClient:
            def __init__(self, *, api_key: str) -> None:
                captured["api_key"] = api_key

            def search(self, **kwargs):
                return {
                    "results": [
                        {
                            "title": "Result",
                            "url": "https://example.test",
                            "content": "Snippet",
                        }
                    ]
                }

        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setattr("app.tools.tavily_search.TavilyClient", FakeTavilyClient)
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            tavily_api_key="settings-tvly-key",
        )

        [tool] = get_platform_tools(settings)
        result = tool.invoke({"query": "MyAgent", "max_results": 3})

        assert captured["api_key"] == "settings-tvly-key"
        assert "https://example.test" in result
