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
    throw new Error(`${name} is required for runtime-contract E2E`);
  }
  return value;
}

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
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
  ${sqlString(event.id)},
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

function seedCompletedArtifactTask(taskRoot, taskId) {
  const timestamp = nowIso();
  const runId = `run-e2e-${Date.now()}`;
  const artifactName = "report.html";
  const taskDir = path.join(taskRoot, taskId);
  const artifactDir = path.join(taskDir, "artifacts", "runs", runId);

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(
    path.join(artifactDir, artifactName),
    [
      "<!doctype html>",
      "<html><head><meta charset=\"utf-8\"><title>E2E Report</title></head>",
      "<body><h1>E2E 运行契约报告</h1><p>产物打开与下载链路可用。</p></body></html>",
    ].join(""),
    "utf8",
  );

  const userMessage = "E2E 运行契约验收";
  const assistantMessage = "E2E 报告已生成，可打开或下载。";
  runSql(`
UPDATE tasks
SET status = 'complete',
    model = 'deepseek:deepseek-chat',
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
  ${sqlString(userMessage)},
  'deepseek:deepseek-chat',
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
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(userMessage)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(assistantMessage)}, ${sqlString(timestamp)}, NULL);

${appendEventSql(taskId, {
  id: randomUUID().replaceAll("-", ""),
  type: "task_completed",
  message: "任务已完成。",
  createdAt: timestamp,
  payload: { previous_status: "running" },
  runId,
  level: "success",
})}

${appendEventSql(taskId, {
  id: randomUUID().replaceAll("-", ""),
  type: "final_answer",
  message: "Final answer generated",
  createdAt: timestamp,
  payload: { content: assistantMessage },
  runId,
  level: "success",
})}
`);
  return { artifactName, runId };
}

test.use({ acceptDownloads: true, baseURL: BASE_URL });

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

test("runtime task contracts expose artifacts and upload errors in the browser", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  const taskRoot = requirePath(TASK_ROOT, "MYAGENT_E2E_TASK_ROOT");
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek:deepseek-chat" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  const { artifactName, runId } = seedCompletedArtifactTask(taskRoot, taskId);

  const lightweightResponse = await request.get(`${API_URL}/api/tasks/${taskId}?include_events=false`, {
    headers: authHeaders(),
  });
  expect(lightweightResponse.ok()).toBeTruthy();
  const lightweightTask = await lightweightResponse.json();
  expect(lightweightTask.events).toEqual([]);
  expect(lightweightTask.artifacts.some((artifact) => artifact.name === artifactName)).toBeTruthy();

  const modelsResponse = await request.get(`${API_URL}/api/models`, { headers: authHeaders() });
  expect(modelsResponse.ok()).toBeTruthy();
  const models = await modelsResponse.json();
  expect(models.some((model) => typeof model.available === "boolean")).toBeTruthy();

  await page.goto("/");
  await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "01-history-loaded.png") });

  await page.getByRole("button", { name: /E2E/ }).first().click();
  await expect(page.getByText(artifactName)).toBeVisible();
  await expect(page.getByText("AI回复")).toBeVisible();
  await expect(page.getByText("已完成").first()).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "02-artifact-card.png") });

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "打开", exact: true }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup.locator("body")).toContainText("E2E 运行契约报告");
  await popup.screenshot({ fullPage: true, path: path.join(evidenceDir, "03-opened-report.png") });
  await popup.close();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(artifactName);
  await download.saveAs(path.join(evidenceDir, "downloaded-report.html"));
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "04-download-finished.png") });

  const seededHistoryRow = page.locator(".historyItemShell", { hasText: "E2E" }).first();
  await seededHistoryRow.getByRole("button", { name: /会话菜单/ }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "05-history-menu-open.png") });

  await page.getByRole("menuitem", { name: "重命名" }).click();
  const renameInput = page.getByLabel("重命名会话");
  await expect(renameInput).toBeVisible();
  await renameInput.fill("历史菜单验收");
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "06-history-rename-form.png") });
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".historyItemShell", { hasText: "历史菜单验收" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "07-history-renamed.png") });

  const renamedHistoryRow = page.locator(".historyItemShell", { hasText: "历史菜单验收" }).first();
  await renamedHistoryRow.getByRole("button", { name: /会话菜单/ }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("menuitem", { name: "删除" }).click();
  await expect(page.locator(".historyItemShell", { hasText: "历史菜单验收" })).toHaveCount(0);
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "08-history-deleted.png") });

  await page.getByRole("button", { name: "新建会话" }).click();
  const invalidJsonPath = path.join(evidenceDir, "invalid-upload.json");
  fs.writeFileSync(invalidJsonPath, "{ invalid json", "utf8");
  await page.locator("#document-files").setInputFiles(invalidJsonPath);
  await expect(page.getByText("invalid-upload.json")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "09-invalid-json-selected.png") });

  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/HTTP 400|内容不是合法 JSON|JSON 文件/)).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "10-invalid-json-error.png") });

  writeJson(path.join(evidenceDir, "assertions.json"), {
    artifactName,
    downloadedArtifact: "downloaded-report.html",
    historyRenameDeletePassed: true,
    includeEventsFalseReturnedEmptyEvents: true,
    modelsExposeAvailable: true,
    runId,
    taskId,
  });
});
