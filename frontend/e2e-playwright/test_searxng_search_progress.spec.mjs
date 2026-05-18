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
    throw new Error(`${name} is required for SearXNG search progress E2E`);
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

function seedSearxngSearchTask(taskId, title) {
  const runId = `run-searxng-e2e-${Date.now()}`;
  const startedAt = nowIso();
  const completedAt = nowIso(5000);
  const toolCallId = `call-searxng-${randomUUID().slice(0, 8)}`;
  const events = [
    {
      type: "tool_call",
      message: "Tool call: searxng_search",
      createdAt: nowIso(1000),
      level: "info",
      payload: {
        id: toolCallId,
        name: "searxng_search",
        args: { query: "OpenAI", max_results: 2, topic: "general" },
        raw_args: "{\"query\":\"OpenAI\",\"max_results\":2,\"topic\":\"general\"}",
        partial: false,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "using_tool",
          tool_name: "searxng_search",
          tool_label: "联网搜索",
          tool_call_id: toolCallId,
          parameter_items: [
            { key: "query", value: "OpenAI" },
            { key: "max_results", value: 2 },
          ],
        },
      },
    },
    {
      type: "tool_result",
      message: "Tool result: searxng_search",
      createdAt: nowIso(2200),
      level: "success",
      payload: {
        name: "searxng_search",
        status: "success",
        content: "Infobox: OpenAI\\n    Wikipedia: https://en.wikipedia.org/wiki/OpenAI",
        live: {
          schema_version: 1,
          kind: "tool_result",
          stage: "completed",
          tool_name: "searxng_search",
          tool_label: "联网搜索",
          tool_call_id: toolCallId,
          result_status: "success",
          result_count: 1,
          parameter_items: [],
        },
      },
    },
    {
      type: "task_completed",
      message: "任务已完成。",
      createdAt: nowIso(4200),
      level: "success",
      payload: {
        previous_status: "running",
        live: {
          schema_version: 1,
          kind: "status",
          stage: "completed",
          display_text: "任务已完成",
          diagnostic_label: "runner.terminal",
          parameter_items: [],
        },
      },
    },
    {
      type: "final_answer",
      message: "Final answer generated",
      createdAt: nowIso(4300),
      level: "success",
      payload: { content: "已通过本地 SearXNG 搜索并整理结果。" },
    },
  ];

  runSql(`
UPDATE tasks
SET status = 'complete',
    title = ${sqlString(title)},
    model = 'deepseek:deepseek-chat',
    updated_at = ${sqlString(completedAt)},
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
  'deepseek:deepseek-chat',
  ${sqlString(startedAt)},
  ${sqlString(completedAt)},
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(startedAt)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString("已通过本地 SearXNG 搜索并整理结果。")}, ${sqlString(completedAt)}, NULL);

${events.map((event) => appendEventSql(taskId, { ...event, runId })).join("\n")}
`);
}

test.use({ baseURL: BASE_URL });

test("browser progress log displays SearXNG search tool activity", async ({ page, request }) => {
  test.setTimeout(45_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const title = `SearXNG验收-${randomUUID().slice(0, 8)}`;
  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek:deepseek-chat" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;

  try {
    seedSearxngSearchTask(taskId, title);

    await page.goto("/");
    await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-history-with-searxng-task.png"),
    });

    await page.getByRole("button", { name: title, exact: true }).click();
    const logPanel = page.getByRole("region", { name: /进度日志/ }).first();
    await expect(logPanel).toBeVisible();
    const rows = logPanel.locator(".liveStatusRow, .liveToolCard");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator("summary").getByText("调用联网搜索")).toBeVisible();
    await expect(rows.nth(1).locator("summary").getByText("联网搜索已返回结果")).toBeVisible();
    await expect(rows.nth(2).locator("summary").getByText("任务已完成")).toBeVisible();
    await expect(rows.nth(0).locator("summary")).not.toContainText("searxng_search");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-searxng-progress-collapsed.png"),
    });

    await rows.nth(0).locator("summary").click();
    await expect(rows.nth(0).locator("pre")).toContainText('"tool_name": "searxng_search"');
    await expect(rows.nth(0).locator("pre")).toContainText('"query": "OpenAI"');
    await rows.nth(1).locator("summary").click();
    await expect(rows.nth(1).locator("pre")).toContainText('"tool_name": "searxng_search"');
    await expect(rows.nth(1).locator("pre")).toContainText("Infobox: OpenAI");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-searxng-progress-expanded.png"),
    });
  } finally {
    await request.delete(`${API_URL}/api/tasks/${taskId}`, { headers: authHeaders() });
  }
});
