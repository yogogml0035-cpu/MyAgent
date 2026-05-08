from __future__ import annotations

import json

from app.streaming.sse import format_sse_done, format_sse_event, format_sse_message


class TestFormatSseEvent:
    def test_structure(self):
        result = format_sse_event("status", {"progress": 50})
        assert result.startswith("event: status\n")
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_data_is_valid_json(self):
        result = format_sse_event("status", {"key": "value"})
        data_line = result.split("data: ", 1)[1].rstrip("\n")
        parsed = json.loads(data_line)
        assert parsed == {"key": "value"}

    def test_unicode_content(self):
        result = format_sse_event("msg", {"text": "中文内容"})
        assert "中文内容" in result


class TestFormatSseMessage:
    def test_event_type_is_message(self):
        result = format_sse_message("hello")
        assert result.startswith("event: message\n")

    def test_content_field(self):
        result = format_sse_message("hello world")
        data_line = result.split("data: ", 1)[1].rstrip("\n")
        parsed = json.loads(data_line)
        assert parsed == {"content": "hello world"}


class TestFormatSseDone:
    def test_event_type_is_done(self):
        result = format_sse_done()
        assert result.startswith("event: done\n")

    def test_data_is_empty_object(self):
        result = format_sse_done()
        data_line = result.split("data: ", 1)[1].rstrip("\n")
        parsed = json.loads(data_line)
        assert parsed == {}
