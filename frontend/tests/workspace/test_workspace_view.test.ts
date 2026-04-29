import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  formatMessagePanelTitle,
  formatReasoningPhaseLabel,
  formatRunLogStatus,
  formatTaskStatus,
  formatTime,
  getMessagePanelTone,
  isWarningChatMessage,
  partitionVisibleLogs,
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

test("buildLogClipboardText labels reasoning summaries without arbitrary payload data", () => {
  assert.equal(formatReasoningPhaseLabel("decide"), "决策");
  const text = buildLogClipboardText([
    {
      id: "reasoning-1",
      type: "reasoning_trace",
      title: "subagent-a 已记录思考摘要。",
      level: "info",
      reasoning: {
        agentId: "subagent-a",
        phase: "decide",
        summary: "纳入 2 条结构化证据。",
        confidence: "medium",
        evidenceRefs: ["quotation_similarity", "bidder-a.md"],
      },
    },
    {
      id: "reasoning-bad",
      type: "reasoning_trace",
      title: "畸形思考摘要。",
      level: "info",
    },
  ]);

  assert.equal(
    text,
    "--:--:-- 思考摘要 决策 subagent-a：纳入 2 条结构化证据。 关联：quotation_similarity、bidder-a.md\n--:--:-- 信息 畸形思考摘要。",
  );
  assert.equal(text.includes("arbitrary_secret"), false);
});

test("buildLogClipboardText includes deep agent activity and file audit summaries", () => {
  const text = buildLogClipboardText([
    {
      id: "activity-1",
      type: "deep_agent_activity",
      title: "DeepAgent activity",
      level: "info",
      createdAt: "2026-04-27T08:01:00.000Z",
      agentActivity: {
        schemaVersion: 1,
        source: "deepagents",
        activityKind: "lifecycle",
        phase: "tool_use",
        status: "started",
        title: "工具调用准备",
        summary: "本轮准备调用 list_dir 检查上传快照。",
        iterationIndex: 1,
        agentId: "main-agent",
        parentAgentId: "root",
        taskLabel: "输入分类",
        toolName: "list_dir",
        parameterSummary: "relative_path=uploads",
        resultSummary: "工具返回 3 个文件名。",
        subgraphPath: ["agent", "file-record-agent"],
        relatedEventId: "audit-1",
        truncated: false,
      },
    },
    {
      id: "audit-1",
      type: "file_tool_audit",
      title: "已记录文件工具访问审计。",
      level: "info",
      createdAt: "2026-04-27T08:02:00.000Z",
      fileAudit: {
        toolName: "read_file",
        operation: "read",
        status: "success",
        virtualPath: "uploads/source.md",
        source: "upload_snapshot",
        bytes: 241,
        sha256: "abc123",
      },
    },
  ]);

  assert.match(text, /执行进展 工具调用 已开始：工具调用准备 本轮准备调用 list_dir 检查上传快照。/);
  assert.match(text, /轮次：1/);
  assert.match(text, /代理：main-agent/);
  assert.match(text, /父代理：root/);
  assert.match(text, /任务：输入分类/);
  assert.match(text, /工具：list_dir/);
  assert.match(text, /参数：relative_path=uploads/);
  assert.match(text, /结果：工具返回 3 个文件名。/);
  assert.match(text, /路径：agent \/ file-record-agent/);
  assert.match(text, /关联：audit-1/);
  assert.match(text, /文件审计 读文件 成功：uploads\/source\.md/);
  assert.match(text, /工具：read_file/);
  assert.match(text, /来源：upload_snapshot/);
  assert.match(text, /字节：241/);
  assert.match(text, /SHA256：abc123/);
});

test("buildLogClipboardText includes bounded search tool parameters and results", () => {
  const text = buildLogClipboardText([
    {
      id: "search-call",
      type: "search_tool_call",
      title: "已调用联网搜索工具。",
      level: "info",
      createdAt: "2026-04-29T01:00:00.000Z",
      searchTrace: {
        kind: "tool_call",
        toolName: "tavily_search",
        parameterSummary: "query=上海天气; max_results=5; use_uploads=false",
        sources: [],
      },
    },
    {
      id: "search-result",
      type: "search_tool_result",
      title: "联网搜索工具已返回安全摘要。",
      level: "info",
      createdAt: "2026-04-29T01:00:01.000Z",
      searchTrace: {
        kind: "tool_result",
        toolName: "tavily_search",
        resultSummary: "结果数量：1",
        sourceCount: 1,
        sources: [{ title: "上海天气", url: "https://weather.example/shanghai" }],
      },
    },
  ]);

  assert.match(text, /搜索日志 工具调用：已调用联网搜索工具。/);
  assert.match(text, /工具：tavily_search/);
  assert.match(text, /参数：query=上海天气; max_results=5; use_uploads=false/);
  assert.match(text, /搜索日志 工具结果：联网搜索工具已返回安全摘要。/);
  assert.match(text, /结果：结果数量：1/);
  assert.match(text, /来源：上海天气/);
});

test("buildLogClipboardText includes safe orchestration profile labels", () => {
  const text = buildLogClipboardText([
    {
      id: "orchestration-1",
      type: "orchestration_decision",
      title: "已记录本轮编排策略。",
      level: "info",
      orchestration: {
        schemaVersion: 1,
        strategy: "multi_agent",
        reasonCode: "multi_document_bid_comparison",
        chosenProfileId: "bid_multi_agent",
        chosenProfileLabel: "招投标多 Agent 分析",
        plannedSubagents: ["document-classification-agent", "report-writing-agent"],
        messageClass: "bid_analysis",
        route: "deep_agent",
        bidderCount: 3,
        decisionSummary: "选择多 Agent Profile。",
      },
    },
  ]);

  assert.match(text, /编排策略 multi_agent：已记录本轮编排策略。/);
  assert.match(text, /Profile：招投标多 Agent 分析/);
  assert.match(text, /ID：bid_multi_agent/);
  assert.match(text, /子 Agent：document-classification-agent、report-writing-agent/);
  assert.match(text, /选择多 Agent Profile。/);
});

test("buildLogClipboardText ignores arbitrary malformed payload fields", () => {
  const text = buildLogClipboardText([
    {
      id: "activity-bad",
      type: "deep_agent_activity",
      title: "畸形活动。",
      level: "info",
      payload: {
        arbitrary_secret: "SHOULD_NOT_COPY",
        raw_provider_chunk: "SHOULD_NOT_COPY",
      },
    } as never,
  ]);

  assert.equal(text, "--:--:-- 信息 畸形活动。");
  assert.equal(text.includes("SHOULD_NOT_COPY"), false);
  assert.equal(text.includes("raw_provider_chunk"), false);
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

test("workspace CSS aligns composer panel with the assistant message card column", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.equal(cssSource.includes("--conversation-width: 940px;"), true);
  assert.equal(cssSource.includes("--message-marker-space: 42px;"), true);
  assert.match(
    cssSource,
    /\.conversationStream\s*\{[\s\S]*?width: min\(var\(--conversation-width\), calc\(100% - 64px\)\);/,
  );
  assert.match(
    cssSource,
    /\.composerShell\s*\{[\s\S]*?width: min\(var\(--conversation-width\), calc\(100% - 64px\)\);/,
  );
  assert.match(cssSource, /\.composerPanel\s*\{[\s\S]*?margin-left: var\(--message-marker-space\);/);
  assert.match(cssSource, /\.isEmpty \.composerPanel\s*\{[\s\S]*?margin-left: 0;/);
});

test("workspace CSS uses the reference robot sender avatar treatment", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.match(
    cssSource,
    /\.agentMarker\s*\{[\s\S]*?width: 32px;[\s\S]*?height: 32px;[\s\S]*?border-radius: var\(--radius-xs\);[\s\S]*?background: #dbeafe;[\s\S]*?color: #2563eb;/,
  );
  assert.match(
    cssSource,
    /\.robotAvatarIcon\s*\{[\s\S]*?width: 20px;[\s\S]*?height: 20px;/,
  );
  assert.match(cssSource, /\.messageBotIcon\s*\{[\s\S]*?color: #2563eb;/);
});

test("formatTaskStatus keeps run badges localized", () => {
  assert.equal(formatTaskStatus("running"), "运行中");
  assert.equal(formatTaskStatus("complete"), "已完成");
  assert.equal(formatTaskStatus("needs_input"), "需补充");
  assert.equal(formatTaskStatus("unknown"), "历史");
});

test("buildRunActivityGroups groups logs and artifacts by run chronologically", () => {
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
  assert.equal(groups[0].artifacts[0].runId, "run-1");
});

test("buildRunActivityGroups keeps reasoning traces chronologically with operation logs", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "operation-2",
        title: "工具完成",
        runId: "run-1",
        createdAt: "2026-04-27T08:03:00.000Z",
      },
      {
        id: "reasoning-1",
        type: "reasoning_trace",
        title: "思考",
        runId: "run-1",
        createdAt: "2026-04-27T08:02:00.000Z",
        reasoning: {
          agentId: "subagent-a",
          phase: "observe",
          summary: "发现证据。",
          evidenceRefs: [],
        },
      },
      {
        id: "operation-1",
        title: "工具开始",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:00.000Z",
      },
    ],
    [],
  );

  assert.deepEqual(groups[0].logs.map((log) => log.id), [
    "operation-1",
    "reasoning-1",
    "operation-2",
  ]);
});

test("partitionVisibleLogs collapses excess info reasoning but preserves warnings", () => {
  const logs = [
    {
      id: "reasoning-1",
      title: "r1",
      reasoning: { agentId: "a", phase: "plan" as const, summary: "1", evidenceRefs: [] },
    },
    {
      id: "operation-1",
      title: "operation",
    },
    {
      id: "reasoning-2",
      title: "r2",
      reasoning: { agentId: "a", phase: "observe" as const, summary: "2", evidenceRefs: [] },
    },
    {
      id: "reasoning-3",
      title: "r3",
      reasoning: { agentId: "a", phase: "decide" as const, summary: "3", evidenceRefs: [] },
    },
    {
      id: "reasoning-4",
      title: "r4",
      reasoning: { agentId: "a", phase: "final_summary" as const, summary: "4", evidenceRefs: [] },
    },
    {
      id: "reasoning-warning",
      title: "rw",
      level: "warning" as const,
      reasoning: { agentId: "a", phase: "risk" as const, summary: "warn", evidenceRefs: [] },
    },
  ];

  const collapsed = partitionVisibleLogs(logs);
  const expanded = partitionVisibleLogs(logs, { expanded: true });

  assert.deepEqual(collapsed.visibleLogs.map((log) => log.id), [
    "reasoning-1",
    "operation-1",
    "reasoning-2",
    "reasoning-3",
    "reasoning-warning",
  ]);
  assert.equal(collapsed.hiddenReasoningCount, 1);
  assert.deepEqual(expanded.visibleLogs.map((log) => log.id), logs.map((log) => log.id));
  assert.equal(expanded.hiddenReasoningCount, 0);
});

test("buildRunActivityGroups suppresses setup-only orphan history after runs exist", () => {
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
        id: "created-1",
        type: "task_created",
        title: "任务目录已创建。",
        createdAt: "2026-04-27T07:58:00.000Z",
      },
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

test("buildRunActivityGroups keeps search runs clear of stale upload fixture logs", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-search",
        status: "complete",
        startedAt: "2026-04-29T01:00:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "upload-old",
        type: "file_uploaded",
        title: "已上传 stale.json",
        createdAt: "2026-04-29T00:59:00.000Z",
      },
      {
        id: "search-call",
        type: "search_tool_call",
        title: "搜索工具调用",
        runId: "run-search",
        createdAt: "2026-04-29T01:01:00.000Z",
      },
      {
        id: "weather-result",
        type: "search_tool_result",
        title: "天气结果摘要",
        runId: "run-search",
        createdAt: "2026-04-29T01:02:00.000Z",
      },
    ],
    [],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-search"]);
  assert.deepEqual(groups[0].logs.map((log) => log.id), ["search-call", "weather-result"]);
  assert.equal(JSON.stringify(groups).includes("stale.json"), false);
});

test("buildRunActivityGroups keeps unmatched warnings while suppressing setup fallback logs", () => {
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
        id: "created-1",
        type: "task_created",
        title: "任务目录已创建。",
        createdAt: "2026-04-27T07:58:00.000Z",
      },
      {
        id: "upload-1",
        type: "file_uploaded",
        title: "已上传 input.json",
        createdAt: "2026-04-27T07:59:00.000Z",
      },
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
  assert.deepEqual(groups.at(-1)?.logs.map((log) => log.id), ["orphan-warning"]);
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

test("buildRunActivityGroups keeps fallback non-report artifacts visible", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
    ],
    [],
    [{ id: "missing-run:final-summary.md", name: "final-summary.md", runId: "missing-run" }],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["legacy"]);
  assert.deepEqual(groups[0].artifacts.map((artifact) => artifact.name), ["final-summary.md"]);
  assert.equal(groups[0].artifacts[0].runId, "legacy");
});

test("buildRunActivityGroups dedupes unscoped artifacts by rendered run", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: ["final-summary.md", "report.html"],
      },
    ],
    [],
    [
      { id: "legacy-summary", name: "final-summary.md" },
      { id: "legacy-report", name: "report.html" },
    ],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-1"]);
  assert.deepEqual(groups[0].artifacts.map((artifact) => artifact.name), [
    "final-summary.md",
    "report.html",
  ]);
  assert.equal(groups[0].artifacts[0].runId, "run-1");
});

test("buildRunActivityGroups keeps same artifact names separate across runs", () => {
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
  assert.deepEqual(groups.map((group) => group.artifacts.length), [1, 1]);
  assert.equal(groups[0].artifacts[0].runId, "run-1");
  assert.equal(groups[1].artifacts[0].runId, "run-2");
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
  assert.equal(formatMessagePanelTitle(errorMessage), "AI 生成内容");
  assert.equal(getMessagePanelTone(warningMessage), "warning");
  assert.equal(formatMessagePanelStatus(warningMessage), "配置提醒");
  assert.equal(formatMessagePanelTitle(warningMessage), "AI 生成内容");
  assert.equal(getMessagePanelTone(systemMessage), "system");
  assert.equal(formatMessagePanelStatus(systemMessage), "系统消息");
  assert.equal(formatMessagePanelTitle(systemMessage), "系统消息");
  assert.equal(getMessagePanelTone(okMessage), "default");
  assert.equal(formatMessagePanelStatus(okMessage), "已完成");
  assert.equal(formatMessagePanelTitle(okMessage), "最终答案");
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
      artifacts: [],
    },
    {
      runId: "run-2",
      title: "第 2 轮",
      status: "running" as const,
      logs: [{ id: "event-2", title: "第二轮", runId: "run-2" }],
      artifacts: [],
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

test("buildConversationStreamItems orders user, logs, final answer, then artifacts", () => {
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
        artifacts: [
          { id: "run-1:final-summary.md", name: "final-summary.md", runId: "run-1" },
          { id: "run-1:evidence.json", name: "evidence.json", runId: "run-1" },
        ],
      },
    ],
  );

  assert.deepEqual(
    items.map((item) => item.id),
    [
      "message:m1",
      "run:run-1",
      "message:m2",
      "artifact:run-1:final-summary.md",
      "artifact:run-1:evidence.json",
    ],
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
        artifacts: [{ id: "run-1:report.html", name: "report.html", runId: "run-1" }],
      },
    ],
  );

  assert.deepEqual(
    items.map((item) => item.id),
    ["message:m1", "run:run-1", "artifact:run-1:report.html"],
  );
});
