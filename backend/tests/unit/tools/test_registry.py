from __future__ import annotations

from app.config import Settings
from app.tools.registry import get_platform_tools
from tests.fakes import InMemoryTaskStorage


class TestGetPlatformTools:
    def test_excludes_searxng_when_url_is_empty(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            searxng_url="",
        )
        tools = get_platform_tools(settings)
        names = [t.name for t in tools]
        assert "searxng_search" not in names

    def test_includes_searxng_when_url_is_set(self, tmp_path):
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            searxng_url="http://127.0.0.1:8181/",
        )
        tools = get_platform_tools(settings)
        names = [t.name for t in tools]
        assert "searxng_search" in names

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
        assert "create_word_document" not in names

    def test_includes_word_artifact_tool_when_run_context_is_available(self, test_settings, tmp_path):
        storage = InMemoryTaskStorage(tmp_path / "tasks")

        tools = get_platform_tools(
            test_settings,
            task_id="task-1",
            run_id="run-1",
            storage=storage,
        )
        names = [t.name for t in tools]

        assert "create_word_document" in names

    def test_searxng_tool_uses_settings_url_not_runtime_environment(self, tmp_path, monkeypatch):
        captured: dict[str, object] = {}

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {
                    "results": [
                        {
                            "title": "Result",
                            "url": "https://example.test",
                            "content": "Snippet",
                            "engine": "test",
                        }
                    ]
                }

        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs["params"]
            return FakeResponse()

        monkeypatch.setenv("MYAGENT_SEARXNG_URL", "http://runtime.example/")
        monkeypatch.setattr("app.tools.searxng_search.httpx.get", fake_get)
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            searxng_url="http://settings.example/base/",
        )

        [tool] = get_platform_tools(settings)
        result = tool.invoke({"query": "MyAgent", "max_results": 3, "topic": "news"})

        assert captured["url"] == "http://settings.example/base/search"
        assert captured["params"] == {
            "q": "MyAgent",
            "format": "json",
            "categories": "news",
        }
        assert "https://example.test" in result
        assert "来源引擎：test" in result

    def test_searxng_tool_reuses_fresh_cache_until_refresh_requested(
        self, tmp_path, monkeypatch
    ):
        calls: list[str] = []

        def fake_run(
            base_url: str,
            query: str,
            *,
            max_results: int,
            topic: str,
            language: str,
            timeout_seconds: float,
        ) -> str:
            calls.append(f"{base_url}:{query}:{language}:{timeout_seconds}")
            return f"fresh:{query}:{max_results}:{topic}:{language}"

        monkeypatch.setattr("app.tools.searxng_search._run_searxng_search", fake_run)
        storage = InMemoryTaskStorage(tmp_path / "tasks")
        state = storage.create_task(message=None, model="deepseek-v4-flash")
        settings = Settings(
            task_root=tmp_path / "tasks",
            workspace_root=tmp_path / "tasks",
            searxng_url="http://127.0.0.1:8181/",
        )

        [tool] = [
            t
            for t in get_platform_tools(settings, task_id=state.task_id, storage=storage)
            if t.name == "searxng_search"
        ]

        cached = tool.invoke({"query": "上海天气"})
        repeat = tool.invoke({"query": "上海天气"})
        refreshed = tool.invoke({"query": "刷新上海天气"})

        assert calls == [
            "http://127.0.0.1:8181/:上海天气:auto:15.0",
            "http://127.0.0.1:8181/:刷新上海天气:auto:15.0",
        ]
        assert "fresh:上海天气" in cached
        assert "[本会话缓存结果" in repeat
        assert "fresh:刷新上海天气" in refreshed
