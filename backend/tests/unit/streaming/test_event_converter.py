from __future__ import annotations

from app.streaming.event_converter import convert_stream_event


class TestConvertStreamEvent:
    def test_tool_call_keeps_raw_payload_and_adds_live_metadata(self):
        record = convert_stream_event(
            {
                "type": "tool_call",
                "data": {
                    "id": "call-1",
                    "name": "tavily_search",
                    "args": {"query": "上海天气", "max_results": 5},
                    "is_subgraph": False,
                },
            },
            "task-1",
            "run-1",
            seq=3,
        )

        assert record is not None
        assert record.type == "tool_call"
        assert record.message == "Calling tool: tavily_search"
        assert record.payload["name"] == "tavily_search"
        assert record.payload["args"] == {"query": "上海天气", "max_results": 5}
        assert record.payload["live"] == {
            "schema_version": 1,
            "kind": "tool_call",
            "stage": "using_tool",
            "tool_name": "tavily_search",
            "tool_label": "联网搜索",
            "tool_call_id": "call-1",
            "parameter_items": [
                {"key": "query", "value": "上海天气", "truncated": False},
                {"key": "max_results", "value": 5},
            ],
            "diagnostic_label": "tool_call",
        }

    def test_partial_tool_call_is_tool_selection_not_execution(self):
        record = convert_stream_event(
            {
                "type": "tool_call",
                "data": {
                    "id": "call-1",
                    "name": "tavily_search",
                    "args": '{"query"',
                    "partial": True,
                    "is_subgraph": False,
                },
            },
            "task-1",
            "run-1",
            seq=3,
        )

        assert record is not None
        assert record.payload["live"]["stage"] == "selecting_tool"
        assert record.payload["live"]["diagnostic_label"] == "tool_call_delta"

    def test_tool_result_adds_live_result_metadata(self):
        record = convert_stream_event(
            {
                "type": "tool_result",
                "data": {
                    "tool_call_id": "call-1",
                    "name": "tavily_search",
                    "content": "result",
                    "status": "success",
                },
            },
            "task-1",
            "run-1",
            seq=4,
        )

        assert record is not None
        assert record.type == "tool_result"
        assert record.payload["content"] == "result"
        assert record.payload["live"] == {
            "schema_version": 1,
            "kind": "tool_result",
            "stage": "completed",
            "tool_name": "tavily_search",
            "tool_label": "联网搜索",
            "tool_call_id": "call-1",
            "parameter_items": [],
            "result_status": "success",
        }

    def test_status_update_maps_internal_nodes_to_chinese_live_stage(self):
        record = convert_stream_event(
            {
                "type": "state_update",
                "data": {
                    "node": "SkillsMiddleware.before_agent",
                    "state_keys": ["messages"],
                    "is_subgraph": False,
                },
            },
            "task-1",
            "run-1",
            seq=5,
        )

        assert record is not None
        assert record.type == "status_update"
        assert record.message == "State update: SkillsMiddleware.before_agent"
        assert record.payload["node"] == "SkillsMiddleware.before_agent"
        assert record.payload["live"]["stage"] == "preparing"
        assert record.payload["live"]["display_text"] == "正在准备任务..."
        assert record.payload["live"]["diagnostic_label"] == "SkillsMiddleware.before_agent"

    def test_patch_tool_calls_before_agent_is_preparing_not_tool_execution(self):
        record = convert_stream_event(
            {
                "type": "state_update",
                "data": {
                    "node": "PatchToolCallsMiddleware.before_agent",
                    "state_keys": ["messages"],
                    "is_subgraph": False,
                },
            },
            "task-1",
            "run-1",
            seq=5,
        )

        assert record is not None
        assert record.payload["live"]["stage"] == "preparing"
        assert record.payload["live"]["display_text"] == "正在准备任务..."

    def test_model_status_update_is_thinking_not_final_generation(self):
        record = convert_stream_event(
            {"type": "state_update", "data": {"node": "model", "state_keys": []}},
            "task-1",
            "run-1",
            seq=6,
        )

        assert record is not None
        assert record.payload["live"]["stage"] == "thinking"
        assert record.payload["live"]["display_text"] == "AI正在思考..."

    def test_after_model_middleware_status_is_not_preparing(self):
        record = convert_stream_event(
            {
                "type": "state_update",
                "data": {
                    "node": "TodoListMiddleware.after_model",
                    "state_keys": [],
                    "is_subgraph": False,
                },
            },
            "task-1",
            "run-1",
            seq=6,
        )

        assert record is not None
        assert record.payload["live"]["stage"] == "organizing_state"
        assert record.payload["live"]["display_text"] == "模型输出已完成"

    def test_answer_delta_behavior_is_unchanged(self):
        record = convert_stream_event(
            {"type": "message_chunk", "data": {"content": "。", "is_subgraph": False}},
            "task-1",
            "run-1",
            seq=7,
        )

        assert record is not None
        assert record.type == "assistant_answer_delta"
        assert record.message == "。"
        assert record.payload == {
            "schema_version": 1,
            "stream_index": 7,
            "content": "。",
            "is_subgraph": False,
        }

    def test_thinking_delta_adds_live_metadata(self):
        record = convert_stream_event(
            {
                "type": "thinking_chunk",
                "data": {"content": "先判断问题是否需要联网。", "is_subgraph": False},
            },
            "task-1",
            "run-1",
            seq=8,
        )

        assert record is not None
        assert record.type == "assistant_thinking_delta"
        assert record.message == "先判断问题是否需要联网。"
        assert record.payload == {
            "schema_version": 1,
            "stream_index": 8,
            "content": "先判断问题是否需要联网。",
            "is_subgraph": False,
            "live": {
                "schema_version": 1,
                "kind": "think",
                "stage": "thinking",
                "display_text": "AI正在思考...",
                "diagnostic_label": "model.reasoning_content",
                "parameter_items": [{"key": "is_subgraph", "value": False}],
            },
        }
