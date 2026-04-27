import assert from "node:assert/strict";
import test from "node:test";

import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildLogClipboardText,
  buildRunActivityGroups,
  calculateLogProgress,
  formatFileSize,
  formatTaskStatus,
  formatTime,
  shouldSubmitComposerKey,
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

test("buildConversationHistoryItems renders backend summaries as title-only history", () => {
  const items = buildConversationHistoryItems([
    {
      id: "task-1",
      title: "请分析这些",
      status: "complete",
      runCount: 1,
    },
    {
      id: "task-2",
      title: "继续补充",
      status: "running",
      runCount: 2,
    },
  ], "task-2");

  assert.deepEqual(items, [
    { id: "task-1", title: "请分析这些", active: false },
    { id: "task-2", title: "继续补充", active: true },
  ]);
  assert.equal("subtitle" in items[0], false);
});

test("buildConversationHistoryItems keeps history intact for an unpersisted draft", () => {
  const items = buildConversationHistoryItems([
    { id: "task-1", title: "请分析这些", status: "complete", runCount: 1 },
  ], "");

  assert.deepEqual(items, [{ id: "task-1", title: "请分析这些", active: false }]);
});

test("shouldSubmitComposerKey submits Enter but not Shift+Enter or IME Enter", () => {
  assert.equal(shouldSubmitComposerKey({ key: "Enter" }), true);
  assert.equal(shouldSubmitComposerKey({ key: "Enter", shiftKey: true }), false);
  assert.equal(shouldSubmitComposerKey({ key: "Enter", isComposing: true }), false);
  assert.equal(shouldSubmitComposerKey({ key: "Enter", nativeIsComposing: true }), false);
  assert.equal(shouldSubmitComposerKey({ key: "a" }), false);
});

test("formatTaskStatus keeps run badges localized", () => {
  assert.equal(formatTaskStatus("running"), "运行中");
  assert.equal(formatTaskStatus("complete"), "已完成");
  assert.equal(formatTaskStatus("needs_input"), "需补充");
  assert.equal(formatTaskStatus("unknown"), "历史");
});

test("buildRunActivityGroups groups logs and reports by run chronologically", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-2",
        status: "complete",
        startedAt: "2026-04-27T09:00:00.000Z",
        artifactNames: ["report.html"],
      },
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: ["report.html"],
      },
    ],
    [
      {
        id: "event-2",
        title: "第二轮",
        runId: "run-2",
        createdAt: "2026-04-27T09:01:00.000Z",
      },
      {
        id: "event-1b",
        title: "第一轮结束",
        runId: "run-1",
        createdAt: "2026-04-27T08:02:00.000Z",
      },
      {
        id: "event-1a",
        title: "第一轮开始",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:00.000Z",
      },
    ],
    [
      { id: "run-2:report.html", name: "report.html", runId: "run-2" },
      { id: "run-1:report.html", name: "report.html", runId: "run-1" },
    ],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-1", "run-2"]);
  assert.deepEqual(groups[0].logs.map((log) => log.id), ["event-1a", "event-1b"]);
  assert.equal(groups[0].reportArtifacts[0].runId, "run-1");
});

test("buildConversationStreamItems places each run activity after its transcript messages", () => {
  const groups = [
    {
      runId: "run-1",
      title: "第 1 轮",
      status: "complete" as const,
      logs: [{ id: "event-1", title: "第一轮", runId: "run-1" }],
      reportArtifacts: [],
    },
    {
      runId: "run-2",
      title: "第 2 轮",
      status: "running" as const,
      logs: [{ id: "event-2", title: "第二轮", runId: "run-2" }],
      reportArtifacts: [],
    },
  ];

  const items = buildConversationStreamItems(
    [
      { id: "m1", role: "user", content: "第一问", runId: "run-1" },
      { id: "m2", role: "assistant", content: "第一答", runId: "run-1" },
      { id: "m3", role: "user", content: "第二问", runId: "run-2" },
    ],
    groups,
  );

  assert.deepEqual(
    items.map((item) => item.id),
    ["message:m1", "message:m2", "run:run-1", "message:m3", "run:run-2"],
  );
});
