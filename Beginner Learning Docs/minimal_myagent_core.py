"""MyAgent core flow, reduced to one beginner-friendly Python file.

Run:
    python3 "Beginner Learning Docs/minimal_myagent_core.py"
"""

storage = {}


def frontend_send_message(user_text):
    print("Frontend: user clicked Send")

    task_id = backend_create_task(user_text)
    backend_run_agent(task_id)
    frontend_render_task(task_id)


def backend_create_task(user_text):
    task_id = "task-1"

    storage[task_id] = {
        "status": "running",
        "messages": [
            {"role": "user", "content": user_text},
        ],
        "events": [
            "task_created",
            "user_message_saved",
        ],
    }

    print("Backend: created task", task_id)
    return task_id


def backend_run_agent(task_id):
    task = storage[task_id]
    user_message = task["messages"][-1]["content"]

    task["events"].append("agent_started")
    assistant_answer = fake_agent(user_message)
    task["events"].append("agent_finished")

    task["messages"].append(
        {"role": "assistant", "content": assistant_answer}
    )
    task["status"] = "complete"
    task["events"].append("task_completed")


def fake_agent(user_message):
    return "我已经收到你的任务。最小版回答：先理解需求，再列出三步计划。你的原始输入是：" + user_message


def frontend_render_task(task_id):
    task = storage[task_id]

    print("\nFrontend: render latest task")
    print("Status:", task["status"])

    print("\nMessages:")
    for message in task["messages"]:
        print("-", message["role"] + ":", message["content"])

    print("\nEvents:")
    for event in task["events"]:
        print("-", event)


frontend_send_message("请帮我生成一份投标分析提纲")
