from __future__ import annotations

from app.config import Settings
from app.tools.registry import get_platform_tools
from tests.fakes import InMemoryTaskStorage


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
        assert "list_uploaded_resources" not in names

    def test_includes_task_scoped_resource_tools_when_task_id_is_available(self, test_settings):
        tools = get_platform_tools(test_settings, task_id="task-1")
        names = [t.name for t in tools]

        assert {
            "list_uploaded_resources",
            "inspect_resource",
            "read_resource_text",
            "read_resource_table",
        }.issubset(set(names))

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

    def test_tavily_tool_reuses_fresh_cache_until_refresh_requested(
        self, tmp_path, monkeypatch
    ):
        calls: list[str] = []

        def fake_run(api_key: str, query: str, *, max_results: int, topic: str) -> str:
            calls.append(query)
            return f"fresh:{query}:{max_results}:{topic}"

        monkeypatch.setattr("app.tools.tavily_search._run_tavily_search", fake_run)
        monkeypatch.setenv("TAVILY_API_KEY", "runtime-key")
        storage = InMemoryTaskStorage(tmp_path / "tasks")
        state = storage.create_task(message=None, model="deepseek:deepseek-chat")
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            tavily_api_key="settings-tvly-key",
        )

        [tool] = [t for t in get_platform_tools(settings, task_id=state.task_id, storage=storage) if t.name == "tavily_search"]

        cached = tool.invoke({"query": "上海天气"})
        repeat = tool.invoke({"query": "上海天气"})
        refreshed = tool.invoke({"query": "刷新上海天气"})

        assert calls == ["上海天气", "刷新上海天气"]
        assert "fresh:上海天气" in cached
        assert "[Cached within this conversation" in repeat
        assert "fresh:刷新上海天气" in refreshed
