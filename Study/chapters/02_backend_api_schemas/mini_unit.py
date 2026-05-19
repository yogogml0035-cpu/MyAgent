from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

BACKEND_TO_FRONTEND_FIELD = {
    "task_id": "id",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "active_run_id": "activeRunId",
    "run_count": "runCount",
    "upload_count": "uploadCount",
    "needs_input": "needsInput",
}

KNOWN_STATUSES = {
    "idle",
    "running",
    "complete",
    "failed",
    "cancelled",
    "needs_input",
    "interrupted",
}
DEFAULT_MODE = "auto"


def normalize_task_state(raw: dict) -> dict:
    result = {}
    for key, value in raw.items():
        result[BACKEND_TO_FRONTEND_FIELD.get(key, key)] = value
    result["status"] = result["status"] if result.get("status") in KNOWN_STATUSES else "unknown"
    return result


def validate_model(model_id: str, registry: set[str]) -> bool:
    return model_id in registry

def build_message_request_payload(message: str, model: str, mode: str = DEFAULT_MODE) -> dict:
    return {
        "content": message,
        "message": message,
        "model": model,
        "mode": mode,
    }


def assert_source_contracts() -> None:
    schemas = (REPO_ROOT / "backend/app/schemas.py").read_text(encoding="utf-8")
    tasks_api = (REPO_ROOT / "backend/app/api/tasks.py").read_text(encoding="utf-8")
    task_state = (REPO_ROOT / "frontend/app/task-state.ts").read_text(encoding="utf-8")
    config = (REPO_ROOT / "backend/app/config.py").read_text(encoding="utf-8")

    assert "MAX_MESSAGE_CHARS = 8_000" in schemas
    assert 'TaskStatus = Literal[' in schemas
    for status in KNOWN_STATUSES:
        assert f'"{status}"' in schemas, f"schemas.py 缺少状态 {status}"
    assert "async def create_task" in tasks_api
    assert "async def send_message" in tasks_api
    assert "_validate_runnable_model" in tasks_api
    assert "include_events: bool = True" in tasks_api
    assert 'mode: TaskMode = "auto"' in schemas
    assert 'input_scope: InputScope = "auto"' in schemas
    assert "record.id ?? record.task_id ?? record.taskId" in task_state
    assert "buildMessageRequestPayload" in task_state
    assert "mode: options.mode ?? DEFAULT_MESSAGE_MODE" in task_state
    assert "MODEL_REGISTRY" in config


if __name__ == "__main__":
    backend_state = {
        "task_id": "task-1",
        "status": "running",
        "created_at": "2026-01-01T00:00:00Z",
        "active_run_id": "run-1",
        "upload_count": 2,
    }
    frontend_state = normalize_task_state(backend_state)

    assert frontend_state["id"] == "task-1"
    assert frontend_state["activeRunId"] == "run-1"
    assert frontend_state["uploadCount"] == 2
    payload = build_message_request_payload("请分析这些文件", "deepseek-v4-flash")
    assert payload["mode"] == "auto"
    assert validate_model("deepseek-v4-flash", {"deepseek-v4-flash"})
    assert not validate_model("fake:model", {"deepseek-v4-flash"})
    assert_source_contracts()

    print(frontend_state)
    print(payload)
    print("OK: 你已经理解了后端 schema 到前端状态的基本映射。")
