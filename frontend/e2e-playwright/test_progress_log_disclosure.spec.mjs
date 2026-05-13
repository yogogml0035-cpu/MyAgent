import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";
const POSTGRES_CONTAINER = process.env.MYAGENT_E2E_POSTGRES_CONTAINER || "PostgreSQL";
const POSTGRES_USER = process.env.MYAGENT_E2E_POSTGRES_USER || "postgres";
const POSTGRES_DB = process.env.MYAGENT_E2E_POSTGRES_DB || "myagent";

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for progress-log E2E`);
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
  ${sqlString(randomUUID().replaceAll("-", ""))},
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

function seedRunningProgressLogTask(taskId, title) {
  const runId = `run-progress-e2e-${Date.now()}`;
  const startedAt = nowIso();
  const eventSeeds = [
    {
      type: "status_update",
      message: "State update: model",
      createdAt: nowIso(1000),
      level: "info",
      payload: {
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
    {
      type: "tool_call",
      message: "Tool call: tavily_search",
      createdAt: nowIso(2000),
      level: "info",
      payload: {
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "using_tool",
          tool_name: "tavily_search",
          tool_call_id: "tool-progress-e2e",
          parameter_items: [{ key: "query", value: "progress log e2e" }],
        },
      },
    },
    {
      type: "tool_result",
      message: "Tool result: tavily_search",
      createdAt: nowIso(3000),
      level: "success",
      payload: {
        live: {
          schema_version: 1,
          kind: "tool_result",
          stage: "completed",
          tool_name: "tavily_search",
          tool_call_id: "tool-progress-e2e",
          result_status: "success",
          result_count: 2,
          parameter_items: [],
        },
      },
    },
    {
      type: "assistant_answer_delta",
      message: "AI reply chunk",
      createdAt: nowIso(4000),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 1,
        content: "这段原始流式内容不应显示在折叠行里。",
      },
    },
  ];

  runSql(`
UPDATE tasks
SET status = 'running',
    title = ${sqlString(title)},
    model = 'deepseek:deepseek-chat',
    updated_at = ${sqlString(startedAt)},
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
  'deepseek:deepseek-chat',
  ${sqlString(startedAt)},
  NULL,
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(startedAt)}, NULL);

${eventSeeds.map((event) => appendEventSql(taskId, { ...event, runId })).join("\n")}
`);

  return runId;
}

test.use({ baseURL: BASE_URL });

test("progress log rows keep left timestamps and all rows expand diagnostics", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const title = `进度日志验收-${randomUUID().slice(0, 8)}`;
  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek:deepseek-chat" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  const runId = seedRunningProgressLogTask(taskId, title);

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-history-with-seeded-task.png"),
    });

    await page.getByRole("button", { name: title, exact: true }).click();
    const logPanel = page.getByRole("region", { name: /进度日志/ }).first();
    await expect(logPanel).toBeVisible();
    const rows = logPanel.locator(".liveStatusRow, .liveToolCard");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator("summary").getByText("AI正在思考...")).toBeVisible();
    await expect(rows.nth(1).locator("summary").getByText("联网搜索已返回结果")).toBeVisible();
    await expect(rows.nth(2).locator("summary").getByText("AI正在生成结果")).toBeVisible();
    await expect(logPanel.getByText("这段原始流式内容不应显示")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-progress-log-collapsed.png"),
    });

    for (let index = 0; index < 3; index += 1) {
      const row = rows.nth(index);
      await expect(row).toHaveJSProperty("tagName", "DETAILS");
      const summary = row.locator("summary");
      const timeBox = await summary.locator("time").boundingBox();
      const labelBox = await summary.locator("span:not(.thinkingDots), strong").first().boundingBox();
      const rowBox = await row.boundingBox();
      expect(timeBox).toBeTruthy();
      expect(labelBox).toBeTruthy();
      expect(rowBox).toBeTruthy();
      expect(timeBox.x).toBeLessThan(labelBox.x);
      expect(timeBox.x - rowBox.x).toBeLessThan(20);
    }

    await rows.nth(2).locator("summary").click();
    await expect(rows.nth(2)).toHaveAttribute("open", "");
    await expect(rows.nth(2).locator("dl")).toHaveCount(0);
    await expect(rows.nth(2).locator("pre")).toContainText('"type": "assistant_answer_delta"');
    await expect(rows.nth(2).locator("pre")).toContainText('"content_hidden": true');
    await expect(rows.nth(2).locator("dt")).toHaveCount(0);
    await expect(rows.nth(2).getByText("这段原始流式内容不应显示")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-generation-row-expanded.png"),
    });

    await rows.nth(1).locator("summary").click();
    await expect(rows.nth(1)).toHaveAttribute("open", "");
    await expect(rows.nth(1).locator("dl")).toHaveCount(0);
    await expect(rows.nth(1).locator("pre")).toContainText('"type": "tool_result"');
    await expect(rows.nth(1).locator("pre")).toContainText('"tool_name": "tavily_search"');
    await expect(rows.nth(1).locator("dt")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-tool-row-expanded.png"),
    });

    await rows.nth(0).locator("summary").click();
    await expect(rows.nth(0)).toHaveAttribute("open", "");
    await expect(rows.nth(0).locator("dl")).toHaveCount(0);
    await expect(rows.nth(0).locator("pre")).toContainText('"type": "status_update"');
    await expect(rows.nth(0).locator("pre")).toContainText('"diagnostic_label": "model"');
    await expect(rows.nth(0).locator("dt")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "05-thinking-row-expanded.png"),
    });
  } finally {
    runSql(`
UPDATE tasks
SET status = 'complete',
    active_run_id = NULL,
    updated_at = ${sqlString(nowIso())}
WHERE task_id = ${sqlString(taskId)};

UPDATE runs
SET status = 'complete',
    completed_at = ${sqlString(nowIso())}
WHERE task_id = ${sqlString(taskId)}
  AND id = ${sqlString(runId)};
`);

    const deleteResponse = await request.delete(`${API_URL}/api/tasks/${taskId}`, {
      headers: authHeaders(),
    });
    expect(deleteResponse.ok()).toBeTruthy();
  }
});
