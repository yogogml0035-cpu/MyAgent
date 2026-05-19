from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[3]
database = {"tasks": {}}


def frontend_send_message(user_text):
    print("1. frontend_send_message: 前端拿到用户输入")
    task_id = "task-1"

    if task_id not in database["tasks"]:
        database["tasks"][task_id] = {
            "status": "idle",
            "messages": [],
            "runs": [],
            "events": [],
        }
        print("   创建了一个新的 task 容器")

    return api_send_message(task_id, user_text)


def api_send_message(task_id, user_text):
    print("2. api_send_message: 后端 API 收到消息")
    task = database["tasks"][task_id]
    run_id = f"run-{len(task['runs']) + 1}"

    task["status"] = "running"
    task["messages"].append({"role": "user", "content": user_text})
    task["runs"].append({"id": run_id, "status": "running"})
    task["events"].append({"type": "run_started", "message": f"{run_id} started"})
    print(f"   写入 user message，创建 {run_id}")

    return runner_start(task_id, run_id, user_text)


def runner_start(task_id, run_id, user_text):
    print("3. runner_start: Runner 开始执行")
    task = database["tasks"][task_id]
    task["events"].append({"type": "thinking", "message": "Runner 准备调用 Agent"})

    answer = fake_agent(user_text)

    task["events"].append({"type": "final_answer", "message": answer})
    print("   Agent 返回最终答案")

    return storage_finish_run(task_id, run_id, answer)


def fake_agent(user_text):
    print("4. fake_agent: 最小 Agent 逻辑")
    return f"你刚才说的是：{user_text}。这是最小示例给出的回答。"


def storage_finish_run(task_id, run_id, answer):
    print("5. storage_finish_run: Storage 写回最终状态")
    task = database["tasks"][task_id]

    task["status"] = "complete"
    task["messages"].append({"role": "assistant", "content": answer})
    task["runs"][-1]["status"] = "complete"
    task["events"].append({"type": "task_completed", "message": f"{run_id} completed"})

    return frontend_render(task_id)


def frontend_render(task_id):
    print("6. frontend_render: 前端重新读取状态并渲染")
    task = database["tasks"][task_id]

    return {
        "task_id": task_id,
        "status": task["status"],
        "messages": task["messages"],
        "events": task["events"],
    }


def assert_project_links():
    hook = (REPO_ROOT / "frontend/hooks/use-task-workspace.ts").read_text(encoding="utf-8")
    api = (REPO_ROOT / "backend/app/api/tasks.py").read_text(encoding="utf-8")
    runner = (REPO_ROOT / "backend/app/runner/core.py").read_text(encoding="utf-8")

    assert "handleSubmit" in hook, "真实前端应有 handleSubmit 编排发送流程"
    assert "postTaskMessage" in hook, "真实前端应调用 postTaskMessage 发送消息"
    assert "storage.start_run(" in api, "真实后端应先 start_run"
    assert "runner.start_background" in api, "真实后端应在 API 中启动后台 Runner"
    assert "def start_background(" in runner, "真实 Runner 应有 start_background 入口"


if __name__ == "__main__":
    result = frontend_send_message("帮我总结这次任务")

    assert result["status"] == "complete"
    assert result["messages"][-1]["role"] == "assistant"
    assert result["events"][0]["type"] == "run_started"
    assert_project_links()

    print("\n页面最后拿到的数据：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("OK: 你已经跑通了一个对应真实项目主链路的最小示例。")
