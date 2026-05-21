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
  isModelRunnable,
  isTaskActive,
  mergeExecutionLogs,
  mergeTaskState,
  normalizeModelOption,
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

test("buildArtifactRequest accepts backend run-scoped artifact URLs on the API origin", () => {
  const request = buildArtifactRequest(
    {
      id: "run-2:report.html",
      name: "report.html",
      runId: "run-2",
      url: "/api/tasks/task-1/runs/run-2/artifacts/report.html",
    },
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

test("buildArtifactRequest rejects external artifact URLs before sending tokens", () => {
  assert.throws(
    () =>
      buildArtifactRequest(
        {
          id: "run-2:report.html",
          name: "report.html",
          runId: "run-2",
          url: "https://evil.example/api/tasks/task-1/runs/run-2/artifacts/report.html",
        },
        "task-1",
        "http://localhost:8001",
        "secret-token",
      ),
    /产物 URL 不受信任/,
  );
});

test("buildArtifactRequest rejects same-origin URLs outside current task artifact routes", () => {
  const badArtifacts = [
    {
      id: "wrong-task",
      name: "report.html",
      runId: "run-2",
      url: "/api/tasks/task-2/runs/run-2/artifacts/report.html",
    },
    {
      id: "wrong-route",
      name: "report.html",
      runId: "run-2",
      url: "/api/tasks/task-1/files/report.html",
    },
    {
      id: "query",
      name: "report.html",
      runId: "run-2",
      url: "/api/tasks/task-1/runs/run-2/artifacts/report.html?next=https://evil.example",
    },
    {
      id: "wrong-name",
      name: "report.html",
      runId: "run-2",
      url: "/api/tasks/task-1/runs/run-2/artifacts/other.html",
    },
  ];

  for (const artifact of badArtifacts) {
    assert.throws(
      () => buildArtifactRequest(artifact, "task-1", "http://localhost:8001", "secret-token"),
      /产物 URL 不受信任/,
    );
  }
});

test("buildMessageRequestPayload sends the default mode without a file-scope toggle", () => {
  assert.deepEqual(buildMessageRequestPayload("请分析这些文件", "deepseek-v4-flash"), {
    content: "请分析这些文件",
    message: "请分析这些文件",
    model: "deepseek-v4-flash",
    mode: "auto",
  });
});

test("buildMessageRequestPayload allows explicit mode overrides", () => {
  assert.deepEqual(
    buildMessageRequestPayload("继续分析这些文件", "deepseek-v4-flash", {
      mode: "analysis",
    }),
    {
      content: "继续分析这些文件",
      message: "继续分析这些文件",
      model: "deepseek-v4-flash",
      mode: "analysis",
    },
  );
});

test("buildMessageRequestPayload includes selected skills without changing message fields", () => {
  assert.deepEqual(
    buildMessageRequestPayload("hello", "deepseek-v4-flash", {
      skills: ["web-research", " ", "code-review"],
    }),
    {
      content: "hello",
      message: "hello",
      model: "deepseek-v4-flash",
      mode: "auto",
      skills: ["web-research", "code-review"],
    },
  );
});

test("normalizeModelOption preserves backend availability metadata", () => {
  assert.deepEqual(
    normalizeModelOption({
      id: "deepseek-v4-flash",
      label: "DeepSeek V4 Flash",
      available: false,
    }),
    {
      id: "deepseek-v4-flash",
      label: "DeepSeek V4 Flash",
      available: false,
    },
  );
});

test("isModelRunnable blocks only explicitly unavailable backend models", () => {
  assert.equal(
    isModelRunnable({
      id: "deepseek-v4-flash-thinking",
      label: "DeepSeek V4 Flash Thinking",
      available: false,
    }),
    false,
  );
  assert.equal(isModelRunnable({ id: "deepseek-v4-flash", label: "DeepSeek" }), true);
  assert.equal(isModelRunnable(null), true);
});

test("first-party composer no longer renders a file-use segmented control", () => {
  const composerSource = readFileSync(
    new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
    "utf-8",
  );

  assert.equal(composerSource.includes("scopeSegment"), false);
  assert.equal(composerSource.includes("本轮是否使用已上传文件"), false);
  assert.equal(composerSource.includes("不用文件"), false);
  assert.equal(composerSource.includes("使用文件"), false);
});

test("user message cards expose a copy action for the exact message content", () => {
  const conversationSource = readFileSync(
    new URL("../../components/chat/TaskConversation.tsx", import.meta.url),
    "utf-8",
  );
  const userTimeIndex = conversationSource.indexOf('className="userMessageTime"');
  const userCopyIndex = conversationSource.indexOf("className={userCopyButtonClassName}");

  assert.equal(conversationSource.includes("复制用户消息"), true);
  assert.equal(conversationSource.includes("onCopyText(message.content, undefined"), true);
  assert.equal(conversationSource.includes("onCopyText(formatTime"), false);
  assert.equal(conversationSource.includes("已复制用户消息"), true);
  assert.equal(conversationSource.includes("copyButton-copied"), true);
  assert.equal(userTimeIndex >= 0, true);
  assert.equal(userCopyIndex >= 0, true);
  assert.equal(userTimeIndex < userCopyIndex, true);
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
          content: "  Task completed\n原样复制  ",
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

  assert.equal(state.messages[0].content, "  Task completed\n原样复制  ");
  assert.equal(state.messages[1].content, "Uploaded input.json");
  assert.equal(state.messages[2].content, "任务已完成。");
});

test("normalizeTaskState preserves event seq and thinking stream diagnostics", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "running",
      events: [
        {
          id: "think-1",
          seq: 42,
          type: "assistant_thinking_delta",
          message: "先判断是否需要工具。",
          payload: {
            schema_version: 1,
            stream_index: 7,
            content: "先判断是否需要工具。",
            is_subgraph: false,
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0]?.seq, 42);
  assert.equal(state.logs[0]?.thinkingStream?.streamIndex, 7);
  assert.equal(state.logs[0]?.thinkingStream?.content, "先判断是否需要工具。");
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

test("normalizeTaskState preserves safe assistant answer stream events", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "running",
      events: [
        {
          id: "stream-1",
          type: "assistant_answer_delta",
          message: "AI 回复生成中。",
          run_id: "run-1",
          payload: {
            schema_version: 1,
            stream_index: 2,
            content: "第一段\n第二段",
          },
        },
        {
          id: "stream-bad",
          type: "assistant_answer_delta",
          message: "AI 回复生成中。",
          run_id: "run-1",
          payload: {
            schema_version: 2,
            content: "不应显示",
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].answerStream, {
    schemaVersion: 1,
    streamIndex: 2,
    content: "第一段\n第二段",
    isSubgraph: false,
  });
  assert.equal(state.logs[1].answerStream, undefined);
});

test("normalizeTaskState preserves safe assistant thinking stream events", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "running",
      events: [
        {
          id: "think-1",
          type: "assistant_thinking_delta",
          message: "AI 思考中。",
          run_id: "run-1",
          payload: {
            schema_version: 1,
            stream_index: 3,
            content: "先判断是否需要联网。",
            is_subgraph: false,
            live: {
              schema_version: 1,
              kind: "think",
              stage: "thinking",
              display_text: "AI正在思考...",
              parameter_items: [],
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].thinkingStream, {
    schemaVersion: 1,
    streamIndex: 3,
    content: "先判断是否需要联网。",
    isSubgraph: false,
  });
  assert.equal(state.logs[0].live?.kind, "think");
});

test("normalizeTaskState keeps full thinking stream content for diagnostics", () => {
  const longReasoning = `思考开始：${"A".repeat(8205)}::TAIL`;
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "running",
      events: [
        {
          id: "think-long",
          type: "assistant_thinking_delta",
          message: "AI 思考中。",
          run_id: "run-1",
          payload: {
            schema_version: 1,
            stream_index: 4,
            content: longReasoning,
            live: {
              schema_version: 1,
              kind: "think",
              stage: "thinking",
              display_text: "AI正在思考...",
              diagnostic_label: "model.reasoning_content",
              parameter_items: [],
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0]?.thinkingStream?.content, longReasoning);
  assert.equal(
    (state.logs[0]?.rawRecord?.payload as { content?: string } | undefined)?.content,
    longReasoning,
  );
  assert.equal(JSON.stringify(state.logs).includes("rawRecord"), false);
});

test("normalizeTaskState preserves terminal task-run reasoning summaries", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "reasoning-terminal",
          type: "reasoning_trace",
          message: "task-run 已记录思考摘要。",
          run_id: "run-1",
          payload: {
            agent_id: "task-run",
            phase: "risk",
            summary: "轻量搜索已结束但存在限制：模型合成=未使用，安全来源数 0。",
            confidence: "medium",
            evidence_refs: ["missing_tavily_key"],
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].reasoning, {
    agentId: "task-run",
    phase: "risk",
    summary: "轻量搜索已结束但存在限制：模型合成=未使用，安全来源数 0。",
    confidence: "medium",
    evidenceRefs: ["missing_tavily_key"],
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
            iteration_index: 2,
            agent_id: "main-agent",
            parent_agent_id: "root",
            task_label: "投标文件对比",
            tool_name: "list_dir",
            parameter_summary: "relative_path=uploads",
            result_summary: "工具返回 3 个文件名。",
            subgraph_path: ["agent", "file-record-agent", { unsafe: true }],
            related_event_id: "file-tool-audit-event-id",
            truncated: true,
            arbitrary_secret: "SHOULD_NOT_RENDER",
            raw_provider_chunk: "SHOULD_NOT_RENDER",
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
  assert.equal(state.logs[0].agentActivity?.iterationIndex, 2);
  assert.equal(state.logs[0].agentActivity?.agentId, "main-agent");
  assert.equal(state.logs[0].agentActivity?.parentAgentId, "root");
  assert.equal(state.logs[0].agentActivity?.taskLabel, "投标文件对比");
  assert.equal(state.logs[0].agentActivity?.toolName, "list_dir");
  assert.equal(state.logs[0].agentActivity?.parameterSummary, "relative_path=uploads");
  assert.equal(state.logs[0].agentActivity?.resultSummary, "工具返回 3 个文件名。");
  assert.deepEqual(state.logs[0].agentActivity?.subgraphPath, ["agent", "file-record-agent"]);
  assert.equal(state.logs[0].agentActivity?.relatedEventId, "file-tool-audit-event-id");
  assert.equal(state.logs[0].agentActivity?.truncated, true);
  assert.equal(state.logs[0].agentActivity?.title.length, 120);
  assert.equal(state.logs[0].agentActivity?.summary.length, 1000);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
  assert.equal(JSON.stringify(state.logs).includes("raw_provider_chunk"), false);
});

test("normalizeTaskState bounds optional deep agent activity fields and ignores unknown fields", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "activity-1",
          type: "deep_agent_activity",
          message: "DeepAgent activity",
          payload: {
            schema_version: 1,
            source: "deepagents",
            activity_kind: "progress",
            phase: "planning",
            status: "running",
            title: "规划任务",
            summary: "准备分析输入。",
            iteration_index: 10000,
            agent_id: "a".repeat(140),
            parent_agent_id: "root",
            task_label: "t".repeat(180),
            unknown_optional: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].agentActivity?.iterationIndex, undefined);
  assert.equal(state.logs[0].agentActivity?.agentId?.length, 120);
  assert.equal(state.logs[0].agentActivity?.parentAgentId, "root");
  assert.equal(state.logs[0].agentActivity?.taskLabel?.length, 160);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
  assert.equal(JSON.stringify(state.logs).includes("unknown_optional"), false);
});

test("normalizeTaskState preserves bounded live metadata for user-facing logs", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "search-call",
          type: "search_tool_call",
          message: "已调用联网搜索工具。",
          payload: {
            live: {
              schema_version: 1,
              kind: "tool_call",
              stage: "using_tool",
              agent_name: "internet_agent",
              tool_name: "tavily_search",
              tool_call_id: "call-1",
              parameter_items: [
                { key: "query", value: "上海天气", secret: "SHOULD_NOT_RENDER" },
                { key: "max_results", value: 5 },
                { key: "use_uploads", value: false },
              ],
              raw_tool_result: "SHOULD_NOT_RENDER",
            },
          },
        },
        {
          id: "search-result",
          type: "search_tool_result",
          message: "联网搜索工具已返回安全摘要。",
          payload: {
            live: {
              schema_version: 1,
              kind: "tool_result",
              stage: "completed",
              agent_name: "internet_agent",
              tool_name: "tavily_search",
              tool_call_id: "call-1",
              result_status: "success",
              result_count: 5,
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.deepEqual(state.logs[0].live, {
    schemaVersion: 1,
    kind: "tool_call",
    stage: "using_tool",
    agentName: "internet_agent",
    toolName: "tavily_search",
    toolLabel: undefined,
    toolCallId: "call-1",
    displayText: undefined,
    diagnosticLabel: undefined,
    parameterItems: [
      { key: "query", value: "上海天气", truncated: undefined },
      { key: "max_results", value: 5, truncated: undefined },
      { key: "use_uploads", value: false, truncated: undefined },
    ],
    resultStatus: undefined,
    resultCount: undefined,
  });
  assert.equal(state.logs[1].live?.kind, "tool_result");
  assert.equal(state.logs[1].live?.resultStatus, "success");
  assert.equal(state.logs[1].live?.resultCount, 5);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState preserves terminal live metadata for task and answer completion", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "completed",
          type: "task_completed",
          message: "任务已完成。",
          payload: {
            previous_status: "running",
            live: {
              schema_version: 1,
              kind: "status",
              stage: "completed",
              display_text: "任务已完成",
              diagnostic_label: "runner.terminal",
              parameter_items: [{ key: "previous_status", value: "running" }],
            },
          },
        },
        {
          id: "final",
          type: "final_answer",
          message: "Final answer generated",
          payload: {
            content: "最终回答",
            live: {
              schema_version: 1,
              kind: "answer_status",
              stage: "completed",
              display_text: "回答已完成",
              diagnostic_label: "runner.final_answer",
              parameter_items: [],
              result_status: "success",
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].live?.kind, "status");
  assert.equal(state.logs[0].live?.stage, "completed");
  assert.equal(state.logs[0].live?.displayText, "任务已完成");
  assert.equal(state.logs[0].live?.parameterItems[0]?.value, "running");
  assert.equal(state.logs[1].live?.kind, "answer_status");
  assert.equal(state.logs[1].live?.stage, "completed");
  assert.equal(state.logs[1].live?.displayText, "回答已完成");
  assert.equal(state.logs[1].live?.resultStatus, "success");
});

test("normalizeTaskState preserves raw records for diagnostics without enumerating them", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "status-1",
          type: "status_update",
          message: "State update: model",
          payload: {
            node: "model",
            raw_provider_chunk: "RAW_DEBUG_VALUE",
            live: {
              schema_version: 1,
              kind: "status",
              stage: "thinking",
              display_text: "AI正在思考...",
              diagnostic_label: "model",
              parameter_items: [],
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].rawRecord?.message, "State update: model");
  assert.equal(
    (state.logs[0].rawRecord?.payload as { raw_provider_chunk?: string } | undefined)
      ?.raw_provider_chunk,
    "RAW_DEBUG_VALUE",
  );
  assert.equal(JSON.stringify(state.logs).includes("RAW_DEBUG_VALUE"), false);
});

test("normalizeTaskState preserves context and memory recall logs", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "running",
      events: [
        {
          id: "context-1",
          type: "context_loaded",
          message: "已载入会话上下文。",
          payload: {
            schema_version: 1,
            summary_present: true,
            recent_message_count: 2,
            cached_tool_result_count: 1,
            summary_preview: "用户之前问过上海天气。",
            cached_tool_previews: ["tavily_search: 上海天气"],
            raw_context: "SHOULD_NOT_RENDER",
            live: {
              schema_version: 1,
              kind: "status",
              stage: "organizing_state",
              display_text: "已载入会话上下文",
              diagnostic_label: "conversation_context",
              parameter_items: [{ key: "最近消息", value: 2 }],
            },
          },
        },
        {
          id: "memory-1",
          type: "memory_recalled",
          message: "已载入长期记忆。",
          payload: {
            schema_version: 1,
            user_id: "local-user",
            memory_count: 1,
            memory_previews: ["preference: 用户喜欢先确认边界"],
            live: {
              schema_version: 1,
              kind: "status",
              stage: "organizing_state",
              display_text: "已载入长期记忆",
              diagnostic_label: "long_term_memory",
              parameter_items: [{ key: "记忆数", value: 1 }],
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].memoryContext?.kind, "conversation");
  assert.equal(state.logs[0].memoryContext?.summaryPreview, "用户之前问过上海天气。");
  assert.equal(state.logs[0].memoryContext?.recentMessageCount, 2);
  assert.equal(state.logs[1].memoryContext?.kind, "long_term");
  assert.equal(state.logs[1].memoryContext?.memoryPreviews[0], "preference: 用户喜欢先确认边界");
  assert.equal(state.logs[1].live?.displayText, "已载入长期记忆");
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState ignores malformed live metadata", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "bad-live",
          type: "search_tool_call",
          message: "已调用联网搜索工具。",
          payload: {
            live: {
              schema_version: 1,
              kind: "raw_chain_of_thought",
              parameter_items: [{ key: "query", value: { unsafe: true } }],
              raw_reasoning: "SHOULD_NOT_RENDER",
            },
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].live, undefined);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState preserves bounded search trace metadata and ignores raw fields", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "search-call",
          type: "search_tool_call",
          message: "已调用联网搜索工具。",
          payload: {
            tool_name: "tavily_search",
            parameter_summary: {
              query: "上海今天的天气怎么样？",
              max_results: 5,
              use_uploads: false,
              raw_prompt: "SHOULD_NOT_RENDER",
            },
          },
        },
        {
          id: "search-result",
          type: "search_tool_result",
          message: "联网搜索工具已返回安全摘要。",
          payload: {
            tool_name: "tavily_search",
            result_count: 1,
            sources: [
              {
                title: "上海天气",
                url: "https://weather.example/shanghai",
                snippet: "多云，午后小雨。",
                raw_content: "SHOULD_NOT_RENDER",
              },
            ],
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].searchTrace?.kind, "tool_call");
  assert.equal(state.logs[0].searchTrace?.toolName, "tavily_search");
  assert.equal(
    state.logs[0].searchTrace?.parameterSummary,
    "query=上海今天的天气怎么样？; max_results=5; use_uploads=false",
  );
  assert.equal(state.logs[1].searchTrace?.kind, "tool_result");
  assert.equal(state.logs[1].searchTrace?.resultSummary, "结果数量：1");
  assert.equal(state.logs[1].searchTrace?.sources[0]?.title, "上海天气");
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
  assert.equal(JSON.stringify(state.logs).includes("raw_content"), false);
  assert.equal(JSON.stringify(state.logs).includes("raw_prompt"), false);
});

test("normalizeTaskState preserves bounded orchestration profile metadata", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "orchestration-1",
          type: "orchestration_decision",
          message: "已记录本轮编排策略。",
          payload: {
            schema_version: 1,
            strategy: "multi_agent",
            reason_code: "multi_document_bid_comparison",
            chosen_profile_id: "bid_multi_agent",
            chosen_profile_label: "招投标多 Agent 分析",
            planned_subagents: [
              "document-classification-agent",
              "report-writing-agent",
              { unsafe: true },
            ],
            message_class: "bid_analysis",
            route: "deep_agent",
            bidder_count: 3,
            decision_summary: "选择多 Agent Profile。",
            raw_prompt: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].orchestration?.strategy, "multi_agent");
  assert.equal(state.logs[0].orchestration?.chosenProfileId, "bid_multi_agent");
  assert.equal(state.logs[0].orchestration?.chosenProfileLabel, "招投标多 Agent 分析");
  assert.deepEqual(state.logs[0].orchestration?.plannedSubagents, [
    "document-classification-agent",
    "report-writing-agent",
  ]);
  assert.equal(state.logs[0].orchestration?.bidderCount, 3);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
  assert.equal(JSON.stringify(state.logs).includes("raw_prompt"), false);
});

test("normalizeTaskState rejects malformed orchestration metadata", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "orchestration-bad",
          type: "orchestration_decision",
          message: "畸形编排策略。",
          payload: {
            schema_version: 1,
            strategy: "dynamic_agent",
            chosen_profile_id: "SHOULD_NOT_RENDER",
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].orchestration, undefined);
  assert.equal(JSON.stringify(state.logs).includes("SHOULD_NOT_RENDER"), false);
});

test("normalizeTaskState ignores non-integer orchestration bidder counts", () => {
  const state = normalizeTaskState(
    {
      task_id: "task-1",
      status: "complete",
      events: [
        {
          id: "orchestration-float-bidder-count",
          type: "orchestration_decision",
          message: "已记录本轮编排策略。",
          payload: {
            schema_version: 1,
            strategy: "multi_agent",
            planned_subagents: [],
            bidder_count: 3.5,
          },
        },
      ],
    },
    "fallback",
  );

  assert.equal(state.logs[0].orchestration?.bidderCount, undefined);
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
          detail: "安全标题详情。",
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
  assert.equal(state.logs[0].title, "畸形活动。");
  assert.equal(state.logs[0].detail, "安全标题详情。");
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
    "需要补充输入。 所需文件类型：Markdown、JSON、TXT、DOCX、XLSX 或 XLSM 文件",
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

test("deriveConversationTitle uses the first ten visible characters", () => {
  assert.equal(deriveConversationTitle("请分析这些 Markdown 文件"), "请分析这些 Mark");
  assert.equal(deriveConversationTitle("Analyze these files"), "Analyze th");
  assert.equal(deriveConversationTitle("  多行\n空白\t会压缩  "), "多行 空白 会压缩");
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
