import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
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
    throw new Error(`${name} is required for resource-upload E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
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
  ${sqlString(event.id || randomUUID())},
  ${sqlString(taskId)},
  latest_event_seq,
  ${sqlString(event.type)},
  ${sqlString(event.message)},
  ${sqlString(event.createdAt)},
  ${sqlJson(event.payload || {})},
  ${event.runId ? sqlString(event.runId) : "NULL"},
  ${event.level ? sqlString(event.level) : "NULL"},
  NULL
FROM next_seq;
`;
}

function seedHarnessRun(taskId, runId, message, answer) {
  const timestamp = nowIso();
  runSql(`
UPDATE tasks
SET status = 'complete',
    updated_at = ${sqlString(timestamp)},
    active_run_id = NULL,
    error = NULL,
    needs_input = NULL
WHERE task_id = ${sqlString(taskId)};

INSERT INTO runs (
  task_id, id, status, message, model, started_at, completed_at,
  error, needs_input, artifact_base_path, artifact_names
)
VALUES (
  ${sqlString(taskId)},
  ${sqlString(runId)},
  'complete',
  ${sqlString(message)},
  'deepseek:deepseek-chat',
  ${sqlString(timestamp)},
  ${sqlString(timestamp)},
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(message)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(answer)}, ${sqlString(timestamp)}, NULL);

${appendEventSql(taskId, {
  type: "tool_call",
  message: "Calling tool: list_uploaded_resources",
  createdAt: timestamp,
  runId,
  level: "info",
  payload: {
    name: "list_uploaded_resources",
    args: {},
    live: {
      schema_version: 1,
      kind: "tool_call",
      stage: "using_tool",
      tool_name: "list_uploaded_resources",
      tool_label: "处理资源文件",
      parameter_items: [],
    },
  },
})}

${appendEventSql(taskId, {
  type: "tool_result",
  message: "Tool result (list_uploaded_resources): success",
  createdAt: timestamp,
  runId,
  level: "info",
  payload: {
    name: "list_uploaded_resources",
    status: "success",
    content: JSON.stringify({
      ok: true,
      data: {
        resources: ["brief.docx", "data.xlsx", "config.json", "notes.txt"],
      },
    }),
    live: {
      schema_version: 1,
      kind: "tool_result",
      stage: "completed",
      tool_name: "list_uploaded_resources",
      tool_label: "处理资源文件",
      parameter_items: [],
      result_status: "success",
    },
  },
})}

${appendEventSql(taskId, {
  type: "task_completed",
  message: "任务已完成。",
  createdAt: timestamp,
  runId,
  level: "success",
  payload: { previous_status: "running" },
})}

${appendEventSql(taskId, {
  type: "final_answer",
  message: "Final answer generated",
  createdAt: timestamp,
  runId,
  level: "success",
  payload: { content: answer },
})}
`);
}

function writeFixtureFiles(evidenceDir) {
  const fixtureDir = path.join(evidenceDir, "fixtures");
  fs.mkdirSync(fixtureDir, { recursive: true });
  fs.writeFileSync(path.join(fixtureDir, "notes.txt"), "TXT notes: alpha\nbeta\n", "utf8");
  fs.writeFileSync(path.join(fixtureDir, "config.json"), '{"project":"MyAgent","format":"json"}\n', "utf8");
  const repoRoot = path.resolve(process.cwd(), "..");
  const bundledPython =
    process.env.MYAGENT_E2E_PYTHON || path.join(repoRoot, "backend", ".venv", "bin", "python");

  execFileSync(
    fs.existsSync(bundledPython) ? bundledPython : "python",
    [
      "-",
      path.join(fixtureDir, "brief.docx"),
      path.join(fixtureDir, "data.xlsx"),
    ],
    {
      input: `
import sys
from docx import Document
from openpyxl import Workbook

doc = Document()
doc.add_heading("Harness Brief", level=1)
doc.add_paragraph("Word file uploaded as a task resource.")
doc.save(sys.argv[1])

wb = Workbook()
ws = wb.active
ws.title = "明细"
ws.append(["名称", "金额"])
ws.append(["A", 10])
wb.save(sys.argv[2])
`,
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  return fixtureDir;
}

test.use({ baseURL: BASE_URL });

test("browser upload accepts document resources and renders harness tool progress", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  requirePath(TASK_ROOT, "MYAGENT_E2E_TASK_ROOT");
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });
  const fixtureDir = writeFixtureFiles(evidenceDir);

  const answer = "已按资源工具读取 DOCX、XLSX、JSON 和 TXT，关键差异已汇总。";
  let taskId = "";
  let releaseMessageRoute = () => {};
  let messageRouteSeen = Promise.resolve();
  messageRouteSeen = new Promise((resolve) => {
    void page.route(/\/api\/tasks\/[^/]+\/messages$/, async (route) => {
      const routeUrl = new URL(route.request().url());
      taskId = routeUrl.pathname.split("/")[3];
      resolve(undefined);
      await new Promise((routeRelease) => {
        releaseMessageRoute = routeRelease;
      });
      seedHarnessRun(
        taskId,
        `run-e2e-${Date.now()}`,
        "总结这些文件并指出关键差异",
        answer,
      );
      const stateResponse = await request.get(`${API_URL}/api/tasks/${taskId}`, {
        headers: authHeaders(),
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(await stateResponse.json()),
      });
    });
  });

  await page.goto("/");
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "01-empty-workspace.png") });

  await page.locator("#document-files").setInputFiles([
    path.join(fixtureDir, "brief.docx"),
    path.join(fixtureDir, "data.xlsx"),
    path.join(fixtureDir, "config.json"),
    path.join(fixtureDir, "notes.txt"),
  ]);
  await expect(page.getByText("通用文件资源")).toBeVisible();
  await expect(page.getByText(/brief\.docx/)).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "02-files-selected.png") });

  await page.getByPlaceholder("尽管问...").fill("总结这些文件并指出关键差异");
  await page.getByRole("button", { name: "发送" }).click();
  await messageRouteSeen;
  await expect(page.getByRole("button", { name: "发送中" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "03-sending-with-files.png") });
  releaseMessageRoute();

  await expect(page.getByText("已上传 4 个文件")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "04-after-upload-state.png") });
  await expect(page.getByText("处理资源文件").first()).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "05-tool-progress.png") });
  await expect(page.getByText(answer)).toBeVisible();
  await expect(page.getByText("已完成").first()).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "06-complete-answer.png") });

  if (taskId) {
    await request.delete(`${API_URL}/api/tasks/${taskId}`, { headers: authHeaders() });
  }
});
