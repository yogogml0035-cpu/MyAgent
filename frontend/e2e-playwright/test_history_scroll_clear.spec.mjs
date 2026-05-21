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
    throw new Error(`${name} is required for history-scroll-clear E2E`);
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

function seedVisibleHistoryMessage(taskId, title, offsetSeconds) {
  runSql(`
UPDATE tasks
SET title = ${sqlString(title)},
    updated_at = NOW() - (${Number(offsetSeconds)} * INTERVAL '1 second')
WHERE task_id = ${sqlString(taskId)};

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, NULL, 'user', ${sqlString(title)}, NOW(), NULL);
`);
}

test.use({ baseURL: BASE_URL, viewport: { width: 1280, height: 720 } });

test("history sidebar scrolls and exposes a bottom clear-all action", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const runId = randomUUID().slice(0, 8);
  const seededTasks = [];

  try {
    for (let index = 0; index < 18; index++) {
      const createdResponse = await request.post(`${API_URL}/api/tasks`, {
        headers: authHeaders(),
        data: { model: "deepseek-v4-flash" },
      });
      expect(createdResponse.status()).toBe(201);
      const createdTask = await createdResponse.json();
      const title = `滚动会话-${runId}-${String(index + 1).padStart(2, "0")}`;
      seededTasks.push({ id: createdTask.task_id, title });
      seedVisibleHistoryMessage(createdTask.task_id, title, index);
    }

    await page.goto("/");
    const historyList = page.locator(".historyList");
    const clearButton = page.getByRole("button", { name: "清空所有会话" });

    await expect(historyList).toBeVisible();
    await expect(clearButton).toBeVisible();
    await expect(clearButton).toBeEnabled();
    await expect(page.getByRole("button", { name: seededTasks[0].title, exact: true })).toBeVisible();

    const scrollMetrics = await historyList.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
    }));
    expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);

    const scrolledTop = await historyList.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      return element.scrollTop;
    });
    expect(scrolledTop).toBeGreaterThan(0);
    await expect(clearButton).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-history-list-scrolled-bottom.png"),
    });
  } finally {
    for (const task of seededTasks) {
      await request.delete(`${API_URL}/api/tasks/${task.id}`, {
        headers: authHeaders(),
      });
    }
  }
});
