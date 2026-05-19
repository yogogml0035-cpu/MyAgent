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
    throw new Error(`${name} is required for history-menu E2E`);
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

function seedVisibleHistoryMessage(taskId, title) {
  runSql(`
UPDATE tasks
SET title = ${sqlString(title)},
    updated_at = NOW()
WHERE task_id = ${sqlString(taskId)};

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, NULL, 'user', ${sqlString(title)}, NOW(), NULL);
`);
}

test.use({ baseURL: BASE_URL });

test("history menu trigger opens without the circular selected border", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const title = `历史菜单验收-${randomUUID().slice(0, 8)}`;
  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek-v4-flash" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  seedVisibleHistoryMessage(taskId, title);

  try {
    await page.goto("/");
    const historyItem = page.getByRole("button", { name: title, exact: true });
    await expect(historyItem).toBeVisible();

    const historyShell = historyItem.locator("xpath=ancestor::*[contains(@class, 'historyItemShell')][1]");
    const menuButton = historyShell.getByRole("button", { name: new RegExp(`打开 ${title} 的会话菜单`) });

    await historyShell.hover();
    await expect(menuButton).toBeVisible();
    await expect(menuButton).toHaveCSS("border-top-width", "0px");
    await expect(menuButton).toHaveCSS("outline-style", "none");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-history-menu-trigger-hover.png"),
    });

    await menuButton.click();
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(menuButton).toHaveCSS("border-top-width", "0px");
    await expect(menuButton).toHaveCSS("outline-style", "none");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-history-menu-open-no-ring.png"),
    });
  } finally {
    await request.delete(`${API_URL}/api/tasks/${taskId}`, {
      headers: authHeaders(),
    });
  }
});
