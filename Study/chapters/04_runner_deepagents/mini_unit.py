from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class AIMessage:
    content: str
    tool_calls: list[str] | None = None


def extract_final_answer(messages: list[AIMessage]) -> str:
    for message in reversed(messages):
        if message.content and not message.tool_calls:
            return message.content
    return ""


def convert_stream_event(event: dict, seq: int) -> dict:
    event_type = event["type"]
    if event_type == "message_chunk":
        record_type = "assistant_answer_delta"
    elif event_type == "tool_call":
        record_type = "tool_call"
    else:
        record_type = "status_update"
    return {
        "seq": seq,
        "type": record_type,
        "payload": event.get("data", {}),
    }


def assert_source_contracts() -> None:
    runner = (REPO_ROOT / "backend/app/runner/core.py").read_text(encoding="utf-8")
    factory = (REPO_ROOT / "backend/app/agent/factory.py").read_text(encoding="utf-8")
    registry = (REPO_ROOT / "backend/app/tools/registry.py").read_text(encoding="utf-8")
    searxng = (REPO_ROOT / "backend/app/tools/searxng_search.py").read_text(encoding="utf-8")
    config = (REPO_ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    adapter = (REPO_ROOT / "backend/app/streaming/v2_adapter.py").read_text(encoding="utf-8")
    converter = (REPO_ROOT / "backend/app/streaming/event_converter.py").read_text(
        encoding="utf-8"
    )

    assert "def start_background(" in runner
    assert "async def start(" in runner
    assert "context_builder.build" in runner
    assert "_recall_memory_context" in runner
    assert "_resource_manifest_context" in runner
    assert "storage.append_event" in runner
    assert "final_answer" in runner
    assert "create_deep_agent(" in factory
    assert "CompositeBackend" in factory
    assert "create_searxng_search_tool" in registry
    assert "settings.searxng_url" in registry
    assert "searxng_search" in searxng
    assert "MYAGENT_SEARXNG_URL" in config
    assert 'stream_mode=_V2_MODES' in adapter
    assert 'version="v2"' in adapter
    assert '"message_chunk": "assistant_answer_delta"' in converter


if __name__ == "__main__":
    messages = [
        AIMessage("我需要先查文件", tool_calls=["read_resource_text"]),
        AIMessage("根据文件内容，最终结论是：风险较低。"),
    ]
    assert extract_final_answer(messages) == "根据文件内容，最终结论是：风险较低。"

    events = [
        convert_stream_event({"type": "tool_call", "data": {"name": "read_resource_text"}}, 1),
        convert_stream_event({"type": "message_chunk", "data": {"content": "最终"}}, 2),
    ]
    assert [event["type"] for event in events] == ["tool_call", "assistant_answer_delta"]
    assert_source_contracts()

    print("final:", extract_final_answer(messages))
    print("events:", events)
    print("OK: 你已经理解 Runner 如何区分中间流和最终回答。")
