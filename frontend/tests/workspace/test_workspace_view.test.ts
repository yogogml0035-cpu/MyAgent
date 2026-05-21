import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildLiveLogItems,
  buildLogClipboardText,
  buildRunDiagnosticsJson,
  buildRunActivityGroups,
  buildStateNoticeMessages,
  buildWorkspaceNoticeMessages,
  calculateLogProgress,
  formatAgentActivityPhase,
  formatFileSize,
  formatLogLevelLabel,
  formatLiveLogItemTime,
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

test("buildLogClipboardText copies raw JSONL diagnostics", () => {
  assert.equal(buildLogClipboardText([]), "暂无日志");
  const text = buildLogClipboardText([
    {
      id: "log-1",
      title: "准备编排副本",
      detail: "开始 (0/5)",
      level: "info",
      rawRecord: {
        id: "log-1",
        type: "status_update",
        message: "State update: model",
        payload: { node: "model" },
      },
    },
  ]);

  assert.deepEqual(JSON.parse(text), {
    id: "log-1",
    type: "status_update",
    message: "State update: model",
    detail: "开始 (0/5)",
    level: "info",
    payload: { node: "model" },
  });
});

test("buildLogClipboardText backfills current run id into copied JSONL diagnostics", () => {
  const text = buildLogClipboardText([
    {
      id: "event-1",
      type: "status_update",
      title: "状态已更新",
      runId: "run-current",
      createdAt: "2026-04-27T08:01:00.000Z",
      rawRecord: {
        id: "event-1",
        type: "status_update",
        message: "State update: model",
      },
    },
  ]);

  assert.deepEqual(JSON.parse(text), {
    id: "event-1",
    type: "status_update",
    message: "State update: model",
    created_at: "2026-04-27T08:01:00.000Z",
    run_id: "run-current",
    payload: {},
  });
});

test("buildLogClipboardText falls back to structured JSONL when raw records are absent", () => {
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

  const lines = text.split("\n").map((line) => JSON.parse(line));
  assert.equal(lines.length, 2);
  assert.equal(lines[0].type, "reasoning_trace");
  assert.equal(lines[0].payload.reasoning.summary, "纳入 2 条结构化证据。");
});

test("buildLogClipboardText preserves raw event JSONL instead of projected summaries", () => {
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
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        agentName: "main_agent",
        toolName: "list_dir",
        toolCallId: "call-1",
        parameterItems: [{ key: "relative_path", value: "uploads" }],
      },
      rawRecord: {
        id: "activity-1",
        type: "tool_call",
        message: "Calling tool: list_dir",
        payload: { name: "list_dir", args: { relative_path: "uploads" } },
      },
    },
    {
      id: "audit-1",
      type: "deep_agent_activity",
      title: "DeepAgent activity",
      level: "info",
      createdAt: "2026-04-27T08:02:00.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        agentName: "main_agent",
        toolName: "list_dir",
        toolCallId: "call-1",
        parameterItems: [],
        resultStatus: "success",
        resultCount: 3,
      },
      rawRecord: {
        id: "audit-1",
        type: "tool_result",
        message: "Tool result (list_dir): success",
        payload: { name: "list_dir", content: "3 files" },
      },
    },
  ]);

  const lines = text.split("\n").map((line) => JSON.parse(line));
  assert.equal(lines[0].message, "Calling tool: list_dir");
  assert.equal(lines[1].message, "Tool result (list_dir): success");
  assert.equal(text.includes("main_agent 调用"), false);
});

test("buildLogClipboardText copies one raw JSON object per log line", () => {
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
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        agentName: "search_agent",
        toolName: "tavily_search",
        toolCallId: "search_tool_1",
        parameterItems: [
          { key: "query", value: "上海天气" },
          { key: "max_results", value: 5 },
        ],
      },
      rawRecord: {
        id: "search-call",
        type: "tool_call",
        message: "Calling tool: tavily_search",
        payload: { name: "tavily_search", args: { query: "上海天气", max_results: 5 } },
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
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        agentName: "search_agent",
        toolName: "tavily_search",
        toolCallId: "search_tool_1",
        parameterItems: [],
        resultStatus: "success",
        resultCount: 1,
      },
      rawRecord: {
        id: "search-result",
        type: "tool_result",
        message: "Tool result (tavily_search): success",
        payload: { name: "tavily_search", status: "success" },
      },
    },
  ]);

  const lines = text.split("\n").map((line) => JSON.parse(line));
  assert.equal(lines.length, 2);
  assert.equal(lines[0].payload.name, "tavily_search");
  assert.equal(lines[0].payload.args.query, "上海天气");
  assert.equal(lines[1].payload.status, "success");
});

test("buildLiveLogItems pairs tool events and keeps one active status row", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "call",
        title: "call",
        live: {
          schemaVersion: 1,
          kind: "tool_call",
          stage: "using_tool",
          agentName: "internet_agent",
          toolName: "tavily_search",
          toolCallId: "tool-1",
          parameterItems: [{ key: "query", value: "上海天气" }],
        },
      },
      {
        id: "answer-start",
        title: "正在生成回答。",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "generating_answer",
          agentName: "internet_agent",
          parameterItems: [],
        },
      },
      {
        id: "result",
        title: "result",
        live: {
          schemaVersion: 1,
          kind: "tool_result",
          stage: "completed",
          agentName: "internet_agent",
          toolName: "tavily_search",
          toolCallId: "tool-1",
          parameterItems: [],
          resultStatus: "empty",
          resultCount: 0,
        },
      },
    ],
    "running",
  );

  assert.equal(items.length, 4);
  assert.equal(items[0]?.kind, "tool");
  assert.equal(items[0]?.kind === "tool" ? items[0].title : "", "调用联网搜索");
  assert.equal(items[0]?.kind === "tool" ? items[0].toolName : "", "tavily_search");
  assert.equal(items[0]?.kind === "tool" ? items[0].parameterText : "", "query=上海天气");
  assert.equal(items[1]?.kind, "status");
  assert.equal(items[1]?.kind === "status" ? items[1].text : "", "AI正在生成结果");
  assert.equal(items[2]?.kind, "tool");
  assert.equal(items[2]?.kind === "tool" ? items[2].title : "", "联网搜索暂无可用结果");
  assert.equal(items[2]?.kind === "tool" ? items[2].resultText : "", "未找到可用结果，正在尝试其他方式");
  assert.equal(items[2]?.kind === "tool" ? items[2].resultStatus : "", "empty");
  assert.equal(items[3]?.kind, "status");
  assert.equal(items[3]?.kind === "status" ? items[3].text : "", "AI正在生成结果");
  assert.equal(items[3]?.kind === "status" ? items[3].active : false, true);
});

test("buildLiveLogItems keeps event seq order and merges tool call argument deltas", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "result",
        seq: 4,
        type: "tool_result",
        title: "result",
        createdAt: "2026-04-27T08:01:00.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_result",
          stage: "completed",
          toolName: "tavily_search",
          toolCallId: "tool-1",
          parameterItems: [],
          resultStatus: "success",
          resultCount: 2,
        },
      },
      {
        id: "think",
        seq: 1,
        type: "assistant_thinking_delta",
        title: "先判断是否需要联网。",
        createdAt: "2026-04-27T08:01:00.000Z",
        thinkingStream: {
          schemaVersion: 1,
          streamIndex: 1,
          content: "先判断是否需要联网。",
        },
      },
      {
        id: "call-partial",
        seq: 2,
        type: "tool_call",
        title: "partial",
        createdAt: "2026-04-27T08:01:00.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_call",
          stage: "selecting_tool",
          toolName: "tavily_search",
          toolCallId: "tool-1",
          parameterItems: [{ key: "args", value: "{\"query\"", truncated: false }],
        },
      },
      {
        id: "call-full",
        seq: 3,
        type: "tool_call",
        title: "full",
        createdAt: "2026-04-27T08:01:00.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_call",
          stage: "using_tool",
          toolName: "tavily_search",
          toolCallId: "tool-1",
          parameterItems: [{ key: "query", value: "progress log" }],
        },
      },
    ],
    "complete",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["AI正在思考", "准备调用联网搜索", "调用联网搜索", "联网搜索已返回结果"],
  );
  const selectingItem = items[1];
  const usingItem = items[2];
  const resultItem = items[3];
  assert.equal(selectingItem?.kind, "tool");
  assert.equal(usingItem?.kind, "tool");
  assert.equal(resultItem?.kind, "tool");
  if (selectingItem?.kind !== "tool" || usingItem?.kind !== "tool" || resultItem?.kind !== "tool") {
    throw new Error("expected staged tool items");
  }
  assert.equal(selectingItem.toolName, "tavily_search");
  assert.equal(selectingItem.parameterText, "args={\"query\"");
  assert.equal(usingItem.parameterText, "query=progress log");
  assert.equal(resultItem.resultText, "返回了 2 条结果");
  assert.deepEqual(
    JSON.parse(selectingItem.details.rawJson).type,
    "tool_call",
  );
  const usingDisplay = JSON.parse(usingItem.details.displayJson);
  assert.equal(usingDisplay.type, "tool_call");
  assert.equal(usingDisplay.tool_name, "tavily_search");
  assert.equal(usingDisplay.tool_call_id, "tool-1");
  assert.deepEqual(usingDisplay.args, { query: "progress log" });
  assert.equal(JSON.stringify(usingDisplay).includes("call-partial"), false);
  assert.equal(resultItem.completedAt, undefined);
});

test("buildLiveLogItems projects staged tool rows into per-event display JSON", () => {
  const logs: Parameters<typeof buildLiveLogItems>[0] = [
    {
      id: "call-partial",
      type: "tool_call",
      title: "partial",
      createdAt: "2026-05-14T08:00:00.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "selecting_tool",
        toolName: "tavily_search",
        toolLabel: "联网搜索",
        toolCallId: "tool-json",
        parameterItems: [{ key: "args", value: "{\"query\"" }],
      },
      rawRecord: {
        type: "tool_call",
        created_at: "2026-05-14T08:00:00.000Z",
        payload: {
          id: "tool-json",
          name: "tavily_search",
          args: "{\"query\"",
          partial: true,
          live: {
            kind: "tool_call",
            tool_name: "tavily_search",
            tool_label: "联网搜索",
            tool_call_id: "tool-json",
          },
        },
      },
    },
    {
      id: "call-final",
      type: "tool_call",
      title: "final",
      createdAt: "2026-05-14T08:00:01.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        toolName: "tavily_search",
        toolLabel: "联网搜索",
        toolCallId: "tool-json",
        parameterItems: [
          { key: "query", value: "progress log" },
          { key: "max_results", value: 2 },
        ],
      },
      rawRecord: {
        type: "tool_call",
        created_at: "2026-05-14T08:00:01.000Z",
        payload: {
          id: "tool-json",
          name: "tavily_search",
          args: "{\"query\":\"progress log\",\"max_results\":2}",
          partial: false,
          live: {
            kind: "tool_call",
            tool_name: "tavily_search",
            tool_label: "联网搜索",
            tool_call_id: "tool-json",
          },
        },
      },
    },
    {
      id: "result",
      type: "tool_result",
      title: "result",
      createdAt: "2026-05-14T08:00:02.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        toolName: "tavily_search",
        toolLabel: "联网搜索",
        toolCallId: "tool-json",
        resultStatus: "success",
        parameterItems: [],
      },
      rawRecord: {
        type: "tool_result",
        created_at: "2026-05-14T08:00:02.000Z",
        payload: {
          id: "tool-json",
          name: "tavily_search",
          status: "success",
          content: "{\"ok\":true,\"items\":[{\"title\":\"A\"}]}",
          live: {
            kind: "tool_result",
            tool_name: "tavily_search",
            tool_label: "联网搜索",
            tool_call_id: "tool-json",
            result_status: "success",
          },
        },
      },
    },
  ];

  const items = buildLiveLogItems(logs, "complete");
  assert.equal(items.length, 3);
  assert.equal(items[0]?.kind, "tool");
  assert.equal(items[1]?.kind, "tool");
  assert.equal(items[2]?.kind, "tool");
  if (items[0]?.kind !== "tool" || items[1]?.kind !== "tool" || items[2]?.kind !== "tool") {
    throw new Error("expected staged tool rows");
  }

  const selectingDisplay = JSON.parse(items[0].details.displayJson);
  assert.equal(selectingDisplay.type, "tool_call");
  assert.equal(selectingDisplay.tool_name, "tavily_search");
  assert.equal(selectingDisplay.tool_label, "联网搜索");
  assert.equal(selectingDisplay.tool_call_id, "tool-json");
  assert.equal(selectingDisplay.stage, "selecting_tool");
  assert.equal(selectingDisplay.args, "{\"query\"");

  const usingDisplay = JSON.parse(items[1].details.displayJson);
  assert.equal(usingDisplay.type, "tool_call");
  assert.equal(usingDisplay.tool_name, "tavily_search");
  assert.equal(usingDisplay.tool_label, "联网搜索");
  assert.equal(usingDisplay.tool_call_id, "tool-json");
  assert.equal(usingDisplay.stage, "using_tool");
  assert.deepEqual(usingDisplay.args, { query: "progress log", max_results: 2 });

  const resultDisplay = JSON.parse(items[2].details.displayJson);
  assert.equal(resultDisplay.type, "tool_result");
  assert.equal(resultDisplay.tool_name, "tavily_search");
  assert.equal(resultDisplay.tool_label, "联网搜索");
  assert.equal(resultDisplay.tool_call_id, "tool-json");
  assert.equal(resultDisplay.status, "success");
  assert.deepEqual(resultDisplay.content, { ok: true, items: [{ title: "A" }] });
  assert.equal("records" in resultDisplay, false);
  assert.equal(items[1].details.displayJson.includes("call-partial"), false);
  assert.equal(JSON.parse(items[0].details.rawJson).type, "tool_call");
  assert.equal(JSON.parse(items[1].details.rawJson).type, "tool_call");
  assert.equal(JSON.parse(items[2].details.rawJson).type, "tool_result");

  const rawLines = buildLogClipboardText(logs).split("\n").map((line) => JSON.parse(line));
  assert.equal(rawLines.length, 3);
  assert.equal(rawLines[0].payload.partial, true);
  assert.equal(rawLines[2].payload.content, "{\"ok\":true,\"items\":[{\"title\":\"A\"}]}");
});

test("buildLiveLogItems truncates oversized tool result display JSON only", () => {
  const oversizedContent = `${"x".repeat(105 * 1024)}TAIL_MARKER`;
  const items = buildLiveLogItems([
    {
      id: "call",
      type: "tool_call",
      title: "call",
      createdAt: "2026-05-14T08:01:00.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        toolName: "read_file",
        toolCallId: "tool-large",
        parameterItems: [{ key: "relative_path", value: "uploads/large.json" }],
      },
      rawRecord: {
        type: "tool_call",
        payload: {
          id: "tool-large",
          name: "read_file",
          args: { relative_path: "uploads/large.json" },
          partial: false,
        },
      },
    },
    {
      id: "result",
      type: "tool_result",
      title: "result",
      createdAt: "2026-05-14T08:01:01.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        toolName: "read_file",
        toolCallId: "tool-large",
        resultStatus: "success",
        parameterItems: [],
      },
      rawRecord: {
        type: "tool_result",
        payload: {
          id: "tool-large",
          name: "read_file",
          status: "success",
          content: oversizedContent,
        },
      },
    },
  ], "complete");

  const toolItem = items[1];
  assert.equal(items.length, 2);
  assert.equal(toolItem?.kind, "tool");
  if (toolItem?.kind !== "tool") {
    throw new Error("expected a tool result row");
  }
  const display = JSON.parse(toolItem.details.displayJson);
  assert.equal(display.type, "tool_result");
  assert.equal(display.content_truncated, true);
  assert.equal(display.content.truncated, true);
  assert.equal(display.content.preview.length, 4096);
  assert.equal(display.content_truncation.max_serialized_size_bytes, 100 * 1024);
  assert.equal(toolItem.details.rawJson.includes("TAIL_MARKER"), true);
  assert.equal(toolItem.details.displayJson.includes("TAIL_MARKER"), false);
});

test("buildLiveLogItems renders DeepAgents stream order with segmented thinking and terminal rows", () => {
  const logs: Parameters<typeof buildLiveLogItems>[0] = [
    {
      id: "snapshot-before",
      seq: 0,
      type: "values_snapshot",
      title: "State snapshot",
      createdAt: "2026-05-14T05:15:23.000Z",
      rawRecord: { id: "snapshot-before", type: "values_snapshot" },
    },
    {
      id: "think-1",
      seq: 1,
      type: "assistant_thinking_delta",
      title: "Need search.",
      createdAt: "2026-05-14T05:15:25.000Z",
      thinkingStream: {
        schemaVersion: 1,
        streamIndex: 1,
        content: "Need search.",
      },
      rawRecord: { id: "think-1", type: "assistant_thinking_delta" },
    },
    {
      id: "call-1-partial",
      seq: 2,
      type: "tool_call",
      title: "Calling tool: tavily_search",
      createdAt: "2026-05-14T05:15:25.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "selecting_tool",
        toolName: "tavily_search",
        toolCallId: "call-1",
        parameterItems: [{ key: "args", value: "{\"query\"" }],
      },
      rawRecord: { id: "call-1-partial", type: "tool_call" },
    },
    {
      id: "call-1-full",
      seq: 3,
      type: "tool_call",
      title: "Calling tool: tavily_search",
      createdAt: "2026-05-14T05:15:25.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        toolName: "tavily_search",
        toolCallId: "call-1",
        parameterItems: [{ key: "query", value: "特朗普 访华" }],
      },
      rawRecord: { id: "call-1-full", type: "tool_call" },
    },
    {
      id: "result-1",
      seq: 4,
      type: "tool_result",
      title: "Tool result (tavily_search): success",
      createdAt: "2026-05-14T05:15:28.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        toolName: "tavily_search",
        toolCallId: "call-1",
        parameterItems: [],
        resultStatus: "success",
        resultCount: 5,
      },
      rawRecord: { id: "result-1", type: "tool_result" },
    },
    {
      id: "snapshot-after-tool",
      seq: 5,
      type: "values_snapshot",
      title: "State snapshot",
      createdAt: "2026-05-14T05:15:28.000Z",
      rawRecord: { id: "snapshot-after-tool", type: "values_snapshot" },
    },
    {
      id: "tools-status",
      seq: 6,
      type: "status_update",
      title: "State update: tools",
      createdAt: "2026-05-14T05:15:28.000Z",
      live: {
        schemaVersion: 1,
        kind: "status",
        stage: "organizing_state",
        displayText: "正在整理工具结果...",
        parameterItems: [],
      },
      rawRecord: { id: "tools-status", type: "status_update" },
    },
    {
      id: "think-2",
      seq: 7,
      type: "assistant_thinking_delta",
      title: "Need verify.",
      createdAt: "2026-05-14T05:15:29.000Z",
      thinkingStream: {
        schemaVersion: 1,
        streamIndex: 7,
        content: "Need verify.",
      },
      rawRecord: { id: "think-2", type: "assistant_thinking_delta" },
    },
    {
      id: "call-2",
      seq: 8,
      type: "tool_call",
      title: "Calling tool: tavily_search",
      createdAt: "2026-05-14T05:15:30.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        toolName: "tavily_search",
        toolCallId: "call-2",
        parameterItems: [{ key: "query", value: "BBC 特朗普 访华" }],
      },
      rawRecord: { id: "call-2", type: "tool_call" },
    },
    {
      id: "result-2",
      seq: 9,
      type: "tool_result",
      title: "Tool result (tavily_search): success",
      createdAt: "2026-05-14T05:15:33.000Z",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        toolName: "tavily_search",
        toolCallId: "call-2",
        parameterItems: [],
        resultStatus: "success",
        resultCount: 3,
      },
      rawRecord: { id: "result-2", type: "tool_result" },
    },
    {
      id: "answer-1",
      seq: 10,
      type: "assistant_answer_delta",
      title: "是的",
      createdAt: "2026-05-14T05:15:38.000Z",
      answerStream: {
        schemaVersion: 1,
        streamIndex: 10,
        content: "是的",
      },
      rawRecord: { id: "answer-1", type: "assistant_answer_delta" },
    },
    {
      id: "after-model",
      seq: 11,
      type: "status_update",
      title: "State update: TodoListMiddleware.after_model",
      createdAt: "2026-05-14T05:15:39.000Z",
      live: {
        schemaVersion: 1,
        kind: "status",
        stage: "organizing_state",
        displayText: "模型输出已完成",
        diagnosticLabel: "TodoListMiddleware.after_model",
        parameterItems: [],
      },
      rawRecord: { id: "after-model", type: "status_update" },
    },
    {
      id: "completed",
      seq: 12,
      type: "task_completed",
      title: "任务已完成。",
      createdAt: "2026-05-14T05:15:39.000Z",
      live: {
        schemaVersion: 1,
        kind: "status",
        stage: "completed",
        displayText: "任务已完成",
        parameterItems: [],
      },
      rawRecord: { id: "completed", type: "task_completed" },
    },
    {
      id: "final",
      seq: 13,
      type: "final_answer",
      title: "Final answer generated",
      createdAt: "2026-05-14T05:15:39.000Z",
      live: {
        schemaVersion: 1,
        kind: "answer_status",
        stage: "completed",
        displayText: "回答已完成",
        parameterItems: [],
      },
      rawRecord: { id: "final", type: "final_answer" },
    },
  ];

  const items = buildLiveLogItems([...logs].reverse(), "complete");
  const labels = items.map((item) => (item.kind === "status" ? item.text : item.title));

  assert.deepEqual(labels, [
    "AI正在思考",
    "准备调用联网搜索",
    "调用联网搜索",
    "联网搜索已返回结果",
    "状态已更新",
    "AI正在思考",
    "调用联网搜索",
    "联网搜索已返回结果",
    "AI正在生成结果",
    "状态已更新",
    "任务已完成",
  ]);
  assert.equal(labels.includes("正在准备任务..."), false);
  assert.equal(labels.includes("正在整理工具结果..."), false);
  assert.equal(labels.includes("模型输出已完成"), false);
  assert.equal(labels.includes("状态已更新"), true);
  assert.equal(labels.includes("State snapshot"), false);
  assert.equal(labels.includes("回答已完成"), false);

  const firstTool = items[1];
  assert.equal(firstTool?.kind, "tool");
  if (firstTool?.kind !== "tool") {
    throw new Error("expected first tool row");
  }
  assert.equal(firstTool.createdAt, "2026-05-14T05:15:25.000Z");
  assert.equal(firstTool.completedAt, undefined);
  assert.equal(formatLiveLogItemTime(firstTool), formatTime(firstTool.createdAt));
  assert.equal(JSON.parse(firstTool.details.rawJson).type, "tool_call");

  const firstThinking = items[0];
  const firstStatusUpdate = items[4];
  const secondThinking = items[5];
  assert.equal(firstThinking?.kind, "status");
  assert.equal(firstStatusUpdate?.kind, "status");
  assert.equal(secondThinking?.kind, "status");
  assert.equal(firstThinking?.details.rawJson.includes("Need verify."), false);
  assert.equal(secondThinking?.details.displayJson.includes("Need verify."), true);
  assert.equal(firstStatusUpdate?.details.rawJson.includes("values_snapshot"), true);
  assert.equal(firstStatusUpdate?.details.rawJson.includes('"type": "status_update"'), true);
  assert.equal(firstThinking?.details.displayJson.includes("values_snapshot"), false);
  assert.equal(
    JSON.parse(firstThinking?.details.displayJson ?? "{}").payload.thinking_stream.content,
    "Need search.",
  );
});

test("buildLiveLogItems shows status updates as a generic compact row while retaining diagnostics", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "prep-1",
        type: "status_update",
        title: "State update: SkillsMiddleware.before_agent",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "preparing",
          displayText: "正在准备任务...",
          diagnosticLabel: "SkillsMiddleware.before_agent",
          parameterItems: [],
        },
        rawRecord: {
          id: "prep-1",
          type: "status_update",
          message: "State update: SkillsMiddleware.before_agent",
          payload: { node: "SkillsMiddleware.before_agent" },
        },
      },
      {
        id: "prep-2",
        type: "status_update",
        title: "State update: PatchToolCallsMiddleware.before_agent",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "preparing",
          displayText: "正在准备任务...",
          diagnosticLabel: "PatchToolCallsMiddleware.before_agent",
          parameterItems: [],
        },
        rawRecord: {
          id: "prep-2",
          type: "status_update",
          message: "State update: PatchToolCallsMiddleware.before_agent",
          payload: { node: "PatchToolCallsMiddleware.before_agent" },
        },
      },
      {
        id: "model",
        type: "status_update",
        title: "State update: model",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "thinking",
          displayText: "AI正在思考...",
          diagnosticLabel: "model",
          parameterItems: [],
        },
        rawRecord: {
          id: "model",
          type: "status_update",
          message: "State update: model",
          payload: { node: "model" },
        },
      },
    ],
    "running",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["状态已更新"],
  );
  const lastItem = items.at(-1);
  assert.equal(lastItem?.kind === "status" ? lastItem.active : false, true);
  assert.equal(
    JSON.stringify(items.map((item) => item.kind === "status" ? item.text : item.title)).includes("Middleware"),
    false,
  );
  assert.equal(
    JSON.stringify(items.map((item) => item.kind === "status" ? item.text : item.title)).includes("正在准备任务..."),
    false,
  );
  assert.equal(JSON.stringify(items).includes("PatchToolCallsMiddleware.before_agent"), true);
});

test("buildLiveLogItems does not treat model state updates as final answer generation", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "model",
        type: "status_update",
        title: "State update: model",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "thinking",
          displayText: "AI正在思考...",
          parameterItems: [],
        },
      },
    ],
    "running",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["状态已更新"],
  );
});

test("buildLiveLogItems keeps final_answer only in diagnostics instead of a visible row", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "completed",
        type: "task_completed",
        title: "任务已完成。",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "completed",
          displayText: "任务已完成",
          parameterItems: [],
        },
        rawRecord: {
          id: "completed",
          type: "task_completed",
          message: "任务已完成。",
        },
      },
      {
        id: "final",
        type: "final_answer",
        title: "Final answer generated",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "completed",
          displayText: "回答已完成",
          parameterItems: [],
        },
        rawRecord: {
          id: "final",
          type: "final_answer",
          message: "Final answer generated",
        },
      },
    ],
    "complete",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["任务已完成"],
  );
  assert.equal(items[0]?.details.displayJson.includes('"type": "task_completed"'), true);
  assert.equal(items[0]?.details.displayJson.includes('"type": "final_answer"'), true);
  assert.equal(items[0]?.details.displayJson.includes("Final answer generated"), true);
});

test("buildLiveLogItems aggregates assistant stream chunks into a generation row", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "answer-start",
        type: "answer_generation_started",
        title: "正在生成回答。",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "generating_answer",
          agentName: "search_agent",
          parameterItems: [],
        },
      },
      {
        id: "stream-1",
        type: "assistant_answer_delta",
        title: "AI 回复生成中。",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "generating_answer",
          agentName: "search_agent",
          parameterItems: [],
        },
        answerStream: {
          schemaVersion: 1,
          streamIndex: 1,
          content: "第一段",
        },
      },
      {
        id: "stream-2",
        type: "assistant_answer_delta",
        title: "AI 回复生成中。",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "generating_answer",
          agentName: "search_agent",
          parameterItems: [],
        },
        answerStream: {
          schemaVersion: 1,
          streamIndex: 2,
          content: "第一段\n第二段",
        },
      },
      {
        id: "answer-complete",
        type: "search_synthesis_completed",
        title: "已根据搜索结果生成最终回答。",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "completed",
          agentName: "search_agent",
          parameterItems: [],
          resultStatus: "success",
        },
      },
    ],
    "complete",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["AI正在生成结果", "回答已完成"],
  );
  const display = JSON.parse(items[0]?.details.displayJson ?? "{}");
  assert.equal(display.type, "assistant_answer_delta");
  assert.equal(display.payload.answer_stream.content.includes("第一段"), true);
  assert.equal(display.payload.answer_stream.content.includes("第二段"), true);
  assert.equal("chunks" in display.payload.answer_stream, false);
  assert.equal("chunk_count" in display.payload.answer_stream, false);
  assert.equal("accumulated_content" in display.payload.answer_stream, false);
});

test("buildLiveLogItems shows answer stream deltas only inside generation diagnostics", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "answer-start",
        type: "answer_generation_started",
        title: "正在生成回答。",
        createdAt: "2026-04-27T08:01:00.000Z",
        live: {
          schemaVersion: 1,
          kind: "answer_status",
          stage: "generating_answer",
          agentName: "search_agent",
          parameterItems: [],
        },
      },
      {
        id: "stream-punctuation",
        type: "assistant_answer_delta",
        title: "。",
        createdAt: "2026-04-27T08:01:01.000Z",
        answerStream: {
          schemaVersion: 1,
          streamIndex: 1,
          content: "。",
        },
      },
      {
        id: "stream-content",
        type: "assistant_answer_delta",
        title: "第一段",
        createdAt: "2026-04-27T08:01:02.000Z",
        answerStream: {
          schemaVersion: 1,
          streamIndex: 2,
          content: "第一段",
        },
      },
    ],
    "running",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["AI正在生成结果"],
  );
  assert.equal(items[0]?.kind === "status" ? items[0].text : "", "AI正在生成结果");
  assert.equal("rows" in (items[0]?.details ?? {}), false);
  assert.equal(items[0]?.details.rawJson.includes("stream-punctuation"), true);
  assert.equal(items[0]?.details.rawJson.includes("stream-content"), true);
  const display = JSON.parse(items[0]?.details.displayJson ?? "{}");
  assert.equal(display.payload.answer_stream.content, "。第一段");
  assert.equal("chunks" in display.payload.answer_stream, false);
  assert.equal("chunk_count" in display.payload.answer_stream, false);
  assert.equal("accumulated_content" in display.payload.answer_stream, false);
  assert.equal(items[0]?.details.displayJson.includes('"content_hidden": true'), false);
});

test("buildLiveLogItems shows thinking stream content inside thinking diagnostics", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "model-status",
        type: "status_update",
        title: "State update: model",
        createdAt: "2026-04-27T08:01:00.000Z",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "thinking",
          displayText: "AI正在思考...",
          diagnosticLabel: "model",
          parameterItems: [],
        },
      },
      {
        id: "think-1",
        type: "assistant_thinking_delta",
        title: "先判断是否需要联网。",
        createdAt: "2026-04-27T08:01:01.000Z",
        thinkingStream: {
          schemaVersion: 1,
          streamIndex: 1,
          content: "先判断是否需要联网。",
        },
      },
      {
        id: "think-2",
        type: "assistant_thinking_delta",
        title: "再选择搜索工具。",
        createdAt: "2026-04-27T08:01:02.000Z",
        thinkingStream: {
          schemaVersion: 1,
          streamIndex: 2,
          content: "再选择搜索工具。",
        },
      },
    ],
    "running",
  );

  assert.deepEqual(
    items.map((item) => (item.kind === "status" ? item.text : item.title)),
    ["状态已更新", "AI正在思考"],
  );
  assert.equal("rows" in (items[1]?.details ?? {}), false);
  assert.equal(items[1]?.details.rawJson.includes('"assistant_thinking_delta"'), true);
  const display = JSON.parse(items[1]?.details.displayJson ?? "{}");
  assert.equal(display.type, "assistant_thinking_delta");
  assert.equal(display.payload.thinking_stream.content, "先判断是否需要联网。再选择搜索工具。");
  assert.equal("chunks" in display.payload.thinking_stream, false);
  assert.equal("chunk_count" in display.payload.thinking_stream, false);
  assert.equal("accumulated_content" in display.payload.thinking_stream, false);
  assert.equal(items[1]?.details.displayJson.includes("再选择搜索工具"), true);
});

test("buildLiveLogItems pairs same-tool legacy results in call order", () => {
  const items = buildLiveLogItems([
    {
      id: "call-a",
      title: "call",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        agentName: "file_agent",
        toolName: "read_file",
        parameterItems: [{ key: "relative_path", value: "uploads/a.md" }],
      },
    },
    {
      id: "call-b",
      title: "call",
      live: {
        schemaVersion: 1,
        kind: "tool_call",
        stage: "using_tool",
        agentName: "file_agent",
        toolName: "read_file",
        parameterItems: [{ key: "relative_path", value: "uploads/b.md" }],
      },
    },
    {
      id: "result-a",
      title: "result",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        agentName: "file_agent",
        toolName: "read_file",
        parameterItems: [],
        resultStatus: "success",
        resultCount: 1,
      },
    },
    {
      id: "result-b",
      title: "result",
      live: {
        schemaVersion: 1,
        kind: "tool_result",
        stage: "completed",
        agentName: "file_agent",
        toolName: "read_file",
        parameterItems: [],
        resultStatus: "empty",
        resultCount: 0,
      },
    },
  ], "complete");

  assert.equal(items.length, 4);
  const firstItem = items[0];
  const secondItem = items[1];
  const thirdItem = items[2];
  const fourthItem = items[3];
  assert.equal(firstItem?.kind, "tool");
  assert.equal(secondItem?.kind, "tool");
  assert.equal(thirdItem?.kind, "tool");
  assert.equal(fourthItem?.kind, "tool");
  if (
    firstItem?.kind !== "tool" ||
    secondItem?.kind !== "tool" ||
    thirdItem?.kind !== "tool" ||
    fourthItem?.kind !== "tool"
  ) {
    throw new Error("expected four tool live items");
  }
  assert.equal(firstItem.title, "调用读取文件");
  assert.equal(firstItem.parameterText, "relative_path=uploads/a.md");
  assert.equal(secondItem.title, "调用读取文件");
  assert.equal(secondItem.parameterText, "relative_path=uploads/b.md");
  assert.equal(thirdItem.title, "读取文件已返回结果");
  assert.equal(thirdItem.resultText, "返回了 1 条结果");
  assert.equal(fourthItem.title, "读取文件暂无可用结果");
  assert.equal(fourthItem.resultText, "未找到可用结果，正在尝试其他方式");
});

test("buildLogClipboardText copies orchestration fallback as JSONL", () => {
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

  const parsed = JSON.parse(text);
  assert.equal(parsed.type, "orchestration_decision");
  assert.equal(parsed.payload.orchestration.strategy, "multi_agent");
});

test("buildLogClipboardText fallback ignores non-normalized ad-hoc fields", () => {
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

test("workspace CSS defines dedicated warm-canvas skill picker and chip styles", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.match(cssSource, /\.skillChipShelf\s*\{[\s\S]*?flex-wrap: wrap;[\s\S]*?width: 100%;/);
  assert.match(
    cssSource,
    /\.skillChip\s*\{[\s\S]*?max-width: min\(240px, 100%\);[\s\S]*?rgba\(204, 120, 92, 0\.34\);[\s\S]*?border-radius: var\(--radius-md\);[\s\S]*?line-height: 1\.2;/,
  );
  assert.match(
    cssSource,
    /\.skillChipMarker::before,\n\.skillOptionMarker::before\s*\{[\s\S]*?transform: rotate\(45deg\);/,
  );
  assert.match(
    cssSource,
    /\.skillPickerMenu\s*\{[\s\S]*?overflow: auto;[\s\S]*?overscroll-behavior: contain;[\s\S]*?background: var\(--surface\);[\s\S]*?border-radius: var\(--radius-lg\);/,
  );
  assert.match(cssSource, /\.skillOption\s*\{[\s\S]*?grid-template-columns: 24px minmax\(0, 1fr\);/);
  assert.match(
    cssSource,
    /\.skillOption small\s*\{[\s\S]*?overflow: hidden;[\s\S]*?-webkit-line-clamp: 2;/,
  );
  assert.match(
    cssSource,
    /@media \(max-width: 760px\)[\s\S]*?\.skillPickerMenu\s*\{[\s\S]*?max-height: min\(220px, 38vh\);/,
  );
  assert.match(
    cssSource,
    /@media \(max-width: 520px\)[\s\S]*?\.skillChip\s*\{[\s\S]*?max-width: 100%;[\s\S]*?\.skillOption\s*\{[\s\S]*?grid-template-columns: 22px minmax\(0, 1fr\);/,
  );
  assert.equal(/\.modelPicker[^{,]*\s+\.skill/.test(cssSource), false);
  assert.equal(/\.modelPickerMenu[^{,]*\s+\.skill/.test(cssSource), false);
});

test("workspace CSS keeps history scrollable with a fixed clear action", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.match(
    cssSource,
    /\.chatSidebar\s*\{[\s\S]*?grid-template-rows: auto minmax\(0, 1fr\);[\s\S]*?height: 100vh;/,
  );
  assert.match(
    cssSource,
    /\.historyPanel\s*\{[\s\S]*?grid-template-rows: auto minmax\(0, 1fr\) auto;[\s\S]*?min-height: 0;/,
  );
  assert.match(
    cssSource,
    /\.historyList\s*\{[\s\S]*?align-content: start;[\s\S]*?grid-auto-rows: minmax\(42px, max-content\);[\s\S]*?overflow-y: auto;[\s\S]*?overscroll-behavior: contain;[\s\S]*?scrollbar-gutter: stable;/,
  );
  assert.match(cssSource, /\.clearHistoryButton\s*\{[\s\S]*?width: 100%;[\s\S]*?min-height: 38px;/);
  assert.match(
    cssSource,
    /@media \(max-width: 760px\)[\s\S]*?\.historyList\s*\{[\s\S]*?overflow-x: auto;[\s\S]*?overflow-y: hidden;/,
  );
});

test("workspace CSS keeps every live log row expandable with a left-aligned timestamp", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");
  const conversationSource = readFileSync(
    new URL("../../components/chat/TaskConversation.tsx", import.meta.url),
    "utf-8",
  );

  assert.match(
    cssSource,
    /\.liveToolCard strong\s*\{[\s\S]*?width: 100%;[\s\S]*?justify-self: stretch;[\s\S]*?text-overflow: ellipsis;[\s\S]*?white-space: nowrap;/,
  );
  assert.match(
    cssSource,
    /\.liveStatusRow summary,\s*\n\.liveToolCard summary\s*\{[\s\S]*?grid-template-columns: 116px minmax\(0, 1fr\) auto auto 10px;/,
  );
  assert.match(
    cssSource,
    /\.liveStatusRow summary::after,\s*\n\.liveToolCard summary::after\s*\{[\s\S]*?transform: rotate\(45deg\);/,
  );
  assert.match(
    cssSource,
    /\.liveStatusRow\[open\] summary::after,\s*\n\.liveToolCard\[open\] summary::after\s*\{[\s\S]*?transform: rotate\(225deg\);/,
  );
  assert.match(
    cssSource,
    /\.liveToolCard\[open\]\s*\{[\s\S]*?border-color: rgba\(250, 249, 245, 0\.1\);/,
  );
  assert.match(
    conversationSource,
    /<time>\{formatLiveLogItemTime\(item\)\}<\/time>\s*<strong className="liveToolSummaryText" title=\{toolSummaryLine\}>\s*\{toolSummaryLine\}\s*<\/strong>/,
  );
  assert.equal(conversationSource.includes("formatToolSummaryLine"), true);
  assert.equal(conversationSource.includes('className="liveToolSummaryMeta"'), false);
  assert.equal(conversationSource.includes('className="liveToolPayload"'), false);
  assert.equal(conversationSource.includes("<article className={statusClassName}"), false);
  assert.match(conversationSource, /className=\{`\$\{statusClassName\} liveStatusRow-details`\}/);
  assert.match(conversationSource, /key=\{item\.id\}[\s\S]*?onToggle=\{syncOpenLogDetailCounts\}/);
  assert.equal(conversationSource.includes("<dl>"), false);
  assert.equal(conversationSource.includes("<dt>{row.label}</dt>"), false);
  assert.equal(conversationSource.includes("<dd>{row.value}</dd>"), false);
  assert.equal(conversationSource.includes("details.rows"), false);
  assert.equal(conversationSource.includes("<p>{item.resultText}</p>"), false);
  assert.equal(conversationSource.includes("<pre>{details.displayJson}</pre>"), true);
  assert.equal(conversationSource.includes("details.rawJson"), false);
  assert.equal(conversationSource.includes("liveLogCopyButton"), true);
  assert.equal(conversationSource.includes("buildRunDiagnosticsJson"), true);
  assert.equal(conversationSource.includes('className="runDiagnosticsPanel"'), true);
  assert.equal(conversationSource.includes("完整诊断 JSON"), true);
  assert.equal(conversationSource.includes("<pre>{runDiagnosticsText}</pre>"), true);
  assert.equal(conversationSource.includes("onToggle={syncOpenLogDetailCounts}"), true);
  assert.equal(conversationSource.includes("toggleRunLogDetails"), true);
  assert.equal(conversationSource.includes("setLogDetailsOpen(logList, open)"), true);
  assert.equal(conversationSource.includes("countOpenLogDetails([logList])"), true);
  assert.equal(conversationSource.includes("const hasOpenLogDetails = openLogDetailCount > 0;"), true);
  assert.equal(conversationSource.includes('hasOpenLogDetails ? "全部折叠" : "全部展开"'), true);
  assert.equal(conversationSource.includes("openLogDetailCount >= totalLogDetailCount"), false);
  assert.equal(conversationSource.includes('className="copyButton traceCollapseButton"'), false);
  assert.equal(conversationSource.includes("traceLogToggleButton"), true);
  assert.equal(conversationSource.includes("全部展开"), true);
  assert.equal(conversationSource.includes("全部折叠"), true);
  assert.equal(conversationSource.includes('"traceCopyButton"'), true);
  assert.equal(conversationSource.includes("event.preventDefault();"), true);
  assert.equal(conversationSource.includes("event.stopPropagation();"), true);
  assert.equal(
    conversationSource.includes("<summary>{statusSummary}</summary>"),
    true,
  );
  assert.match(
    conversationSource,
    /<strong className="liveToolSummaryText" title=\{toolSummaryLine\}>[\s\S]*?\{toolSummaryLine\}[\s\S]*?<\/strong>[\s\S]*?\{renderLiveLogCopyButton\(item\.details, copyKey\)\}/,
  );
  assert.equal(cssSource.includes(".liveLogDiagnosticRows"), false);
  assert.match(
    cssSource,
    /\.liveLogCopyButton\s*\{[\s\S]*?grid-column: 4;[\s\S]*?justify-self: end;/,
  );
  assert.match(
    cssSource,
    /\.runDiagnosticsPanel\s*\{[\s\S]*?margin: 0 14px 14px;[\s\S]*?background: rgba\(24, 23, 21, 0\.78\);/,
  );
  assert.match(
    cssSource,
    /\.runDiagnosticsPanel summary\s*\{[\s\S]*?grid-template-columns: minmax\(0, 1fr\) auto 10px;[\s\S]*?min-height: 38px;/,
  );
  assert.match(
    cssSource,
    /\.runDiagnosticsPanel\[open\] summary::after\s*\{[\s\S]*?transform: rotate\(225deg\);/,
  );
  assert.match(
    cssSource,
    /\.runDiagnosticsBody pre\s*\{[\s\S]*?max-height: 240px;/,
  );
  assert.match(
    cssSource,
    /\.traceActions\s*\{[\s\S]*?display: flex;[\s\S]*?gap: 8px;/,
  );
  assert.match(
    cssSource,
    /\.traceLogToggleButton\s*\{[\s\S]*?min-width: 82px;[\s\S]*?height: 28px;[\s\S]*?border: 1px solid rgba\(250, 249, 245, 0\.1\);[\s\S]*?background: var\(--surface-dark-soft\);/,
  );
  assert.match(
    cssSource,
    /\.traceLogToggleButton::after\s*\{[\s\S]*?m6 9 6 6 6-6[\s\S]*?center \/ 13px 13px no-repeat;/,
  );
  assert.match(cssSource, /\.traceLogToggleButton::before\s*\{[\s\S]*?display: none;/);
  assert.match(
    cssSource,
    /\.traceLogToggleButton-open::after\s*\{[\s\S]*?m18 15-6-6-6 6/,
  );
  assert.equal(cssSource.includes(".traceLogToggleButton-open {\n"), false);
  assert.equal(cssSource.includes("rgba(204, 120, 92, 0.68)"), false);
  assert.equal(cssSource.includes(".copyButton.traceCollapseButton"), false);
  assert.match(
    cssSource,
    /\.liveLogDiagnostics pre\s*\{[\s\S]*?padding: 10px;/,
  );
  assert.match(
    cssSource,
    /@media \(max-width: 760px\)[\s\S]*?\.traceHeader\s*\{[\s\S]*?align-items: flex-start;[\s\S]*?flex-wrap: wrap;/,
  );
  assert.match(
    cssSource,
    /@media \(max-width: 760px\)[\s\S]*?\.liveStatusRow summary,\s*\n  \.liveToolCard summary\s*\{[\s\S]*?grid-template-columns: 92px minmax\(0, 1fr\) auto auto 10px;/,
  );
  assert.match(
    cssSource,
    /\.copyButton-copied,\s*\n\.copyButton-copied:hover:not\(:disabled\)\s*\{[\s\S]*?border-color: rgba\(204, 120, 92, 0\.52\);[\s\S]*?color: var\(--primary-active\);/,
  );
  assert.match(
    cssSource,
    /\.copyButton::before\s*\{[\s\S]*?display: none;/,
  );
  assert.match(
    cssSource,
    /\.copyButton::after\s*\{[\s\S]*?position: absolute;[\s\S]*?left: 50%;[\s\S]*?top: 50%;[\s\S]*?width: 14px;[\s\S]*?height: 14px;[\s\S]*?background: currentColor;[\s\S]*?transform: translate\(-50%, -50%\);[\s\S]*?mask: url\("data:image\/svg\+xml,[\s\S]*?\) center \/ 14px 14px no-repeat;/,
  );
  assert.match(
    cssSource,
    /\.copyButton-copied::after\s*\{[\s\S]*?mask: url\("data:image\/svg\+xml,[\s\S]*?\) center \/ 14px 14px no-repeat;/,
  );
  assert.match(cssSource, /\.copyButton-copied::before\s*\{[\s\S]*?display: none;/);
  assert.match(cssSource, /\.copyButton-copied span\s*\{[\s\S]*?opacity: 0;[\s\S]*?transform: none;/);
  assert.match(
    cssSource,
    /\.copyButton\.userCopyButton\.copyButton-copied span\s*\{[\s\S]*?width: 14px;[\s\S]*?height: 14px;[\s\S]*?transform: none;/,
  );
  assert.match(
    cssSource,
    /\.copyButton-copied span::before,\s*\n\.copyButton-copied span::after\s*\{[\s\S]*?display: none;/,
  );
  assert.match(cssSource, /\.copyButton\.userCopyButton\.copyButton-copied span::before\s*\{[\s\S]*?display: none;/);
  assert.match(
    cssSource,
    /\.traceCard-failed,\s*\n\.traceCard-cancelled\s*\{[\s\S]*?border-color: rgba\(250, 249, 245, 0\.12\);/,
  );
  assert.match(
    cssSource,
    /\.liveStatusRow-error\s*\{[\s\S]*?border-color: rgba\(250, 249, 245, 0\.1\);/,
  );
  assert.match(
    cssSource,
    /\.liveToolCard-failed\s*\{[\s\S]*?border-color: rgba\(250, 249, 245, 0\.1\);/,
  );
  assert.doesNotMatch(cssSource, /\.liveStatusRow-error\s*\{[\s\S]*?rgba\(198, 69, 69/);
  assert.doesNotMatch(cssSource, /\.liveToolCard-failed\s*\{[\s\S]*?rgba\(198, 69, 69/);
  assert.equal(cssSource.includes("color: #8bd899;"), false);
  assert.equal(cssSource.includes("box-shadow: 3px -3px 0"), false);
  assert.equal(cssSource.includes(".liveToolIcon"), false);
});

test("workspace CSS hides user copy controls until hover or focus", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.match(
    cssSource,
    /\.copyButton\.userCopyButton\s*\{[\s\S]*?width: 0;[\s\S]*?opacity: 0;[\s\S]*?pointer-events: none;[\s\S]*?visibility: hidden;/,
  );
  assert.match(
    cssSource,
    /\.userMessageFrame:hover \.copyButton\.userCopyButton,\s*\n\.userMessageFrame:focus-within \.copyButton\.userCopyButton,\s*\n\.copyButton\.userCopyButton\.copyButton-copied\s*\{[\s\S]*?width: 24px;[\s\S]*?opacity: 1;[\s\S]*?pointer-events: auto;[\s\S]*?visibility: visible;/,
  );
});

test("workspace CSS keeps only the row-level robot sender avatar", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");
  const conversationSource = readFileSync(
    new URL("../../components/chat/TaskConversation.tsx", import.meta.url),
    "utf-8",
  );

  assert.match(
    cssSource,
    /\.agentMarker\s*\{[\s\S]*?width: 32px;[\s\S]*?height: 32px;[\s\S]*?border-radius: var\(--radius-xs\);[\s\S]*?background: #dbeafe;[\s\S]*?color: #2563eb;/,
  );
  assert.match(
    cssSource,
    /\.robotAvatarIcon\s*\{[\s\S]*?width: 20px;[\s\S]*?height: 20px;/,
  );
  assert.equal(cssSource.includes(".messageBotIcon"), false);
  assert.equal(cssSource.includes(".documentIcon"), false);
  assert.equal(conversationSource.includes('variant="title"'), false);
  assert.equal(conversationSource.includes("documentIcon"), false);
  assert.equal(conversationSource.includes("liveToolIcon"), false);
});

test("assistant replies render Markdown with GFM but no raw HTML plugin", () => {
  const conversationSource = readFileSync(
    new URL("../../components/chat/TaskConversation.tsx", import.meta.url),
    "utf-8",
  );

  assert.equal(conversationSource.includes("react-markdown"), true);
  assert.equal(conversationSource.includes("remark-gfm"), true);
  assert.equal(conversationSource.includes("rehype-raw"), false);
  assert.equal(conversationSource.includes("markdownBody"), true);
  assert.equal(conversationSource.includes("messageArtifactFooter"), true);
  assert.equal(conversationSource.includes("answerStreamCursor"), true);
});

test("empty workspace hero wordmark is text-only", () => {
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.equal(cssSource.includes(".heroMark::before"), false);
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

test("buildRunActivityGroups keeps per-run diagnostics and JSONL copy isolated", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-a",
        status: "complete",
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
      {
        id: "run-b",
        status: "complete",
        startedAt: "2026-04-27T08:05:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "run-a-think",
        seq: 1,
        type: "assistant_thinking_delta",
        title: "A thinking",
        runId: "run-a",
        createdAt: "2026-04-27T08:00:01.000Z",
        thinkingStream: {
          schemaVersion: 1,
          streamIndex: 0,
          content: "RUN_A_REASONING_CANARY",
        },
        rawRecord: {
          id: "run-a-think",
          type: "assistant_thinking_delta",
          run_id: "run-a",
          payload: { thinking_stream: { content: "RUN_A_REASONING_CANARY" } },
        },
      },
      {
        id: "run-b-think",
        seq: 2,
        type: "assistant_thinking_delta",
        title: "B thinking",
        runId: "run-b",
        createdAt: "2026-04-27T08:05:01.000Z",
        thinkingStream: {
          schemaVersion: 1,
          streamIndex: 0,
          content: "RUN_B_REASONING_CANARY",
        },
        rawRecord: {
          id: "run-b-think",
          type: "assistant_thinking_delta",
          run_id: "run-b",
          payload: { thinking_stream: { content: "RUN_B_REASONING_CANARY" } },
        },
      },
      {
        id: "run-a-call",
        seq: 3,
        type: "tool_call",
        title: "run a call",
        runId: "run-a",
        createdAt: "2026-04-27T08:00:02.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_call",
          stage: "using_tool",
          toolName: "list_dir",
          toolCallId: "tool-a",
          parameterItems: [{ key: "relative_path", value: "uploads/run-a" }],
        },
        rawRecord: {
          id: "run-a-call",
          type: "tool_call",
          run_id: "run-a",
          payload: { name: "list_dir", args: { relative_path: "uploads/run-a" } },
        },
      },
      {
        id: "run-b-call",
        seq: 4,
        type: "tool_call",
        title: "run b call",
        runId: "run-b",
        createdAt: "2026-04-27T08:05:02.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_call",
          stage: "using_tool",
          toolName: "read_file",
          toolCallId: "tool-b",
          parameterItems: [{ key: "relative_path", value: "uploads/run-b.md" }],
        },
        rawRecord: {
          id: "run-b-call",
          type: "tool_call",
          run_id: "run-b",
          payload: { name: "read_file", args: { relative_path: "uploads/run-b.md" } },
        },
      },
      {
        id: "run-a-result",
        seq: 5,
        type: "tool_result",
        title: "run a result",
        runId: "run-a",
        createdAt: "2026-04-27T08:00:03.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_result",
          stage: "completed",
          toolName: "list_dir",
          toolCallId: "tool-a",
          parameterItems: [],
          resultStatus: "success",
          resultCount: 1,
        },
        rawRecord: {
          id: "run-a-result",
          type: "tool_result",
          run_id: "run-a",
          payload: { name: "list_dir", status: "success", content: "RUN_A_RESULT_CANARY" },
        },
      },
      {
        id: "run-b-result",
        seq: 6,
        type: "tool_result",
        title: "run b result",
        runId: "run-b",
        createdAt: "2026-04-27T08:05:03.000Z",
        live: {
          schemaVersion: 1,
          kind: "tool_result",
          stage: "completed",
          toolName: "read_file",
          toolCallId: "tool-b",
          parameterItems: [],
          resultStatus: "success",
          resultCount: 1,
        },
        rawRecord: {
          id: "run-b-result",
          type: "tool_result",
          run_id: "run-b",
          payload: { name: "read_file", status: "success", content: "RUN_B_RESULT_CANARY" },
        },
      },
      {
        id: "run-a-final",
        seq: 7,
        type: "final_answer",
        title: "run a final",
        runId: "run-a",
        createdAt: "2026-04-27T08:00:04.000Z",
        rawRecord: {
          id: "run-a-final",
          type: "final_answer",
          run_id: "run-a",
          payload: { content: "RUN_A_FINAL_CANARY" },
        },
      },
      {
        id: "run-b-final",
        seq: 8,
        type: "final_answer",
        title: "run b final",
        runId: "run-b",
        createdAt: "2026-04-27T08:05:04.000Z",
        rawRecord: {
          id: "run-b-final",
          type: "final_answer",
          run_id: "run-b",
          payload: { content: "RUN_B_FINAL_CANARY" },
        },
      },
    ],
    [],
  );

  assert.deepEqual(groups.map((group) => group.runId), ["run-a", "run-b"]);
  assert.deepEqual(groups[0].logs.map((log) => log.id), [
    "run-a-think",
    "run-a-call",
    "run-a-result",
    "run-a-final",
  ]);
  assert.deepEqual(groups[1].logs.map((log) => log.id), [
    "run-b-think",
    "run-b-call",
    "run-b-result",
    "run-b-final",
  ]);

  const runALiveItems = buildLiveLogItems(groups[0].logs, groups[0].status);
  const runAThinking = runALiveItems.find(
    (item) => item.kind === "status" && item.text === "AI正在思考",
  );
  assert.equal(runAThinking?.kind, "status");
  if (runAThinking?.kind !== "status") {
    throw new Error("expected run-a thinking diagnostics");
  }
  assert.equal(runAThinking.details.displayJson.includes("RUN_A_REASONING_CANARY"), true);
  assert.equal(runAThinking.details.displayJson.includes("RUN_B_REASONING_CANARY"), false);

  const runAClipboard = buildLogClipboardText(groups[0].logs);
  assert.equal(runAClipboard.includes("RUN_A_RESULT_CANARY"), true);
  assert.equal(runAClipboard.includes("RUN_A_FINAL_CANARY"), true);
  assert.equal(runAClipboard.includes("RUN_B_REASONING_CANARY"), false);
  assert.equal(runAClipboard.includes("RUN_B_RESULT_CANARY"), false);
  assert.equal(runAClipboard.includes("RUN_B_FINAL_CANARY"), false);
  assert.equal(runAClipboard.includes("uploads/run-a"), true);
  assert.equal(runAClipboard.includes("uploads/run-b.md"), false);

  const runADiagnostics = buildRunDiagnosticsJson(groups[0].logs);
  assert.equal(runADiagnostics.includes("RUN_A_REASONING_CANARY"), true);
  assert.equal(runADiagnostics.includes("RUN_A_RESULT_CANARY"), true);
  assert.equal(runADiagnostics.includes("RUN_A_FINAL_CANARY"), true);
  assert.equal(runADiagnostics.includes('"run_id": "run-a"'), true);
  assert.equal(runADiagnostics.includes("RUN_B_REASONING_CANARY"), false);
  assert.equal(runADiagnostics.includes("RUN_B_RESULT_CANARY"), false);
  assert.equal(runADiagnostics.includes("RUN_B_FINAL_CANARY"), false);

  const runBClipboard = buildLogClipboardText(groups[1].logs);
  assert.equal(runBClipboard.includes("RUN_B_RESULT_CANARY"), true);
  assert.equal(runBClipboard.includes("RUN_B_FINAL_CANARY"), true);
  assert.equal(runBClipboard.includes("RUN_A_REASONING_CANARY"), false);
  assert.equal(runBClipboard.includes("RUN_A_RESULT_CANARY"), false);
  assert.equal(runBClipboard.includes("RUN_A_FINAL_CANARY"), false);
  assert.equal(runBClipboard.includes("uploads/run-b.md"), true);
  assert.equal(runBClipboard.includes("uploads/run-a"), false);
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
  const streamingMessage = { id: "m5", role: "assistant" as const, content: "生成中", streaming: true };

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
  assert.equal(formatMessagePanelTitle(okMessage), "AI回复");
  assert.equal(formatMessagePanelStatus(streamingMessage), "生成中");
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

test("buildConversationStreamItems renders a streamed assistant draft while a run is active", () => {
  const groups = buildRunActivityGroups(
    [
      {
        id: "run-1",
        status: "running" as const,
        startedAt: "2026-04-27T08:00:00.000Z",
        artifactNames: [],
      },
    ],
    [
      {
        id: "event-1",
        title: "正在生成回答。",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:00.000Z",
      },
      {
        id: "stream-1",
        type: "assistant_answer_delta",
        title: "AI 回复生成中。",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:01.000Z",
        answerStream: {
          schemaVersion: 1,
          streamIndex: 1,
          content: "第一段",
        },
      },
      {
        id: "stream-2",
        type: "assistant_answer_delta",
        title: "AI 回复生成中。",
        runId: "run-1",
        createdAt: "2026-04-27T08:01:02.000Z",
        answerStream: {
          schemaVersion: 1,
          streamIndex: 2,
          content: "第一段\n第二段",
        },
      },
    ],
    [],
  );
  const items = buildConversationStreamItems(
    [{ id: "m1", role: "user", content: "写一段回复", runId: "run-1" }],
    groups,
  );

  assert.deepEqual(
    items.map((item) => item.id),
    ["message:m1", "run:run-1"],
  );
});

test("buildConversationStreamItems attaches run artifacts to the assistant reply", () => {
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
    ],
  );
  const assistantItem = items[2];
  assert.equal(assistantItem.kind, "message");
  assert.deepEqual(
    assistantItem.kind === "message"
      ? assistantItem.assistantArtifacts?.map((artifact) => artifact.name)
      : [],
    ["final-summary.md", "evidence.json"],
  );
  assert.equal(assistantItem.kind === "message" ? assistantItem.groupTitle : "", "第 1 轮");
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

test("accumulateStreamedAnswer concatenates delta chunks by streamIndex", () => {
  const groups = buildRunActivityGroups(
    [{ id: "run-1", status: "running", artifactNames: [] }],
    [
      { id: "s1", type: "assistant_answer_delta" as const, runId: "run-1", title: "", answerStream: { schemaVersion: 1, streamIndex: 2, content: " world" } },
      { id: "s2", type: "assistant_answer_delta" as const, runId: "run-1", title: "", answerStream: { schemaVersion: 1, streamIndex: 0, content: "Hello" } },
      { id: "s3", type: "assistant_answer_delta" as const, runId: "run-1", title: "", answerStream: { schemaVersion: 1, streamIndex: 1, content: "," } },
    ],
    [],
  );
  assert.equal(groups[0].streamedAnswer, "Hello, world");
});

test("hasMeaningfulContent rejects punctuation-only content", () => {
  const groups = buildRunActivityGroups(
    [{ id: "run-1", status: "running", artifactNames: [] }],
    [
      { id: "s1", type: "assistant_answer_delta" as const, runId: "run-1", title: "", answerStream: { schemaVersion: 1, streamIndex: 0, content: "。" } },
    ],
    [],
  );
  const items = buildConversationStreamItems(
    [{ id: "m1", role: "user" as const, content: "test", runId: "run-1" }],
    groups,
  );
  assert.equal(items.some(i => i.kind === "message" && "streaming" in i.message && i.message.streaming), false);
});

test("hasMeaningfulContent allows content with punctuation and meaningful text", () => {
  const groups = buildRunActivityGroups(
    [{ id: "run-1", status: "complete", artifactNames: [] }],
    [
      { id: "s1", type: "assistant_answer_delta" as const, runId: "run-1", title: "", answerStream: { schemaVersion: 1, streamIndex: 0, content: "，你好。" } },
    ],
    [],
  );
  assert.equal(groups[0].streamedAnswer, "，你好。");
  const items = buildConversationStreamItems(
    [{ id: "m1", role: "user" as const, content: "test", runId: "run-1" }],
    groups,
  );
  assert.equal(items.some(i => i.kind === "message" && "streaming" in i.message && i.message.streaming), false);
});

test("formatAgentActivityPhase maps agent activity phases to Chinese", () => {
  assert.equal(formatAgentActivityPhase("planning"), "正在规划任务...");
  assert.equal(formatAgentActivityPhase("reasoning"), "AI正在思考...");
  assert.equal(formatAgentActivityPhase("tool_use"), "正在调用工具...");
  assert.equal(formatAgentActivityPhase("file_operation"), "正在处理文件...");
  assert.equal(formatAgentActivityPhase("finalizing"), "AI正在生成结果");
});

test("formatAgentActivityPhase returns empty for unknown phase", () => {
  assert.equal(formatAgentActivityPhase(undefined), "");
});

test("buildLiveLogItems uses agentActivity phase over live stage", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "act-1",
        title: "DeepAgent activity",
        agentActivity: {
          schemaVersion: 1,
          source: "deepagents",
          activityKind: "progress",
          phase: "reasoning",
          status: "running",
          title: "思考中",
          summary: "AI正在分析。",
          subgraphPath: [],
          truncated: false,
        },
        live: {
          schemaVersion: 1,
          kind: "think",
          stage: "analyzing_intent",
          parameterItems: [],
        },
      },
    ],
    "running",
  );
  
  const activeItem = items.find(i => i.kind === "status" && i.active);
  assert.ok(activeItem, "should have an active status item");
  if (activeItem && activeItem.kind === "status") {
    assert.equal(activeItem.text, "AI正在思考...");
  }
});

test("buildLiveLogItems falls back to live stage when agentActivity absent", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "status-1",
        title: "Status",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "selecting_tool",
          parameterItems: [],
        },
      },
    ],
    "running",
  );
  
  const activeItem = items.find(i => i.kind === "status" && i.active);
  assert.ok(activeItem, "should have an active status item");
  if (activeItem && activeItem.kind === "status") {
    assert.equal(activeItem.text, "正在选择合适工具...");
  }
});

test("buildLiveLogItems default fallback is AI thinking", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "legacy-1",
        type: "unknown_type",
        title: "Something happened",
      },
    ],
    "running",
  );

  const activeItem = items.find(i => i.kind === "status" && i.active);
  assert.ok(activeItem, "should have an active status item");
  if (activeItem && activeItem.kind === "status") {
    assert.equal(activeItem.text, "AI正在思考");
  }
});

test("buildLiveLogItems shows cancelled status when cancel event present", () => {
  const items = buildLiveLogItems(
    [
      {
        id: "status-1",
        title: "Status",
        live: {
          schemaVersion: 1,
          kind: "status",
          stage: "generating_answer",
          parameterItems: [],
        },
      },
      {
        id: "cancel-1",
        type: "task_cancelled",
        title: "任务已取消",
        level: "warning",
      },
    ],
    "running",
  );

  const cancelledItem = items.find(i => i.kind === "status" && i.id === "status:cancelled");
  assert.ok(cancelledItem, "should have a cancelled status item");
  if (cancelledItem && cancelledItem.kind === "status") {
    assert.equal(cancelledItem.text, "任务已取消");
    assert.equal(cancelledItem.level, "warning");
    assert.equal(cancelledItem.active, false);
  }
});

test("buildLiveLogItems exposes redacted memory context diagnostics", () => {
  const items = buildLiveLogItems([
    {
      id: "context-1",
      type: "context_loaded",
      title: "已载入会话上下文。",
      level: "info",
      createdAt: "2025-01-01T00:00:00Z",
      live: {
        schemaVersion: 1,
        kind: "status",
        stage: "organizing_state",
        displayText: "已载入会话上下文",
        diagnosticLabel: "conversation_context",
        parameterItems: [],
      },
      memoryContext: {
        schemaVersion: 1,
        kind: "conversation",
        summaryPreview: "用户之前问过上海天气。",
        memoryPreviews: ["tavily_search: 上海天气"],
        recentMessageCount: 2,
        cachedToolResultCount: 1,
      },
      rawRecord: {
        type: "context_loaded",
        payload: { raw_context: "SHOULD_STAY_RAW_ONLY" },
      },
    },
  ]);

  assert.equal(items.length, 1);
  assert.equal(items[0].kind, "status");
  assert.equal("rows" in items[0].details, false);
  assert.equal(items[0].details.rawJson.includes("上海天气"), true);
  assert.equal(items[0].details.rawJson.includes("SHOULD_STAY_RAW_ONLY"), false);
});

test("buildConversationStreamItems filters placeholder assistant messages", () => {
  const groups = buildRunActivityGroups([], [], []);
  const items = buildConversationStreamItems(
    [
      {
        id: "msg-1",
        role: "user",
        content: "Hello",
      },
      {
        id: "msg-2",
        role: "assistant",
        content: "AI回复",
      },
      {
        id: "msg-3",
        role: "assistant",
        content: "AI回复。",
      },
      {
        id: "msg-4",
        role: "assistant",
        content: "This is a real response",
      },
    ],
    groups,
  );

  const messageItems = items.filter(i => i.kind === "message");
  assert.equal(messageItems.length, 2);
  assert.equal(messageItems[0].message.content, "Hello");
  assert.equal(messageItems[1].message.content, "This is a real response");
});

test("buildConversationStreamItems keeps streaming messages with meaningful content", () => {
  const groups = buildRunActivityGroups(
    [{ id: "run-1", status: "running", artifactNames: [] }],
    [
      {
        id: "stream-1",
        title: "assistant_answer_delta",
        type: "assistant_answer_delta",
        answerStream: { schemaVersion: 1, streamIndex: 0, content: "Hello" },
        runId: "run-1",
      },
    ],
    [],
  );
  const items = buildConversationStreamItems([], groups);

  const streamItems = items.filter((i): i is Extract<typeof i, { kind: "message" }> => i.kind === "message" && Boolean(i.message.streaming));
  assert.equal(streamItems.length, 0);
});
