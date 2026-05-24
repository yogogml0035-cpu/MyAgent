import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const TASK_ROOT = process.env.MYAGENT_E2E_TASK_ROOT;
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";
const POSTGRES_CONTAINER = process.env.MYAGENT_E2E_POSTGRES_CONTAINER || "PostgreSQL";
const POSTGRES_USER = process.env.MYAGENT_E2E_POSTGRES_USER || "postgres";
const POSTGRES_DB = process.env.MYAGENT_E2E_POSTGRES_DB || "myagent";

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for task-log-artifact-delivery E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function nowIso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function sqlString(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function sqlJson(value) {
  return `${sqlString(JSON.stringify(value))}::jsonb`;
}

function runSql(sql) {
  execFileSync(
    "docker",
    [
      "exec",
      "-i",
      POSTGRES_CONTAINER,
      "psql",
      "-v",
      "ON_ERROR_STOP=1",
      "-U",
      POSTGRES_USER,
      "-d",
      POSTGRES_DB,
    ],
    {
      input: sql,
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
}

function appendEventSql(taskId, event) {
  return `
WITH next_seq AS (
  UPDATE tasks
  SET latest_event_seq = latest_event_seq + 1
  WHERE task_id = ${sqlString(taskId)}
  RETURNING latest_event_seq
)
INSERT INTO events (
  id, task_id, seq, type, message, created_at, payload, run_id, level, idempotency_key
)
SELECT
  ${sqlString(event.id ?? randomUUID().replaceAll("-", ""))},
  ${sqlString(taskId)},
  latest_event_seq,
  ${sqlString(event.type)},
  ${sqlString(event.message)},
  ${sqlString(event.createdAt)},
  ${sqlJson(event.payload)},
  ${event.runId ? sqlString(event.runId) : "NULL"},
  ${event.level ? sqlString(event.level) : "NULL"},
  NULL
FROM next_seq;
`;
}

function ensureTaskWorkspace(taskRoot, taskId) {
  const taskDir = path.join(taskRoot, taskId);
  fs.mkdirSync(taskDir, { recursive: true });
  return taskDir;
}

function seedLargeLogTask(taskId, title) {
  const runId = `run-large-log-${Date.now()}`;
  const startedAt = nowIso();
  const events = [];
  const toolDeltaCount = 1350;
  const thinkingCount = 800;
  const oversizedToolArgs = `{"description":"${"x".repeat(2048)}TOOL_ARG_TAIL_MARKER`;
  for (let index = 0; index < toolDeltaCount; index += 1) {
    const createdAt = nowIso(index * 10);
    events.push({
      type: "tool_call",
      message: "Calling tool: task",
      createdAt,
      level: "info",
      payload: {
        id: "call-large-task",
        name: "task",
        args: oversizedToolArgs,
        raw_args: oversizedToolArgs,
        partial: true,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "selecting_tool",
          tool_name: "task",
          tool_label: "调用工具",
          tool_call_id: "call-large-task",
          diagnostic_label: "tool_call_delta",
          parameter_items: [{ key: "args", value: oversizedToolArgs.slice(0, 160), truncated: true }],
        },
      },
    });
  }
  for (let index = 0; index < thinkingCount; index += 1) {
    const createdAt = nowIso((toolDeltaCount + index) * 15);
    events.push({
      type: "assistant_thinking_delta",
      message: "thinking",
      createdAt,
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: index + 1,
        content: "r",
        is_subgraph: false,
      },
    });
  }

  runSql(`
UPDATE tasks
SET status = 'running',
    title = ${sqlString(title)},
    model = 'deepseek-v4-flash-thinking',
    updated_at = ${sqlString(nowIso(42_200))},
    error = NULL,
    needs_input = NULL,
    active_run_id = ${sqlString(runId)}
WHERE task_id = ${sqlString(taskId)};

INSERT INTO runs (
  task_id, id, status, message, model, started_at, completed_at,
  error, needs_input, artifact_base_path, artifact_names
)
VALUES (
  ${sqlString(taskId)},
  ${sqlString(runId)},
  'running',
  ${sqlString(title)},
  'deepseek-v4-flash-thinking',
  ${sqlString(startedAt)},
  NULL,
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
)
ON CONFLICT (task_id, id) DO UPDATE
SET status = EXCLUDED.status,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    artifact_names = EXCLUDED.artifact_names;

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(startedAt)}, NULL);

${events.map((event) => appendEventSql(taskId, { ...event, runId })).join("\n")}
`);

  return { runId, eventCount: events.length };
}

function seedDocxArtifactTask(taskRoot, taskId, title) {
  const timestamp = nowIso();
  const runId = `run-docx-${Date.now()}`;
  const artifactName = "技术参数总结.docx";
  const taskDir = ensureTaskWorkspace(taskRoot, taskId);
  const artifactDir = path.join(taskDir, "artifacts", "runs", runId);
  const assistantMessage = "已生成技术参数总结。请使用下方下载卡片获取正式交付文件。";

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(
    path.join(artifactDir, artifactName),
    Buffer.from(`DOCX-STUB:${artifactName}:${runId}`),
  );

  runSql(`
UPDATE tasks
SET status = 'complete',
    title = ${sqlString(title)},
    model = 'deepseek-v4-flash',
    updated_at = ${sqlString(timestamp)},
    error = NULL,
    needs_input = NULL,
    active_run_id = NULL
WHERE task_id = ${sqlString(taskId)};

INSERT INTO runs (
  task_id, id, status, message, model, started_at, completed_at,
  error, needs_input, artifact_base_path, artifact_names
)
VALUES (
  ${sqlString(taskId)},
  ${sqlString(runId)},
  'complete',
  ${sqlString(title)},
  'deepseek-v4-flash',
  ${sqlString(timestamp)},
  ${sqlString(timestamp)},
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  ${sqlJson([artifactName])}
)
ON CONFLICT (task_id, id) DO UPDATE
SET status = EXCLUDED.status,
    completed_at = EXCLUDED.completed_at,
    artifact_names = EXCLUDED.artifact_names;

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(assistantMessage)}, ${sqlString(timestamp)}, NULL);

${appendEventSql(taskId, {
  type: "task_completed",
  message: "任务已完成。",
  createdAt: timestamp,
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
  runId,
  level: "success",
})}

${appendEventSql(taskId, {
  type: "final_answer",
  message: "Final answer generated",
  createdAt: timestamp,
  payload: {
    content: assistantMessage,
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
  runId,
  level: "success",
})}
`);

  return { artifactName, runId };
}

function seedMissingArtifactTask(taskId, title) {
  const timestamp = nowIso();
  const runId = `run-missing-artifact-${Date.now()}`;
  const assistantMessage = "文件未生成或未登记为产物，请重新生成交付文件后再提交。";
  const needsInput = {
    message: assistantMessage,
    reason: "artifact_missing",
  };

  runSql(`
UPDATE tasks
SET status = 'needs_input',
    title = ${sqlString(title)},
    model = 'deepseek-v4-flash',
    updated_at = ${sqlString(timestamp)},
    error = NULL,
    needs_input = ${sqlJson(needsInput)},
    active_run_id = NULL
WHERE task_id = ${sqlString(taskId)};

INSERT INTO runs (
  task_id, id, status, message, model, started_at, completed_at,
  error, needs_input, artifact_base_path, artifact_names
)
VALUES (
  ${sqlString(taskId)},
  ${sqlString(runId)},
  'needs_input',
  ${sqlString(title)},
  'deepseek-v4-flash',
  ${sqlString(timestamp)},
  ${sqlString(timestamp)},
  NULL,
  ${sqlJson(needsInput)},
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
)
ON CONFLICT (task_id, id) DO UPDATE
SET status = EXCLUDED.status,
    completed_at = EXCLUDED.completed_at,
    needs_input = EXCLUDED.needs_input,
    artifact_names = EXCLUDED.artifact_names;

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(assistantMessage)}, ${sqlString(timestamp)}, 'warning');

${appendEventSql(taskId, {
  type: "task_failed",
  message: assistantMessage,
  createdAt: timestamp,
  payload: {
    live: {
      schema_version: 1,
      kind: "status",
      stage: "needs_input",
      display_text: "文件未生成或未登记为产物",
      diagnostic_label: "runner.artifact_validation",
      parameter_items: [],
      result_status: "warning",
    },
  },
  runId,
  level: "warning",
})}
`);

  return { runId };
}

async function deleteTaskIfPresent(request, taskId) {
  if (!taskId) {
    return;
  }
  try {
    await request.delete(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
    });
  } catch {
    // Ignore cleanup failures after Playwright has already torn down the request context.
  }
}

function retireSyntheticRunningTask(taskId, runId) {
  if (!taskId || !runId) {
    return;
  }
  const timestamp = nowIso();
  runSql(`
UPDATE tasks
SET status = 'cancelled',
    updated_at = ${sqlString(timestamp)},
    error = NULL,
    needs_input = NULL,
    active_run_id = NULL
WHERE task_id = ${sqlString(taskId)};

UPDATE runs
SET status = 'cancelled',
    completed_at = ${sqlString(timestamp)},
    error = NULL,
    needs_input = NULL
WHERE task_id = ${sqlString(taskId)}
  AND id = ${sqlString(runId)};
`);
}

test.use({ acceptDownloads: true, baseURL: BASE_URL });

test("large logs stay responsive with lightweight projection", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  const scenarioDir = path.join(evidenceDir, "large-log-responsive");
  fs.mkdirSync(scenarioDir, { recursive: true });

  const largeLogTitle = `大日志验收-${randomUUID().slice(0, 8)}`;
  let largeLogTaskId = "";
  let largeLogRunId = "";

  try {
    const largeLogCreated = await request.post(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
      data: { model: "deepseek-v4-flash-thinking" },
    });
    expect(largeLogCreated.status()).toBe(201);
    largeLogTaskId = (await largeLogCreated.json()).task_id;
    const largeLogSeed = seedLargeLogTask(largeLogTaskId, largeLogTitle);
    largeLogRunId = largeLogSeed.runId;

    await page.goto("/");
    await expect(page.getByRole("button", { name: largeLogTitle, exact: true })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(scenarioDir, "01-history-with-seeded-task.png"),
    });

    await page.getByRole("button", { name: largeLogTitle, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: largeLogTitle })).toBeVisible();
    const stopButton = page.getByRole("button", { name: "停止当前会话任务" });
    await expect(stopButton).toBeVisible();
    const largeLogPanel = page.getByRole("region", { name: /第 1 轮进度日志/ }).first();
    await expect(largeLogPanel).toBeVisible({ timeout: 20_000 });
    const visibleRows = largeLogPanel.locator(".liveStatusRow, .liveToolCard");
    const rowCount = await visibleRows.count();
    expect(rowCount).toBeGreaterThan(0);
    expect(rowCount).toBeLessThan(120);
    expect(rowCount).toBeLessThan(largeLogSeed.eventCount);
    await expect(largeLogPanel).not.toContainText("TOOL_ARG_TAIL_MARKER");
    await page.screenshot({
      fullPage: true,
      path: path.join(scenarioDir, "02-large-log-collapsed.png"),
    });

    await page.mouse.wheel(0, 1200);
    const logClickPoint = await page.evaluate(() => {
      const panel = document.querySelector('[aria-label*="进度日志"] .logList, [aria-label*="进度日志"]');
      if (!panel) {
        return null;
      }
      const rect = panel.getBoundingClientRect();
      return { x: rect.left + 48, y: rect.top + 48 };
    });
    expect(logClickPoint).toBeTruthy();
    await page.mouse.click(logClickPoint.x, logClickPoint.y);
    await page.waitForTimeout(150);
    await expect(stopButton).toBeEnabled();
    await stopButton.click({ trial: true });
    fs.writeFileSync(
      path.join(scenarioDir, "assertions.json"),
      `${JSON.stringify(
        {
          largeLogEventCount: largeLogSeed.eventCount,
          largeLogRunId: largeLogSeed.runId,
          largeLogVisibleRowCount: rowCount,
          largeToolDeltaCount: 1350,
          logRegionClickedAfterScroll: true,
          stopButtonClickable: true,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    retireSyntheticRunningTask(largeLogTaskId, largeLogRunId);
    await deleteTaskIfPresent(request, largeLogTaskId);
  }
});

test("docx artifacts render a download card and download with the expected filename", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const taskRoot = requirePath(TASK_ROOT, "MYAGENT_E2E_TASK_ROOT");
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  const scenarioDir = path.join(evidenceDir, "docx-artifact-download");
  fs.mkdirSync(scenarioDir, { recursive: true });

  const artifactTitle = `交付文件验收-${randomUUID().slice(0, 8)}`;
  let artifactTaskId = "";
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  try {
    const artifactCreated = await request.post(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
      data: { model: "deepseek-v4-flash" },
    });
    expect(artifactCreated.status()).toBe(201);
    artifactTaskId = (await artifactCreated.json()).task_id;
    const artifactSeed = seedDocxArtifactTask(taskRoot, artifactTaskId, artifactTitle);

    await page.goto("/");
    await expect(page.getByRole("button", { name: artifactTitle, exact: true })).toBeVisible();
    await page.getByRole("button", { name: artifactTitle, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: artifactTitle })).toBeVisible();
    await expect(page.getByText(artifactSeed.artifactName)).toBeVisible();
    const artifactFooter = page.locator(".messageArtifactFooter", {
      has: page.getByText(artifactSeed.artifactName, { exact: true }),
    });
    await expect(artifactFooter).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(scenarioDir, "01-docx-artifact-card.png"),
    });

    const downloadDocxPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: `下载 ${artifactSeed.artifactName}` }).click();
    const downloadDocx = await downloadDocxPromise;
    expect(downloadDocx.suggestedFilename()).toBe(artifactSeed.artifactName);
    await downloadDocx.saveAs(path.join(scenarioDir, artifactSeed.artifactName));
    await page.screenshot({
      fullPage: true,
      path: path.join(scenarioDir, "02-docx-download-finished.png"),
    });

    expect(consoleErrors).toEqual([]);
    fs.writeFileSync(
      path.join(scenarioDir, "assertions.json"),
      `${JSON.stringify(
        {
          artifactName: artifactSeed.artifactName,
          runId: artifactSeed.runId,
          consoleErrors,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    await deleteTaskIfPresent(request, artifactTaskId);
  }
});

test("missing file delivery stays in needs-input without fake download links", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  const scenarioDir = path.join(evidenceDir, "missing-artifact-warning");
  fs.mkdirSync(scenarioDir, { recursive: true });

  const missingArtifactTitle = `缺失交付验收-${randomUUID().slice(0, 8)}`;
  let missingArtifactTaskId = "";

  try {
    const created = await request.post(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
      data: { model: "deepseek-v4-flash" },
    });
    expect(created.status()).toBe(201);
    missingArtifactTaskId = (await created.json()).task_id;
    const missingArtifactSeed = seedMissingArtifactTask(missingArtifactTaskId, missingArtifactTitle);

    await page.goto("/");
    await expect(page.getByRole("button", { name: missingArtifactTitle, exact: true })).toBeVisible();
    await page.getByRole("button", { name: missingArtifactTitle, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: missingArtifactTitle })).toBeVisible();
    await expect(
      page.getByText("文件未生成或未登记为产物，请重新生成交付文件后再提交。", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /下载 .*\.docx/ })).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(scenarioDir, "01-missing-artifact-warning.png"),
    });

    const missingTaskResponse = await request.get(
      `${API_URL}/api/tasks/${encodeURIComponent(missingArtifactTaskId)}?include_events=false`,
      {
        headers: authHeaders(),
      },
    );
    expect(missingTaskResponse.ok()).toBeTruthy();
    const missingTaskState = await missingTaskResponse.json();
    expect(missingTaskState.status).toBe("needs_input");
    expect(missingTaskState.artifacts).toEqual([]);

    fs.writeFileSync(
      path.join(scenarioDir, "assertions.json"),
      `${JSON.stringify(
        {
          runId: missingArtifactSeed.runId,
          status: missingTaskState.status,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    await deleteTaskIfPresent(request, missingArtifactTaskId);
  }
});
