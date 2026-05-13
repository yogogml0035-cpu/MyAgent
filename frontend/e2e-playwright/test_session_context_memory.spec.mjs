import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";
const POSTGRES_CONTAINER = process.env.MYAGENT_E2E_POSTGRES_CONTAINER || "PostgreSQL";
const POSTGRES_USER = process.env.MYAGENT_E2E_POSTGRES_USER || "postgres";
const POSTGRES_DB = process.env.MYAGENT_E2E_POSTGRES_DB || "myagent";
const DEFAULT_USER_ID = process.env.MYAGENT_DEFAULT_USER_ID || "local-user";
const BACKEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "backend");

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for session-context-memory E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function sqlString(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function runSql(sql) {
  return execFileSync(
    "docker",
    [
      "exec",
      "-i",
      POSTGRES_CONTAINER,
      "psql",
      "-t",
      "-A",
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
      encoding: "utf8",
    },
  ).trim();
}

async function cleanupTask(request, taskId) {
  if (!taskId) {
    return;
  }

  const taskResponse = await request.get(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  });
  if (!taskResponse.ok()) {
    return;
  }
  const task = await taskResponse.json();
  if (task.status === "running") {
    await request.post(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
      headers: authHeaders(),
    }).catch(() => {});
  }
  await request.delete(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  }).catch(() => {});
}

function seedLongTermMemoryAndRebuild(taskId) {
  const memoryId = randomUUID();
  const memoryText =
    "用户的稳定回答偏好：当用户要求复述记住的偏好或说明会怎么回答时，先给结论再给依据。";
  runSql(`
INSERT INTO long_term_memories (
  memory_id, user_id, memory_type, text, confidence,
  source_task_id, source_run_id, created_at, updated_at
)
VALUES (
  ${sqlString(memoryId)},
  ${sqlString(DEFAULT_USER_ID)},
  'preference',
  ${sqlString(memoryText)},
  0.95,
  ${sqlString(taskId)},
  'e2e-memory-seed',
  now(),
  now()
)
ON CONFLICT (memory_id) DO UPDATE
SET text = EXCLUDED.text,
    confidence = EXCLUDED.confidence,
    updated_at = EXCLUDED.updated_at;
`);

  execFileSync(
    "uv",
    ["run", "python", "-m", "app.memory_admin", "rebuild-qdrant", "--yes"],
    {
      cwd: BACKEND_ROOT,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      encoding: "utf8",
    },
  );
}

async function waitForTerminalState(page) {
  await page
    .getByText(/任务已完成|回答已完成|已完成|生成失败|运行失败|已取消/)
    .last()
    .waitFor({ timeout: 180_000 });
}

test.use({ baseURL: BASE_URL });

test("same-session context and long-term memory are recalled on the next turn", async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const marker = `CXT-${randomUUID().slice(0, 8)}`;
  let taskId = "";

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-empty-workspace.png"),
    });

    const firstPrompt = `请记住这个偏好标记 ${marker}：我喜欢你回答时先给结论，再给依据。先用一句话确认。`;
    const composer = page.getByPlaceholder("尽管问...");
    await composer.fill(firstPrompt);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-first-prompt-ready.png"),
    });

    const firstMessagePromise = page.waitForResponse((response) => {
      const url = response.url();
      return (
        response.request().method() === "POST" &&
        url.startsWith(`${API_URL}/api/tasks/`) &&
        url.endsWith("/messages")
      );
    });
    await page.getByRole("button", { name: "发送" }).click();
    const firstMessageResponse = await firstMessagePromise;
    expect(firstMessageResponse.ok()).toBeTruthy();
    const firstTaskState = await firstMessageResponse.json();
    taskId = firstTaskState.task_id;
    expect(taskId).toBeTruthy();

    await page.getByText(firstPrompt).waitFor({ timeout: 30_000 });
    await waitForTerminalState(page);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-first-turn-complete.png"),
    });

    seedLongTermMemoryAndRebuild(taskId);

    const followupPrompt = "我刚才问了什么？请复述你记住的偏好，并说明你会怎么回答。";
    await composer.fill(followupPrompt);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-followup-ready.png"),
    });

    const secondMessagePromise = page.waitForResponse((response) => {
      const url = response.url();
      return (
        response.request().method() === "POST" &&
        url.startsWith(`${API_URL}/api/tasks/`) &&
        url.endsWith("/messages")
      );
    });
    await page.getByRole("button", { name: "发送" }).click();
    const secondMessageResponse = await secondMessagePromise;
    expect(secondMessageResponse.ok()).toBeTruthy();

    await expect(page.getByText("已载入会话上下文").first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText("已载入长期记忆").first()).toBeVisible({ timeout: 45_000 });

    await page
      .locator(".liveStatusRow-details")
      .filter({ hasText: "已载入会话上下文" })
      .first()
      .locator("summary")
      .click();
    await page
      .locator(".liveStatusRow-details")
      .filter({ hasText: "已载入长期记忆" })
      .first()
      .locator("summary")
      .click();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "05-context-and-memory-logs-expanded.png"),
    });

    const assistantReplies = page.locator(".assistantMessageRow .chatMessage-assistant");
    await expect(assistantReplies.last()).toContainText(/刚才|记住|偏好/, { timeout: 120_000 });
    await expect(assistantReplies.last()).toContainText(/先给结论.*再给依据|先给结论，再给依据/, {
      timeout: 120_000,
    });
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "06-followup-answer-with-recall.png"),
    });

    fs.writeFileSync(
      path.join(evidenceDir, "assertions.json"),
      `${JSON.stringify(
        {
          taskId,
          marker,
          defaultUserId: DEFAULT_USER_ID,
          firstPrompt,
          followupPrompt,
          longTermMemoryLoaded: true,
          contextLoaded: true,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    await cleanupTask(request, taskId);
  }
});
