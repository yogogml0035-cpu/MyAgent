import assert from "node:assert/strict";
import test from "node:test";

import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildLogClipboardText,
  buildRunActivityGroups,
  buildStateNoticeMessages,
  buildWorkspaceNoticeMessages,
  calculateLogProgress,
  formatFileSize,
  formatLogLevelLabel,
  formatMessagePanelStatus,
  formatRunLogStatus,
  formatTaskStatus,
  formatTime,
  getMessagePanelTone,
  isWarningChatMessage,
  shouldSubmitComposerKey,
} from "../../app/workspace-view";

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
    "--:--:-- 信息 准备编排副本 开始 (0/5)",
  );
});

test("formatLogLevelLabel keeps stored level values display-localized", () => {
  assert.equal(formatLogLevelLabel("info"), "信息");
  assert.equal(formatLogLevelLabel("success"), "成功");
  assert.equal(formatLogLevelLabel("warning"), "警告");
  assert.equal(formatLogLevelLabel("error"), "错误");
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

test("buildStateNoticeMessages renders state notices as assistant messages", () => {
  assert.deepEqual(buildStateNoticeMessages(" 后端连接失败 ", " 需要补充字段 "), [
    {
      id: "state:backend-error",
      role: "assistant",
      content: "后端连接失败",
      level: "error",
    },
    {
      id: "state:needs-input",
      role: "assistant",
      content: "需要补充字段",
      level: "warning",
    },
  ]);
  assert.deepEqual(buildStateNoticeMessages("", "   "), []);
});

test("buildWorkspaceNoticeMessages renders local UI notices as robot messages", () => {
  assert.deepEqual(buildWorkspaceNoticeMessages("  打开报告失败  "), [
    {
      id: "state:workspace-notice",
      role: "assistant",
      content: "打开报告失败",
      level: "error",
    },
  ]);
  assert.deepEqual(buildWorkspaceNoticeMessages("  已忽略非 Markdown/JSON 文件  ", "warning"), [
    {
      id: "state:workspace-notice",
      role: "assistant",
      content: "已忽略非 Markdown/JSON 文件",
      level: "warning",
    },
  ]);
  assert.deepEqual(buildWorkspaceNoticeMessages("   "), []);
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

test("buildRunActivityGroups suppresses upload-only orphan history after runs exist", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
      {
        id: "run-2",
        status: "complete",
        startedAt: "2026-04-27T09:00:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "upload-1",
        type: "file_uploaded",
        title: "file_uploaded",
        detail: "Uploaded input.json",
        createdAt: "2026-04-27T07:59:00.000Z",
      },
      {
        id: "event-1",
        title: "运行完成",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:00.000Z",
      },
    ],
    [],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-1"]);
  assert.deepEqual(groups[0].logs.map((log) => log.id), ["event-1"]);
});

test("buildRunActivityGroups keeps non-upload orphan logs as neutral history", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
      {
        id: "run-2",
        status: "complete",
        startedAt: "2026-04-27T09:00:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "orphan-warning",
        type: "model_warning",
        title: "模型提醒",
        level: "warning",
        createdAt: "2026-04-27T09:02:00.000Z",
      },
    ],
    [],
  );

  assert.equal(groups.at(-1)?.runId, "legacy");
  assert.equal(groups.at(-1)?.status, "unknown");
  assert.deepEqual(groups.at(-1)?.logs.map((log) => log.id), ["orphan-warning"]);
});

test("buildRunActivityGroups dedupes unscoped report artifacts by rendered run", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: ["report.html"],
      },
    ],
    [],
    [{ id: "legacy-report", name: "report.html" }],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-1"]);
  assert.equal(groups[0].reportArtifacts.length, 1);
  assert.equal(groups[0].reportArtifacts[0].runId, "run-1");
});

test("buildRunActivityGroups keeps same report names separate across runs", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: ["report.html"],
      },
      {
        id: "run-2",
        status: "complete",
        startedAt: "2026-04-27T09:00:00.000Z",
        artifactNames: ["report.html"],
      },
    ],
    [],
    [
      { id: "run-1:report.html", name: "report.html", runId: "run-1" },
      { id: "run-2:report.html", name: "report.html", runId: "run-2" },
    ],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-1", "run-2"]);
  assert.deepEqual(groups.map((group) => group.reportArtifacts.length), [1, 1]);
  assert.equal(groups[0].reportArtifacts[0].runId, "run-1");
  assert.equal(groups[1].reportArtifacts[0].runId, "run-2");
});

test("isWarningChatMessage recognizes explicit and legacy provider warnings", () => {
  assert.equal(
    isWarningChatMessage({ id: "m1", role: "assistant", content: "Check config", level: "warning" }),
    true,
  );
  assert.equal(
    isWarningChatMessage({
      id: "m2",
      role: "assistant",
      content:
        "DeepSeek is selected, but DEEPSEEK_API_KEY is not configured in the backend .env.",
    }),
    true,
  );
  assert.equal(
    isWarningChatMessage({
      id: "m2-zh",
      role: "assistant",
      content: "已选择 DeepSeek，但后端 .env 未配置 DEEPSEEK_API_KEY。",
    }),
    true,
  );
  assert.equal(isWarningChatMessage({ id: "m3", role: "assistant", content: "正常回复" }), false);
});

test("message panel helpers map assistant notices to TenderWord-like card states", () => {
  const errorMessage = { id: "m1", role: "assistant" as const, content: "失败", level: "error" as const };
  const warningMessage = { id: "m2", role: "assistant" as const, content: "提醒", level: "warning" as const };
  const systemMessage = { id: "m3", role: "system" as const, content: "系统" };
  const okMessage = { id: "m4", role: "assistant" as const, content: "完成" };

  assert.equal(getMessagePanelTone(errorMessage), "error");
  assert.equal(formatMessagePanelStatus(errorMessage), "生成失败");
  assert.equal(getMessagePanelTone(warningMessage), "warning");
  assert.equal(formatMessagePanelStatus(warningMessage), "配置提醒");
  assert.equal(getMessagePanelTone(systemMessage), "system");
  assert.equal(formatMessagePanelStatus(systemMessage), "系统消息");
  assert.equal(getMessagePanelTone(okMessage), "default");
  assert.equal(formatMessagePanelStatus(okMessage), "已完成");
});

test("formatRunLogStatus uses log-card labels for terminal states", () => {
  assert.equal(formatRunLogStatus("running"), "日志收集中...");
  assert.equal(formatRunLogStatus("complete"), "日志完成");
  assert.equal(formatRunLogStatus("failed"), "日志结束（失败）");
  assert.equal(formatRunLogStatus("interrupted"), "日志结束（已中断）");
});

test("buildConversationStreamItems places run activity before the assistant reply", () => {
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
    ["message:m1", "run:run-1", "message:m2", "message:m3", "run:run-2"],
  );
});

test("buildConversationStreamItems places artifact cards after assistant replies", () => {
  const items = buildConversationStreamItems(
    [
      { id: "m1", role: "user", content: "分析", runId: "run-1" },
      { id: "m2", role: "assistant", content: "完成", runId: "run-1" },
    ],
    [
      {
        runId: "run-1",
        title: "第 1 轮",
        status: "complete" as const,
        logs: [{ id: "event-1", title: "完成", runId: "run-1" }],
        reportArtifacts: [{ id: "run-1:report.html", name: "report.html", runId: "run-1" }],
      },
    ],
  );

  assert.deepEqual(
    items.map((item) => item.id),
    ["message:m1", "run:run-1", "message:m2", "artifact:run-1:report.html"],
  );
});

test("buildConversationStreamItems keeps artifact cards after run logs without assistant reply", () => {
  const items = buildConversationStreamItems(
    [{ id: "m1", role: "user", content: "分析", runId: "run-1" }],
    [
      {
        runId: "run-1",
        title: "第 1 轮",
        status: "running" as const,
        logs: [{ id: "event-1", title: "写入报告", runId: "run-1" }],
        reportArtifacts: [{ id: "run-1:report.html", name: "report.html", runId: "run-1" }],
      },
    ],
  );

  assert.deepEqual(
    items.map((item) => item.id),
    ["message:m1", "run:run-1", "artifact:run-1:report.html"],
  );
});
