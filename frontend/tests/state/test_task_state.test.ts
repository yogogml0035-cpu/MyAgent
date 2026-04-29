import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  backendDownMessage,
  buildArtifactRequest,
  buildMessageRequestPayload,
  deriveConversationTitle,
  formatHttpErrorMessage,
  formatNeedsInput,
  formatRequestFailure,
  isTaskActive,
  mergeExecutionLogs,
  mergeTaskState,
  normalizeTaskSummaries,
  normalizeTaskState,
  resolveApiBaseUrl,
  type TaskState,
} from "../../app/task-state";

function baseState(overrides: Partial<TaskState> = {}): TaskState {
  return {
    id: "task-1",
    status: "running",
    statusLabel: "running",
    runs: [],
    messages: [],
    logs: [],
    artifacts: [],
    uploadCount: 0,
    needsInput: null,
    ...overrides,
  };
}

test("normalizeTaskState maps unknown backend statuses to unknown instead of running", () => {
  const state = normalizeTaskState({ task_id: "task-1", status: "paused" }, "fallback");

  assert.equal(state.status, "unknown");
  assert.equal(state.statusLabel, "未知状态：paused");
  assert.equal(isTaskActive(state.status), false);
});

test("normalizeTaskState preserves interrupted as an inactive known status", () => {
  const state = normalizeTaskState({ task_id: "task-1", status: "interrupted" }, "fallback");

  assert.equal(state.status, "interrupted");
  assert.equal(state.statusLabel, "interrupted");
  assert.equal(isTaskActive(state.status), false);
});

test("mergeExecutionLogs appends only new events by id", () => {
  const existing = [
    { id: "event-a", title: "A" },
    { id: "event-b", title: "B" },
  ];
  const incoming = [
    { id: "event-b", title: "B duplicate" },
    { id: "event-c", title: "C" },
  ];

  assert.deepEqual(mergeExecutionLogs(existing, incoming).map((log) => log.id), [
    "event-a",
    "event-b",
    "event-c",
  ]);
});

test("mergeTaskState keeps existing messages when incremental payload omits them", () => {
  const existing = baseState({
    messages: [{ id: "message-a", role: "user", content: "hello" }],
    logs: [{ id: "event-a", title: "A" }],
  });
  const incoming = baseState({
    status: "complete",
    statusLabel: "complete",
    messages: [],
    logs: [{ id: "event-b", title: "B" }],
    artifacts: [{ id: "report", name: "report.html" }],
    uploadCount: 2,
  });

  const merged = mergeTaskState(existing, incoming);

  assert.deepEqual(merged.messages, existing.messages);
  assert.equal(merged.status, "complete");
  assert.equal(merged.uploadCount, 2);
  assert.deepEqual(merged.artifacts, incoming.artifacts);
  assert.deepEqual(merged.logs.map((log) => log.id), ["event-a", "event-b"]);
});

test("buildArtifactRequest carries the access token for protected artifact fetches", () => {
  const request = buildArtifactRequest(
    { id: "report", name: "report.html", url: "/api/tasks/task-1/artifacts/report.html" },
    "task-1",
    "http://localhost:8001",
    "secret-token",
  );

  assert.equal(request.url, "http://localhost:8001/api/tasks/task-1/artifacts/report.html");
  assert.deepEqual(request.headers, { "X-MyAgent-Token": "secret-token" });
});

test("buildArtifactRequest builds run-scoped artifact URLs with the access token", () => {
  const request = buildArtifactRequest(
    { id: "run-2:report.html", name: "report.html", runId: "run-2" },
    "task-1",
    "http://localhost:8001",
    "secret-token",
  );

  assert.equal(
    request.url,
    "http://localhost:8001/api/tasks/task-1/runs/run-2/artifacts/report.html",
  );
  assert.deepEqual(request.headers, { "X-MyAgent-Token": "secret-token" });
});

test("buildMessageRequestPayload sends the default mode without a file-scope toggle", () => {
  assert.deepEqual(buildMessageRequestPayload("请分析这些文件", "deepseek-reasoner"), {
    content: "请分析这些文件",
    message: "请分析这些文件",
    model: "deepseek-reasoner",
    mode: "auto",
  });
});

test("buildMessageRequestPayload allows explicit mode overrides", () => {
  assert.deepEqual(
    buildMessageRequestPayload("继续分析这些文件", "deepseek-reasoner", {
      mode: "deep_agent",
    }),
    {
      content: "继续分析这些文件",
      message: "继续分析这些文件",
      model: "deepseek-reasoner",
      mode: "deep_agent",
    },
  );
});

test("first-party composer no longer renders a file-use segmented control", () => {
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf-8");

  assert.equal(pageSource.includes("scopeSegment"), false);
  assert.equal(pageSource.includes("本轮是否使用已上传文件"), false);
  assert.equal(pageSource.includes("不用文件"), false);
  assert.equal(pageSource.includes("使用文件"), false);
});

test("user message cards expose a copy action for the exact message content", () => {
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf-8");

  assert.equal(pageSource.includes('aria-label="复制用户消息"'), true);
  assert.equal(pageSource.includes("handleCopyText(message.content)"), true);
});

test("normalizeTaskState preserves user message content without display localization", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      messages: [
        {
          id: "message-1",
          role: "user",
          content: "Task completed",
        },
        {
          id: "message-2",
          role: "user",
          content: "Uploaded input.json",
        },
        {
          id: "message-3",
          role: "assistant",
          content: "Task completed",
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.messages[0].content, "Task completed");
  assert.equal(state.messages[1].content, "Uploaded input.json");
  assert.equal(state.messages[2].content, "任务已完成。");
});

test("normalizeTaskState preserves run ids on messages, logs, artifacts, and runs", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      runs: [
        {
          id: "run-1",
          status: "complete",
          message: "请分析这些文件",
          started_at: "2026-04-27T08:00:00.000Z",
          artifact_names: ["report.html"],
        },
      ],
      messages: [
        { id: "message-1", role: "assistant", content: "请分析", run_id: "run-1", level: "warning" },
      ],
      events: [
        { id: "event-1", type: "task_completed", message: "完成", run_id: "run-1", level: "success" },
      ],
      artifacts: [{ name: "report.html", type: "html", run_id: "run-1" }],
    },
    "fallback",
  );

  assert.equal(state.runs[0].id, "run-1");
  assert.equal(state.messages[0].runId, "run-1");
  assert.equal(state.messages[0].level, "warning");
  assert.equal(state.logs[0].runId, "run-1");
  assert.equal(state.logs[0].level, "success");
  assert.equal(state.logs[0].title, "完成");
  assert.equal(state.artifacts[0].runId, "run-1");
});

test("normalizeTaskState preserves valid reasoning trace metadata", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "reasoning-1",
          type: "reasoning_trace",
          message: "subagent-a 已记录思考摘要。",
          run_id: "run-1",
          payload: {
            agent_id: "subagent-a",
            phase: "observe",
            summary: "发现 2 条结构化证据。",
            confidence: "medium",
            evidence_refs: ["quotation_similarity", "bidder-a.md", { unsafe: true }],
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].reasoning, {
    agentId: "subagent-a",
    phase: "observe",
    summary: "发现 2 条结构化证据。",
    confidence: "medium",
    evidenceRefs: ["quotation_similarity", "bidder-a.md"],
  });
});

test("normalizeTaskState preserves valid deep agent activity metadata", () => {
  const longTitle = "T".repeat(130);
  const longSummary = "S".repeat(1010);
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "activity-1",
          type: "deep_agent_activity",
          message: "DeepAgent activity",
          run_id: "run-1",
          payload: {
            schema_version: 1,
            source: "deepagents",
            source_event_id: "dg_evt_123",
            activity_kind: "lifecycle",
            phase: "tool_use",
            status: "started",
            title: longTitle,
            summary: longSummary,
            tool_name: "list_dir",
            parameter_summary: "relative_path=uploads",
            result_summary: "工具返回 3 个文件名。",
            subgraph_path: ["agent", "file-record-agent", { unsafe: true }],
            related_event_id: "file-tool-audit-event-id",
            truncated: true,
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].agentActivity?.schemaVersion, 1);
  assert.equal(state.logs[0].agentActivity?.source, "deepagents");
  assert.equal(state.logs[0].agentActivity?.activityKind, "lifecycle");
  assert.equal(state.logs[0].agentActivity?.phase, "tool_use");
  assert.equal(state.logs[0].agentActivity?.status, "started");
  assert.equal(state.logs[0].agentActivity?.toolName, "list_dir");
  assert.equal(state.logs[0].agentActivity?.parameterSummary, "relative_path=uploads");
  assert.equal(state.logs[0].agentActivity?.resultSummary, "工具返回 3 个文件名。");
  assert.deepEqual(state.logs[0].agentActivity?.subgraphPath, ["agent", "file-record-agent"]);
  assert.equal(state.logs[0].agentActivity?.relatedEventId, "file-tool-audit-event-id");
  assert.equal(state.logs[0].agentActivity?.truncated, true);
  assert.equal(state.logs[0].agentActivity?.title.length, 120);
  assert.equal(state.logs[0].agentActivity?.summary.length, 1000);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState rejects malformed deep agent activity payloads", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "activity-invalid-status",
          type: "deep_agent_activity",
          message: "畸形活动。",
          payload: {
            schema_version: 1,
            source: "deepagents",
            activity_kind: "lifecycle",
            phase: "tool_use",
            status: "raw_provider_chunk",
            title: "不能进入活动字段。",
            summary: "不能进入活动字段。",
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
        {
          id: "activity-missing-summary",
          type: "deep_agent_activity",
          message: "缺少摘要。",
          payload: {
            schema_version: 1,
            source: "deepagents",
            activity_kind: "progress",
            phase: "planning",
            status: "running",
            title: "缺少摘要。",
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].agentActivity, undefined);
  assert.equal(state.logs[1].agentActivity, undefined);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState preserves safe file tool audit metadata only", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "audit-1",
          type: "file_tool_audit",
          message: "已记录文件工具访问审计。",
          payload: {
            tool_name: "read_file",
            op: "read",
            status: "success",
            virtual_path: "uploads/source.md",
            resolved_workspace_path: "/private/raw/path/source.md",
            source: "upload_snapshot",
            bytes: 241,
            sha256: "abc123",
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].fileAudit, {
    toolName: "read_file",
    operation: "read",
    status: "success",
    virtualPath: "uploads/source.md",
    source: "upload_snapshot",
    bytes: 241,
    sha256: "abc123",
    reason: undefined,
    promotedArtifactId: undefined,
    partial: undefined,
  });
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
  assert.equal(JSON.stringify(state.logs).includes("/private/raw/path/source.md"), false);
});

test("normalizeTaskState falls back for malformed reasoning trace payloads", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "reasoning-invalid-phase",
          type: "reasoning_trace",
          message: "畸形思考摘要。",
          payload: {
            agent_id: "subagent-a",
            phase: "raw_thought",
            summary: "不能进入 reasoning 字段。",
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
        {
          id: "reasoning-missing-summary",
          type: "reasoning_trace",
          message: "缺少摘要。",
          payload: {
            agent_id: "subagent-a",
            phase: "plan",
            arbitrary_secret: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].reasoning, undefined);
  assert.equal(state.logs[1].reasoning, undefined);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState localizes fixed legacy event messages without changing machine fields", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        { id: "event-1", type: "plan_created", message: "Execution plan generated" },
        { id: "event-2", type: "file_uploaded", message: "Uploaded input.json" },
      ],
      artifacts: [{}],
    },
    "fallback",
  );

  assert.equal(state.logs[0].type, "plan_created");
  assert.equal(state.logs[0].title, "已生成执行计划。");
  assert.equal(state.logs[1].type, "file_uploaded");
  assert.equal(state.logs[1].title, "已上传 input.json");
  assert.equal(state.artifacts[0].name, "产物 1");
});

test("formatNeedsInput localizes fixed payload keys and fallback messages", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "needs_input",
      needs_input: {
        message: "Additional input is required.",
        required_file_type: "markdown_or_json",
      },
    },
    "fallback",
  );

  assert.equal(state.needsInput?.required_file_type, "markdown_or_json");
  assert.equal(
    formatNeedsInput(state.needsInput ?? {}),
    "需要补充输入。 所需文件类型：Markdown 或 JSON 文件",
  );
});

test("normalizeTaskSummaries reads backend history titles without subtitles", () => {
  const summaries = normalizeTaskSummaries([
    {
      task_id: "task-2",
      title: "请分析这些",
      status: "complete",
      run_count: 2,
      updated_at: "2026-04-27T09:00:00.000Z",
    },
  ]);

  assert.deepEqual(summaries, [
    {
      id: "task-2",
      title: "请分析这些",
      status: "complete",
      model: undefined,
      createdAt: undefined,
      updatedAt: "2026-04-27T09:00:00.000Z",
      runCount: 2,
      lastMessageAt: undefined,
    },
  ]);
});

test("deriveConversationTitle uses the first five visible characters", () => {
  assert.equal(deriveConversationTitle("请分析这些 Markdown 文件"), "请分析这些");
  assert.equal(deriveConversationTitle("Analyze these files"), "Analy");
  assert.equal(deriveConversationTitle("  多行\n空白\t会压缩  "), "多行 空白");
});

test("request error formatting distinguishes backend-down from auth detail", () => {
  assert.equal(
    formatRequestFailure(new TypeError("Failed to fetch"), "http://localhost:8001"),
    backendDownMessage("http://localhost:8001"),
  );
  assert.equal(
    formatHttpErrorMessage(401, "Unauthorized", '{"detail":"Invalid or missing access token"}'),
    "访问令牌无效或缺失。",
  );
  assert.equal(
    formatHttpErrorMessage(
      422,
      "Unprocessable Entity",
      '{"detail":[{"msg":"String should have at most 8000 characters"}]}',
    ),
    "请求参数校验失败，请检查输入内容。",
  );
});

test("resolveApiBaseUrl preserves explicit backend URLs without trailing slashes", () => {
  assert.equal(
    resolveApiBaseUrl("http://192.0.2.10:8001/"),
    "http://192.0.2.10:8001",
  );
});

test("resolveApiBaseUrl derives the backend URL from the current page host", () => {
  assert.equal(
    resolveApiBaseUrl("auto", { protocol: "http:", hostname: "localhost" }),
    "http://localhost:8001",
  );
  assert.equal(
    resolveApiBaseUrl(undefined, { protocol: "http:", hostname: "192.0.2.10" }),
    "http://192.0.2.10:8001",
  );
});
