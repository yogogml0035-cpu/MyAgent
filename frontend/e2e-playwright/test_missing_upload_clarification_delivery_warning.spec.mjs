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

const INTERNAL_DELIVERY_FIELDS = [
  "reason",
  "repair_hint",
  "missing_artifact_names",
  "missing_deliverables",
  "requested_deliverable_types",
  "promoted_artifacts",
];

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for missing-upload-delivery-warning E2E`);
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
  ${sqlJson(event.payload ?? {})},
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

function writeUploadFixture(evidenceDir) {
  const fixtureDir = path.join(evidenceDir, "fixtures");
  fs.mkdirSync(fixtureDir, { recursive: true });
  const fixturePath = path.join(fixtureDir, "clarification-brief.txt");
  fs.writeFileSync(
    fixturePath,
    [
      "项目背景：本文件用于缺上传澄清后的继续处理验收。",
      "需要输出：请延续上一轮需求，总结内容并生成 Word。",
      "截图要求：不要包含任何客户资料或密钥。",
    ].join("\n"),
    "utf8",
  );
  return fixturePath;
}

function seedContinuationDocxRun(taskRoot, taskId, userMessage) {
  const timestamp = nowIso();
  const runId = `run-missing-upload-e2e-${Date.now()}`;
  const artifactName = "上一轮需求总结.docx";
  const taskDir = ensureTaskWorkspace(taskRoot, taskId);
  const artifactDir = path.join(taskDir, "artifacts", "runs", runId);
  const assistantMessage =
    "已继续上一轮总结并生成 Word 的需求。请使用下方下载卡片获取 Word 文件。";

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(
    path.join(artifactDir, artifactName),
    Buffer.from(`DOCX-STUB:${artifactName}:${runId}`),
  );

  runSql(`
UPDATE tasks
SET status = 'complete',
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
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(userMessage)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(assistantMessage)}, ${sqlString(timestamp)}, NULL);

${appendEventSql(taskId, {
  type: "context_loaded",
  message: "已载入会话上下文。",
  createdAt: timestamp,
  runId,
  level: "info",
  payload: {
    message_count: 2,
    has_previous_user_intent: true,
    previous_user_intent: "总结内容并生成 Word",
  },
})}

${appendEventSql(taskId, {
  type: "task_completed",
  message: "任务已完成。",
  createdAt: timestamp,
  runId,
  level: "success",
  payload: {
    previous_status: "running",
    live: {
      schema_version: 1,
      kind: "status",
      stage: "completed",
      display_text: "任务已完成",
      diagnostic_label: "runner.terminal",
      parameter_items: [{ key: "previous_status", value: "running" }],
      result_status: "success",
    },
  },
})}

${appendEventSql(taskId, {
  type: "final_answer",
  message: "Final answer generated",
  createdAt: timestamp,
  runId,
  level: "success",
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
})}
`);

  return { artifactName, runId };
}

function seedMissingArtifactTask(taskId, title) {
  const timestamp = nowIso();
  const runId = `run-missing-artifact-e2e-${Date.now()}`;
  const message = "文件未成功生成或未能登记为下载文件。请重新生成交付文件后再试。";
  const needsInput = {
    message,
    action_label: "重新生成文件",
    reason: "artifact_missing",
    repair_hint: "internal repair hint",
    missing_artifact_names: ["承诺交付.docx"],
    missing_deliverables: ["Word"],
    requested_deliverable_types: ["word"],
    promoted_artifacts: [],
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
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES
  (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(timestamp)}, NULL),
  (${sqlString(taskId)}, ${sqlString(runId)}, 'assistant', ${sqlString(message)}, ${sqlString(timestamp)}, 'warning');

${appendEventSql(taskId, {
  type: "needs_input",
  message,
  createdAt: timestamp,
  runId,
  level: "warning",
  payload: {
    message,
    action_label: "重新生成文件",
    live: {
      schema_version: 1,
      kind: "status",
      stage: "needs_input",
      display_text: "文件未成功生成或未能登记为下载文件",
      diagnostic_label: "runner.artifact_validation",
      parameter_items: [],
      result_status: "warning",
    },
  },
})}
`);

  return { runId };
}

function seedRunningTask(taskId, title) {
  const startedAt = nowIso();
  const runId = `run-running-clear-e2e-${Date.now()}`;

  runSql(`
UPDATE tasks
SET status = 'running',
    title = ${sqlString(title)},
    model = 'deepseek-v4-flash',
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
  'deepseek-v4-flash',
  ${sqlString(startedAt)},
  NULL,
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(startedAt)}, NULL);

${appendEventSql(taskId, {
  type: "status",
  message: "任务正在运行。",
  createdAt: startedAt,
  runId,
  level: "info",
  payload: {
    live: {
      schema_version: 1,
      kind: "status",
      stage: "running",
      display_text: "任务正在运行",
      diagnostic_label: "runner.terminal",
      parameter_items: [],
    },
  },
})}
`);

  return { runId };
}

function retireRunningTask(taskId, runId) {
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

async function createEmptyTask(request) {
  const created = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek-v4-flash" },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).task_id;
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
    // The UI clear-all path may have already deleted this task.
  }
}

async function expectNoVisibleInternalFields(page) {
  const visibleText = await page.locator("body").innerText();
  for (const field of INTERNAL_DELIVERY_FIELDS) {
    expect(visibleText).not.toContain(field);
  }
}

test.use({ acceptDownloads: true, baseURL: BASE_URL, viewport: { width: 1366, height: 820 } });

test("missing upload clarification, file delivery, and clear-all warnings stay user-safe", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);

  const taskRoot = requirePath(TASK_ROOT, "MYAGENT_E2E_TASK_ROOT");
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });
  const uploadFixture = writeUploadFixture(evidenceDir);
  const uploadFileName = path.basename(uploadFixture);
  const runMarker = randomUUID().slice(0, 8);
  const createdTaskIds = new Set();
  const consoleErrors = [];
  let missingUploadTaskId = "";
  let runningTaskId = "";
  let runningRunId = "";

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-empty-workspace.png"),
    });

    await page.locator("textarea.promptTextarea").fill("总结内容并生成 Word");
    const missingUploadResponsePromise = page.waitForResponse((response) => {
      const url = response.url();
      return (
        response.request().method() === "POST" &&
        url.startsWith(`${API_URL}/api/tasks/`) &&
        url.endsWith("/messages")
      );
    });
    await page.getByRole("button", { name: "发送" }).click();
    const missingUploadResponse = await missingUploadResponsePromise;
    expect(missingUploadResponse.ok()).toBeTruthy();
    const missingUploadState = await missingUploadResponse.json();
    missingUploadTaskId = missingUploadState.task_id;
    createdTaskIds.add(missingUploadTaskId);

    await expect(page.getByText(/你是不是忘记上传文件了/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/上传后我继续帮你生成 Word/)).toBeVisible();
    await expect(page.getByText("配置提醒")).toHaveCount(0);
    await expect(page.getByText("等待补充输入")).toHaveCount(0);
    await expect(page.getByText("reason")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-missing-upload-clarification.png"),
    });

    let capturedFollowUp = "";
    await page.route(/\/api\/tasks\/[^/]+\/messages$/, async (route) => {
      const routeUrl = new URL(route.request().url());
      const routeTaskId = decodeURIComponent(routeUrl.pathname.split("/")[3] || "");
      if (routeTaskId !== missingUploadTaskId) {
        await route.continue();
        return;
      }

      const body = JSON.parse(route.request().postData() || "{}");
      capturedFollowUp = String(body.message || body.content || "");
      expect(capturedFollowUp).toContain("继续上一轮需求");
      expect(capturedFollowUp).toContain("总结内容并生成 Word");
      expect(capturedFollowUp).toContain(uploadFileName);

      const seeded = seedContinuationDocxRun(taskRoot, routeTaskId, capturedFollowUp);
      const stateResponse = await request.get(
        `${API_URL}/api/tasks/${encodeURIComponent(routeTaskId)}`,
        { headers: authHeaders() },
      );
      expect(stateResponse.ok()).toBeTruthy();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(await stateResponse.json()),
      });
      fs.writeFileSync(
        path.join(evidenceDir, "file-only-follow-up.json"),
        `${JSON.stringify({ message: capturedFollowUp, ...seeded }, null, 2)}\n`,
        "utf8",
      );
    });

    await page.locator("#document-files").setInputFiles(uploadFixture);
    await expect(page.getByTestId("selected-file-card")).toContainText(uploadFileName);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-file-only-selected.png"),
    });

    await expect(page.getByRole("button", { name: "发送" })).toBeEnabled();
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.locator(".userMessageFileList", { hasText: uploadFileName })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("已继续上一轮总结并生成 Word 的需求")).toBeVisible();
    await expect(page.getByText("上一轮需求总结.docx", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "下载 上一轮需求总结.docx" })).toBeVisible();
    await expect(page.getByText("文件未成功生成或未能登记为下载文件")).toHaveCount(0);
    await expect(page.getByText("配置提醒")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-file-only-continued-docx-card.png"),
    });

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载 上一轮需求总结.docx" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("上一轮需求总结.docx");
    await download.saveAs(path.join(evidenceDir, download.suggestedFilename()));
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "05-docx-download-finished.png"),
    });

    const missingArtifactTaskId = await createEmptyTask(request);
    createdTaskIds.add(missingArtifactTaskId);
    const missingArtifactTitle = `友好交付失败-${runMarker}`;
    const missingArtifactSeed = seedMissingArtifactTask(missingArtifactTaskId, missingArtifactTitle);

    await page.goto("/");
    await expect(page.getByRole("button", { name: missingArtifactTitle, exact: true })).toBeVisible();
    await page.getByRole("button", { name: missingArtifactTitle, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: missingArtifactTitle })).toBeVisible();
    await expect(page.getByText("文件未成功生成或未能登记为下载文件").first()).toBeVisible();
    await expect(page.getByText("重新生成文件").first()).toBeVisible();
    await expect(page.getByText("配置提醒")).toHaveCount(0);
    await expectNoVisibleInternalFields(page);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "06-friendly-missing-artifact.png"),
    });

    page.once("dialog", async (dialog) => {
      expect(dialog.message()).toContain("清空所有历史会话");
      await dialog.accept();
    });
    await page.getByRole("button", { name: "清空所有会话" }).click();
    await expect(page.getByRole("button", { name: missingArtifactTitle, exact: true })).toHaveCount(0);
    const clearedResponse = await request.get(
      `${API_URL}/api/tasks/${encodeURIComponent(missingArtifactTaskId)}`,
      { headers: authHeaders() },
    );
    expect(clearedResponse.status()).toBe(404);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "07-needs-input-cleared.png"),
    });

    runningTaskId = await createEmptyTask(request);
    createdTaskIds.add(runningTaskId);
    const runningTitle = `运行中阻止清空-${runMarker}`;
    const runningSeed = seedRunningTask(runningTaskId, runningTitle);
    runningRunId = runningSeed.runId;

    await page.goto("/");
    await expect(page.getByRole("button", { name: runningTitle, exact: true })).toBeVisible();
    let unexpectedDialog = false;
    page.once("dialog", async (dialog) => {
      unexpectedDialog = true;
      await dialog.dismiss();
    });
    await page.getByRole("button", { name: "清空所有会话" }).click();
    await expect(page.getByText("有任务正在运行，完成或停止后再清空历史会话。")).toBeVisible();
    expect(unexpectedDialog).toBe(false);
    await expect(page.getByRole("button", { name: runningTitle, exact: true })).toBeVisible();
    const runningResponse = await request.get(
      `${API_URL}/api/tasks/${encodeURIComponent(runningTaskId)}`,
      { headers: authHeaders() },
    );
    expect(runningResponse.ok()).toBeTruthy();
    expect((await runningResponse.json()).status).toBe("running");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "08-running-blocks-clear-all.png"),
    });

    expect(consoleErrors).toEqual([]);
    fs.writeFileSync(
      path.join(evidenceDir, "assertions.json"),
      `${JSON.stringify(
        {
          consoleErrors,
          capturedFollowUp,
          missingArtifactRunId: missingArtifactSeed.runId,
          runningRunId,
          tasks: {
            missingUploadTaskId,
            runningTaskId,
          },
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    if (runningTaskId && runningRunId) {
      retireRunningTask(runningTaskId, runningRunId);
    }
    for (const taskId of createdTaskIds) {
      await deleteTaskIfPresent(request, taskId);
    }
  }
});
