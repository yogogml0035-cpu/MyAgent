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
const EXPECT_UPLOAD_LIMIT_BYTES = Number(process.env.MYAGENT_E2E_EXPECT_UPLOAD_LIMIT_BYTES || "0");
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
  const uniqueTitle = `E2E-${randomUUID().slice(0, 8)}`;
  const taskDir = path.join(taskRoot, taskId);
  const artifactDir = path.join(taskDir, "artifacts", "runs", runId);

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(
    path.join(artifactDir, artifactName),
    [
      "<!doctype html>",
      "<html><head><meta charset=\"utf-8\"><title>E2E Report</title></head>",
      "<body><h1>E2E 运行契约报告</h1><p>产物打开与下载链路可用。</p>",
      "<script>document.body.setAttribute('data-script-executed', 'yes');</script>",
      "</body></html>",
    ].join(""),
    "utf8",
  );

  const userMessage = "E2E 运行契约验收";
  const assistantMessage = "E2E 报告已生成，可打开或下载。";
  runSql(`
UPDATE tasks
SET status = 'complete',
    title = ${sqlString(uniqueTitle)},
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
  ${sqlString(userMessage)},
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
  return { artifactName, runId, uniqueTitle };
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
  const browserAuthSignals = {
    apiHeader: false,
    artifactHeader: false,
    sseQueryToken: false,
  };

  page.on("request", (browserRequest) => {
    const url = browserRequest.url();
    if (!url.startsWith(API_URL)) {
      return;
    }
    const headers = browserRequest.headers();
    if (headers["x-myagent-token"] === ACCESS_TOKEN) {
      browserAuthSignals.apiHeader = true;
    }
    if (url.includes("/artifacts/") && headers["x-myagent-token"] === ACCESS_TOKEN) {
      browserAuthSignals.artifactHeader = true;
    }
    if (url.includes("/stream") && new URL(url).searchParams.get("token") === ACCESS_TOKEN) {
      browserAuthSignals.sseQueryToken = true;
    }
  });

  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek-v4-flash" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  const { artifactName, runId, uniqueTitle } = seedCompletedArtifactTask(taskRoot, taskId);

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

  await expect(page.locator(".modelPickerTrigger")).toHaveCount(1);
  await page.getByRole("button", { name: "DeepSeek V4 Flash" }).click();
  await expect(page.locator(".modelOption")).toHaveCount(2);
  await expect(page.locator(".modelOptionTitle").getByText("DeepSeek V4 Flash", { exact: true })).toHaveCount(1);
  await expect(
    page.locator(".modelOptionTitle").getByText("DeepSeek V4 Flash Thinking", { exact: true }),
  ).toHaveCount(1);
  await expect(page.getByText("GPT-4o")).toHaveCount(0);
  await expect(page.getByText("Claude Sonnet")).toHaveCount(0);
  await page.locator(".modelOption").filter({
    has: page.locator(".modelOptionTitle").getByText("DeepSeek V4 Flash Thinking", { exact: true }),
  }).click();
  await expect(page.getByRole("button", { name: "DeepSeek V4 Flash Thinking" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "02-deepseek-v4-flash-picker.png") });

  await page.getByRole("button", { name: uniqueTitle, exact: true }).click();
  await expect(page.getByText(artifactName)).toBeVisible();
  await expect(page.getByText("AI回复")).toBeVisible();
  await expect(page.getByText("已完成").first()).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "03-artifact-card.png") });

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "打开", exact: true }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup.getByText("此 HTML 产物已在禁用脚本的沙箱 iframe 中预览。")).toBeVisible();
  const reportFrame = popup.frameLocator("iframe");
  await expect(reportFrame.getByText("E2E 运行契约报告")).toBeVisible();
  await expect(reportFrame.locator("body")).not.toHaveAttribute("data-script-executed", "yes");
  await popup.screenshot({ fullPage: true, path: path.join(evidenceDir, "04-opened-report-sandboxed.png") });
  await popup.close();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(artifactName);
  await download.saveAs(path.join(evidenceDir, "downloaded-report.html"));
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "05-download-finished.png") });

  if (ACCESS_TOKEN) {
    await page.evaluate(
      ({ apiUrl, taskId, token }) =>
        new Promise((resolve, reject) => {
          const source = new EventSource(
            `${apiUrl}/api/tasks/${encodeURIComponent(taskId)}/stream?token=${encodeURIComponent(token)}`,
          );
          const timer = window.setTimeout(() => {
            source.close();
            reject(new Error("Timed out waiting for authenticated SSE"));
          }, 10_000);
          source.onmessage = (event) => {
            if (event.data.includes("done")) {
              window.clearTimeout(timer);
              source.close();
              resolve(true);
            }
          };
          source.onerror = () => {
            window.clearTimeout(timer);
            source.close();
            reject(new Error("Authenticated SSE failed"));
          };
        }),
      { apiUrl: API_URL, taskId, token: ACCESS_TOKEN },
    );
    expect(browserAuthSignals.apiHeader).toBeTruthy();
    expect(browserAuthSignals.artifactHeader).toBeTruthy();
    expect(browserAuthSignals.sseQueryToken).toBeTruthy();
  }

  const seededHistoryRow = page.locator(".historyItemShell", { hasText: uniqueTitle }).first();
  await seededHistoryRow.getByRole("button", { name: /会话菜单/ }).click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "06-history-menu-open.png") });

  await page.getByRole("menuitem", { name: "重命名" }).click();
  const renameInput = page.getByLabel("重命名会话");
  await expect(renameInput).toBeVisible();
  await renameInput.fill("历史菜单验收");
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "07-history-rename-form.png") });
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".historyItemShell", { hasText: "历史菜单验收" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "08-history-renamed.png") });

  const renamedHistoryRow = page.locator(".historyItemShell", { hasText: "历史菜单验收" }).first();
  await renamedHistoryRow.getByRole("button", { name: /会话菜单/ }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("menuitem", { name: "删除" }).click();
  await expect(page.locator(".historyItemShell", { hasText: "历史菜单验收" })).toHaveCount(0);
  await expect.poll(() => fs.existsSync(path.join(taskRoot, taskId))).toBe(false);
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "09-history-deleted.png") });

  await page.getByRole("button", { name: "新建会话" }).click();
  const invalidJsonPath = path.join(evidenceDir, "invalid-upload.json");
  fs.writeFileSync(invalidJsonPath, "{ invalid json", "utf8");
  await page.locator("#document-files").setInputFiles(invalidJsonPath);
  await expect(page.getByText("invalid-upload.json")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "10-invalid-json-selected.png") });

  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/HTTP 400|内容不是合法 JSON|JSON 文件/)).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "11-invalid-json-error.png") });

  let oversizedUploadRejected = false;
  if (EXPECT_UPLOAD_LIMIT_BYTES > 0) {
    await page.getByRole("button", { name: "新建会话" }).click();
    const oversizedUploadPath = path.join(evidenceDir, "oversized-upload.md");
    fs.writeFileSync(
      oversizedUploadPath,
      `# Oversized upload\n\n${"x".repeat(EXPECT_UPLOAD_LIMIT_BYTES + 1024)}`,
      "utf8",
    );
    await page.locator("#document-files").setInputFiles(oversizedUploadPath);
    await expect(page.getByText("oversized-upload.md")).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "12-oversized-upload-selected.png"),
    });

    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText(/HTTP 413|上传请求超过|413/)).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "13-oversized-upload-rejected.png"),
    });
    oversizedUploadRejected = true;
  }

  writeJson(path.join(evidenceDir, "assertions.json"), {
    artifactName,
    downloadedArtifact: "downloaded-report.html",
    deletedTaskFolderRemoved: true,
    historyRenameDeletePassed: true,
    includeEventsFalseReturnedEmptyEvents: true,
    modelsExposeAvailable: true,
    oversizedUploadRejected,
    runId,
    taskId,
    uniqueTitle,
    browserAuthSignals,
  });
});
