import assert from "node:assert/strict";
import test from "node:test";

import {
  backendDownMessage,
  buildArtifactRequest,
  deriveConversationTitle,
  formatHttpErrorMessage,
  formatRequestFailure,
  isTaskActive,
  mergeExecutionLogs,
  mergeTaskState,
  normalizeTaskSummaries,
  normalizeTaskState,
  resolveApiBaseUrl,
  type TaskState,
} from "../app/task-state";

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
  assert.equal(state.statusLabel, "unknown: paused");
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
      messages: [{ id: "message-1", role: "user", content: "请分析", run_id: "run-1" }],
      events: [{ id: "event-1", type: "task_completed", message: "完成", run_id: "run-1" }],
      artifacts: [{ name: "report.html", type: "html", run_id: "run-1" }],
    },
    "fallback",
  );

  assert.equal(state.runs[0].id, "run-1");
  assert.equal(state.messages[0].runId, "run-1");
  assert.equal(state.logs[0].runId, "run-1");
  assert.equal(state.artifacts[0].runId, "run-1");
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
    "Invalid or missing access token",
  );
});

test("resolveApiBaseUrl preserves explicit backend URLs without trailing slashes", () => {
  assert.equal(
    resolveApiBaseUrl("http://10.11.148.97:8001/"),
    "http://10.11.148.97:8001",
  );
});

test("resolveApiBaseUrl derives the backend URL from the current page host", () => {
  assert.equal(
    resolveApiBaseUrl("auto", { protocol: "http:", hostname: "localhost" }),
    "http://localhost:8001",
  );
  assert.equal(
    resolveApiBaseUrl(undefined, { protocol: "http:", hostname: "10.11.148.97" }),
    "http://10.11.148.97:8001",
  );
});
