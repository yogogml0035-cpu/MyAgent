from __future__ import annotations

from app.config import Settings
from app.conversation_context import ConversationContextBuilder
from app.schemas import ChatMessage
from tests.fakes import InMemoryTaskStorage


def test_context_builder_injects_previous_messages_without_current_tail(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        recent_message_limit=12,
    )
    storage = InMemoryTaskStorage(settings.task_root)
    state = storage.create_task(message=None, model="deepseek:deepseek-chat")
    run = storage.start_run(
        state.task_id,
        message="上海今日天气",
        model="deepseek:deepseek-chat",
        expected_statuses={"idle"},
    )
    assert run is not None
    _, run_id = run
    storage.update_task_if_status_and_append_event(
        state.task_id,
        {"running"},
        status="complete",
        run_id=run_id,
        append_message=ChatMessage(role="assistant", content="上海今日多云，适合出行。", created_at=""),
        event_type="task_completed",
        event_message="任务已完成。",
    )
    followup = storage.start_run(
        state.task_id,
        message="我刚才问了什么？",
        model="deepseek:deepseek-chat",
        expected_statuses={"complete"},
    )
    assert followup is not None

    context = ConversationContextBuilder(settings, storage).build(
        task_id=state.task_id,
        current_message="我刚才问了什么？",
    )

    contents = [str(message.content) for message in context.messages]
    assert any("同一 MyAgent 会话" in content for content in contents)
    assert any("上海今日天气" in content for content in contents)
    assert all(content != "我刚才问了什么？" for content in contents)
    assert context.event_payload()["recent_message_count"] == 2


def test_context_builder_summarizes_long_history(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        recent_message_limit=2,
    )
    storage = InMemoryTaskStorage(settings.task_root)
    state = storage.create_task(message=None, model="deepseek:deepseek-chat")
    for index in range(4):
        run = storage.start_run(
            state.task_id,
            message=f"历史问题 {index}",
            model="deepseek:deepseek-chat",
            expected_statuses={"idle", "complete"},
        )
        assert run is not None
        _, run_id = run
        storage.update_task_if_status_and_append_event(
            state.task_id,
            {"running"},
            status="complete",
            run_id=run_id,
            append_message=ChatMessage(role="assistant", content=f"历史回答 {index}", created_at=""),
            event_type="task_completed",
            event_message="任务已完成。",
        )
    storage.start_run(
        state.task_id,
        message="继续",
        model="deepseek:deepseek-chat",
        expected_statuses={"complete"},
    )

    context = ConversationContextBuilder(settings, storage).build(
        task_id=state.task_id,
        current_message="继续",
    )

    assert context.summary
    assert "历史问题 0" in context.summary
    assert context.recent_message_count == 2


def test_context_builder_injects_fresh_tool_cache_unless_refresh_requested(tmp_path):
    settings = Settings(
        task_root=tmp_path / "tasks",
        workspace_root=tmp_path / "tasks",
        recent_message_limit=12,
    )
    storage = InMemoryTaskStorage(settings.task_root)
    state = storage.create_task(message=None, model="deepseek:deepseek-chat")
    storage.cache_tool_result(
        state.task_id,
        tool_name="searxng_search",
        query="上海天气",
        result_text="上海今日多云。",
        ttl_seconds=600,
    )

    context = ConversationContextBuilder(settings, storage).build(
        task_id=state.task_id,
        current_message="刚才查到的天气是什么？",
    )

    assert context.cached_tool_results
    assert any("上海天气" in str(message.content) for message in context.messages)
    assert context.event_payload()["cached_tool_result_count"] == 1

    refresh_context = ConversationContextBuilder(settings, storage).build(
        task_id=state.task_id,
        current_message="刷新一下上海天气",
    )

    assert refresh_context.cached_tool_results == []
