import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for event-cursor E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

test.use({ baseURL: BASE_URL });

test("events endpoint replays the ordered stream when the cursor is unknown", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek:deepseek-chat" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-page-ready-before-cursor-recovery.png"),
    });

    const fullEvents = await page.evaluate(
      async ({ apiUrl, taskId: browserTaskId, token }) => {
        const headers = token ? { "X-MyAgent-Token": token } : {};
        const response = await fetch(
          `${apiUrl}/api/tasks/${encodeURIComponent(browserTaskId)}/events?after_id=missing-event-id`,
          { headers },
        );
        if (!response.ok) {
          throw new Error(`events request failed: ${response.status}`);
        }
        return response.json();
      },
      { apiUrl: API_URL, taskId, token: ACCESS_TOKEN },
    );
    expect(fullEvents.map((event) => event.seq)).toEqual([1]);
    expect(fullEvents[0].type).toBe("task_created");

    await page.locator("textarea.promptTextarea").fill("事件游标恢复验收");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-composer-ready-after-cursor-recovery.png"),
    });

    fs.writeFileSync(
      path.join(evidenceDir, "assertions.json"),
      `${JSON.stringify(
        {
          recoveredEventSeqs: fullEvents.map((event) => event.seq),
          recoveredEventTypes: fullEvents.map((event) => event.type),
          taskId,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  } finally {
    await request.delete(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
    });
  }
});
