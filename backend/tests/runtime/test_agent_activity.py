from __future__ import annotations

from app.agent_activity import _split_stream_chunk


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
