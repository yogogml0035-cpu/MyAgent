import assert from "node:assert/strict";
import test from "node:test";

import {
  buildConversationHistoryItems,
  buildLogClipboardText,
  calculateLogProgress,
  formatFileSize,
  formatTime,
} from "../app/workspace-view";

test("calculateLogProgress keeps a five-step floor for sparse logs", () => {
  assert.deepEqual(calculateLogProgress(0), { count: 0, total: 5, percent: 0 });
  assert.deepEqual(calculateLogProgress(1), { count: 1, total: 5, percent: 20 });
  assert.deepEqual(calculateLogProgress(7), { count: 7, total: 7, percent: 100 });
});

test("formatFileSize uses compact binary units", () => {
  assert.equal(formatFileSize(241), "241 B");
  assert.equal(formatFileSize(241 * 1024), "241 KB");
  assert.equal(formatFileSize(1536 * 1024), "1.5 MB");
});

test("formatTime has stable empty and invalid fallbacks", () => {
  assert.equal(formatTime(), "--:--:--");
  assert.equal(formatTime(undefined, "short"), "");
  assert.equal(formatTime("not-a-date"), "--:--:--");
});

test("buildLogClipboardText includes level, title, and detail", () => {
  assert.equal(buildLogClipboardText([]), "暂无日志");
  assert.equal(
    buildLogClipboardText([
      {
        id: "log-1",
        title: "准备编排副本",
        detail: "开始 (0/5)",
        level: "info",
      },
    ]),
    "--:--:-- INFO 准备编排副本 开始 (0/5)",
  );
});

test("buildConversationHistoryItems exposes current draft when no messages exist", () => {
  assert.deepEqual(buildConversationHistoryItems([], "", "idle"), [
    {
      id: "draft",
      title: "新对话",
      subtitle: "等待开始",
      active: true,
    },
  ]);
});

test("buildConversationHistoryItems derives compact user-message history", () => {
  const items = buildConversationHistoryItems(
    [
      { id: "assistant-1", role: "assistant", content: "ready" },
      {
        id: "user-1",
        role: "user",
        content: "请分析这些 Markdown 投标文件里的异常线索，并输出报告",
        createdAt: "2026-04-27T08:30:00.000Z",
      },
      { id: "user-2", role: "user", content: "继续补充价格一致性检查" },
    ],
    "task-1",
    "running",
  );

  assert.equal(items.length, 2);
  assert.deepEqual(items[0], {
    id: "user-2",
    title: "继续补充价格一致性检查",
    subtitle: "running",
    active: true,
  });
  assert.equal(items[1].id, "user-1");
  assert.equal(items[1].title, "请分析这些 Markdown 投标文件里的异常线...");
  assert.equal(items[1].active, false);
});
