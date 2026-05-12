from __future__ import annotations

from app.memory import build_task_memory_text


def test_build_task_memory_text_is_high_level_and_bounded():
    text = build_task_memory_text(
        task_id="task-1",
        run_id="run-1",
        user_goal="请帮我分析一个很长的目标" * 50,
        final_answer="这是最终回答" * 80,
    )

    assert "用户目标:" in text
    assert "最终回答摘要:" in text
    assert "task-1" in text
    assert len(text) < 800
