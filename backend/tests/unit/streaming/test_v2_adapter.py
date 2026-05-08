from __future__ import annotations

import inspect

from app.streaming.v2_adapter import stream_agent


class TestStreamAgentFunction:
    def test_is_async_generator(self):
        assert inspect.isasyncgenfunction(stream_agent)

    def test_signature_accepts_agent_messages_config(self):
        sig = inspect.signature(stream_agent)
        params = list(sig.parameters)
        assert "agent" in params
        assert "messages" in params
        assert "config" in params
