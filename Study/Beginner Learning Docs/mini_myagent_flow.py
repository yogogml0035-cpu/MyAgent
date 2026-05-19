def append_event(task, event_type, text):
    task["next_event_seq"] = task["next_event_seq"] + 1
    task["events"].append(
        {
            "seq": task["next_event_seq"],
            "type": event_type,
            "text": text,
        }
    )


def create_task(user_text):
    task = {
        "id": "task-1",
        "status": "queued",
        "messages": [],
        "events": [],
        "next_event_seq": 0,
    }

    task["messages"].append({"role": "user", "content": user_text})
    append_event(task, "task_created", "用户创建了一个任务")

    return task


def run_task(task):
    task["status"] = "running"
    append_event(task, "run_started", "Runner 开始执行任务")

    user_text = task["messages"][0]["content"]
    answer = "我收到你的任务：" + user_text

    task["messages"].append({"role": "assistant", "content": answer})
    append_event(task, "assistant_message", "Assistant 生成了回复")

    task["status"] = "completed"
    append_event(task, "task_completed", "任务完成")


def show_task(task):
    print("任务状态:", task["status"])

    print("\n消息:")
    for message in task["messages"]:
        print("-", message["role"] + ":", message["content"])

    print("\n事件:")
    for event in task["events"]:
        print("-", event["seq"], event["type"], event["text"])


if __name__ == "__main__":
    user_text = "请用一句话说明 MyAgent 的任务流"
    task = create_task(user_text)
    run_task(task)
    show_task(task)
