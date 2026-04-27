import assert from "node:assert/strict";
import test from "node:test";

import {
  buildArtifactRequest,
  isTaskActive,
  mergeExecutionLogs,
  mergeTaskState,
  normalizeTaskState,
  type TaskState,
} from "../app/task-state";

function baseState(overrides: Partial<TaskState> = {}): TaskState {
  return {
    id: "task-1",
    status: "running",
    statusLabel: "running",
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
