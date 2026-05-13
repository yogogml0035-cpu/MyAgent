import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for auto-title E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function visibleCharCount(value) {
  if (Intl.Segmenter) {
    return Array.from(new Intl.Segmenter("zh-CN", { granularity: "grapheme" }).segment(value))
      .length;
  }
  return Array.from(value).length;
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

test.use({ baseURL: BASE_URL });

test("first user message receives a model-generated history title", async ({ page, request }) => {
  test.setTimeout(120_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const uniqueMarker = randomUUID().slice(0, 8);
  const message = `请根据用户消息生成左侧历史会话名称，重点是自动标题验收 ${uniqueMarker}`;
  let taskId = "";
  let generatedTitle = "";

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-empty-history-and-composer.png"),
    });

    await page.locator("textarea.promptTextarea").fill(message);
    await expect(page.getByRole("button", { name: "发送" })).toBeEnabled();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-composer-ready-with-user-message.png"),
    });

    const messageResponsePromise = page.waitForResponse((response) => {
      const url = response.url();
      return (
        response.request().method() === "POST" &&
        url.startsWith(`${API_URL}/api/tasks/`) &&
        url.endsWith("/messages")
      );
    });
    await page.getByRole("button", { name: "发送" }).click();
    const messageResponse = await messageResponsePromise;
    expect(messageResponse.ok()).toBeTruthy();
    const taskState = await messageResponse.json();
    taskId = taskState.task_id;
    generatedTitle = String(taskState.title || "").trim();

    expect(taskId).toBeTruthy();
    expect(generatedTitle).toBeTruthy();
    expect(visibleCharCount(generatedTitle)).toBeLessThanOrEqual(10);

    await expect(page.getByRole("button", { name: generatedTitle, exact: true })).toBeVisible({
      timeout: 20_000,
    });
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-auto-title-visible-in-history.png"),
    });

    const summariesResponse = await request.get(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
    });
    expect(summariesResponse.ok()).toBeTruthy();
    const summaries = await summariesResponse.json();
    expect(
      summaries.some((summary) => summary.task_id === taskId && summary.title === generatedTitle),
    ).toBeTruthy();

    const taskResponse = await request.get(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
    });
    expect(taskResponse.ok()).toBeTruthy();
    const persistedTask = await taskResponse.json();
    expect(
      persistedTask.messages.some(
        (persistedMessage) => persistedMessage.role === "user" && persistedMessage.content === message,
      ),
    ).toBeTruthy();

    await page.getByRole("button", { name: generatedTitle, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: generatedTitle })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-auto-title-selected-history-row.png"),
    });

    fs.writeFileSync(
      path.join(evidenceDir, "assertions.json"),
      `${JSON.stringify(
        {
          generatedTitle,
          generatedTitleLength: visibleCharCount(generatedTitle),
          message,
          taskId,
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
