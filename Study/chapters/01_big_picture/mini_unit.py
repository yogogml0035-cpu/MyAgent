from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

PIPELINE = [
    "frontend.submit",
    "api.validate",
    "storage.create_task",
    "storage.start_run",
    "runner.start_background",
    "agent.stream",
    "storage.append_event",
    "storage.finish_run",
    "frontend.render",
]


def assert_pipeline_order(steps: list[str]) -> None:
    positions = {step: index for index, step in enumerate(steps)}
    assert positions["storage.start_run"] < positions["runner.start_background"], (
        "storage 必须先 start_run，Runner 才能拿到同一个 run_id"
    )
    assert positions["agent.stream"] < positions["storage.finish_run"], (
        "Agent 流结束后，storage 才能写 complete/failed/cancelled 终态"
    )
    assert positions["storage.append_event"] < positions["frontend.render"], (
        "前端展示的是已经被 storage 记录下来的事件"
    )


def describe(steps: list[str]) -> str:
    return " -> ".join(steps)


def assert_source_anchors() -> None:
    page = (REPO_ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    workspace = (REPO_ROOT / "frontend/components/chat/TaskWorkspace.tsx").read_text(
        encoding="utf-8"
    )
    main = (REPO_ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    tasks = (REPO_ROOT / "backend/app/api/tasks.py").read_text(encoding="utf-8")

    assert "return <TaskWorkspace />" in page, "前端页面入口应该只挂载 TaskWorkspace"
    assert "useTaskWorkspace()" in workspace, "TaskWorkspace 应该通过 hook 获得状态和动作"
    for router_name in [
        "tasks_router",
        "files_router",
        "artifacts_router",
        "streaming_router",
        "models_router",
    ]:
        assert f"app.include_router({router_name})" in main, f"main.py 缺少 {router_name}"
    assert "runner.start_background" in tasks, "任务 API 必须调度后台 Runner"


if __name__ == "__main__":
    assert_pipeline_order(PIPELINE)
    assert_source_anchors()
    print(describe(PIPELINE))
    print("OK: 你已经跑通了 MyAgent 的最小架构链路。")
