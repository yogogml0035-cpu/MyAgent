from __future__ import annotations

from app.agent_activity import DeepAgentActivityProjector, _split_stream_chunk


class TestSplitStreamChunk:
    """Tests for _split_stream_chunk v2 dict format support."""

    def test_v2_dict_updates(self):
        chunk = {"type": "updates", "ns": ("tools:abc123",), "data": {"node": "value"}}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "updates"
        assert data == {"node": "value"}
        assert path == ["tools:abc123"]

    def test_v2_dict_messages(self):
        chunk = {"type": "messages", "ns": (), "data": ("token", "meta")}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "messages"
        assert data == ("token", "meta")
        assert path == []

    def test_v2_dict_custom(self):
        chunk = {"type": "custom", "ns": ["tools:x"], "data": {"progress": 50}}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "custom"
        assert data == {"progress": 50}
        assert path == ["tools:x"]

    def test_v2_dict_missing_type_returns_fallback(self):
        chunk = {"ns": ("tools:a",), "data": "value"}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode is None
        assert data == chunk
        assert path == []

    def test_v2_dict_unknown_type_returns_fallback(self):
        chunk = {"type": "unknown", "ns": (), "data": "value"}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode is None
        assert data == chunk
        assert path == []

    def test_tuple_three_element(self):
        chunk = (("ns",), "updates", {"node": "value"})
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "updates"
        assert data == {"node": "value"}
        assert path == ["ns"]

    def test_tuple_two_element_mode_first(self):
        chunk = ("updates", {"node": "value"})
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "updates"
        assert data == {"node": "value"}
        assert path == []

    def test_tuple_nested(self):
        chunk = (("ns",), ("updates", {"node": "value"}))
        mode, data, path = _split_stream_chunk(chunk)
        assert mode == "updates"
        assert data == {"node": "value"}
        assert path == ["ns"]

    def test_plain_dict_without_type_still_fallback(self):
        chunk = {"data": "something"}
        mode, data, path = _split_stream_chunk(chunk)
        assert mode is None
        assert data == chunk
        assert path == []


class TestDeepAgentActivityProjectorCustom:
    """Tests for DeepAgentActivityProjector custom stream handling."""

    def test_observe_custom_dict(self):
        sink_calls = []
        projector = DeepAgentActivityProjector(
            task_id="t1", run_id="r1", sink=sink_calls.append
        )
        projector.observe_stream_chunk(
            {"type": "custom", "ns": ("tools:search",), "data": {"status": "starting", "topic": "搜索中"}}
        )
        assert len(sink_calls) == 1
        payload = sink_calls[0]
        assert payload["activity_kind"] == "progress"
        assert payload["phase"] == "tool_use"
        assert "搜索中" in payload["summary"]
        assert payload["live"]["kind"] == "status"

    def test_observe_custom_string(self):
        sink_calls = []
        projector = DeepAgentActivityProjector(
            task_id="t1", run_id="r1", sink=sink_calls.append
        )
        projector.observe_stream_chunk(
            {"type": "custom", "ns": (), "data": "处理完成"}
        )
        assert len(sink_calls) == 1
        payload = sink_calls[0]
        assert "处理完成" in payload["summary"]

    def test_observe_custom_empty_data(self):
        sink_calls = []
        projector = DeepAgentActivityProjector(
            task_id="t1", run_id="r1", sink=sink_calls.append
        )
        projector.observe_stream_chunk(
            {"type": "custom", "ns": ("tools:x",), "data": None}
        )
        assert len(sink_calls) == 1
        payload = sink_calls[0]
        assert payload["title"] == "自定义进度"


class TestAgentIdFromPath:
    def test_tools_prefix_first(self):
        from app.agent_activity import _agent_id_from_path

        assert _agent_id_from_path(["tools:abc123"]) == "tools:abc123"

    def test_tools_prefix_among_others(self):
        from app.agent_activity import _agent_id_from_path

        assert _agent_id_from_path(["tools:abc123", "model_request:def456"]) == "tools:abc123"

    def test_empty_path_returns_none(self):
        from app.agent_activity import _agent_id_from_path

        assert _agent_id_from_path([]) is None

    def test_fallback_without_tools_prefix(self):
        from app.agent_activity import _agent_id_from_path

        assert _agent_id_from_path(["some_node"]) == "some_node"

    def test_skips_updates_and_messages(self):
        from app.agent_activity import _agent_id_from_path

        assert _agent_id_from_path(["updates", "real_node"]) == "real_node"
