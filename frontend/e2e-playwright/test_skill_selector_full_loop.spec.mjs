import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;
const ACCESS_TOKEN = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";
const USER_MESSAGE = "搜索今天的 AI 新闻";
const SKILL_NAME = "web-research";
const VISIBLE_SKILL_REF = "[$web-research]";

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for skill selector full-loop E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
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

  for (let attempt = 0; attempt < 6; attempt += 1) {
    const deleteResponse = await request.delete(
      `${API_URL}/api/tasks/${encodeURIComponent(taskId)}`,
      { headers: authHeaders() },
    ).catch(() => null);
    if (deleteResponse?.ok()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function userMessages(taskState) {
  return Array.isArray(taskState?.messages)
    ? taskState.messages.filter((message) => message?.role === "user")
    : [];
}

function hasVisibleSkillMessage(taskState) {
  return userMessages(taskState).some((message) => {
    const content = String(message?.content || "");
    return content.includes(VISIBLE_SKILL_REF) && content.includes(USER_MESSAGE);
  });
}

async function expectSkillPickerOptions(page) {
  const textarea = page.locator("textarea.promptTextarea");
  await expect(textarea).toBeVisible();
  await textarea.fill("");
  await textarea.focus();
  await textarea.type("/");

  const picker = page.getByRole("listbox", { name: "Skill 选择器" });
  await expect(picker).toBeVisible();
  await expect(picker.getByRole("option", { name: /code-review/ })).toBeVisible();
  await expect(picker.getByRole("option", { name: /web-research/ })).toBeVisible();
  return { picker, textarea };
}

test.use({ baseURL: BASE_URL });

test("real services preserve selected skill through send and history reload", async ({
  browser,
  page,
  request,
}) => {
  test.setTimeout(180_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const consoleErrors = [];
  const messagePayloads = [];
  let taskId = "";
  const marker = randomUUID().slice(0, 8);
  const historyTitle = `Skill闭环${marker}`;

  const recordConsoleError = (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  };
  page.on("console", recordConsoleError);
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });
  page.on("request", (browserRequest) => {
    const url = browserRequest.url();
    if (
      browserRequest.method() !== "POST" ||
      !url.startsWith(`${API_URL}/api/tasks/`) ||
      !url.endsWith("/messages")
    ) {
      return;
    }

    const rawPayload = browserRequest.postData() || "{}";
    try {
      messagePayloads.push(JSON.parse(rawPayload));
    } catch {
      messagePayloads.push({ unparsable: rawPayload });
    }
  });

  try {
    const skillsResponse = await request.get(`${API_URL}/api/skills`, {
      headers: authHeaders(),
    });
    expect(skillsResponse.ok()).toBeTruthy();
    const skillNames = (await skillsResponse.json()).map((skill) => skill.name);
    expect(skillNames).toContain("code-review");
    expect(skillNames).toContain(SKILL_NAME);

    const modelsResponse = await request.get(`${API_URL}/api/models`, {
      headers: authHeaders(),
    });
    expect(modelsResponse.ok()).toBeTruthy();
    const models = await modelsResponse.json();
    expect(models.some((model) => model.id === "deepseek-v4-flash" && model.available)).toBeTruthy();

    await page.goto("/");
    await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();

    const { picker, textarea } = await expectSkillPickerOptions(page);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-desktop-skill-picker.png"),
    });

    await picker.getByRole("option", { name: /web-research/ }).click();
    await expect(page.getByRole("button", { name: "移除 web-research skill" })).toBeVisible();
    await textarea.type(USER_MESSAGE);
    await expect(textarea).toHaveValue(USER_MESSAGE);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-desktop-before-send.png"),
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

    expect(taskId).toBeTruthy();
    expect(messagePayloads).toHaveLength(1);
    expect(messagePayloads[0]).toMatchObject({
      message: USER_MESSAGE,
      model: "deepseek-v4-flash",
      skills: [SKILL_NAME],
    });
    expect(hasVisibleSkillMessage(taskState)).toBeTruthy();

    const userMessage = page.locator(".chatMessage-user", {
      hasText: USER_MESSAGE,
    }).filter({ hasText: VISIBLE_SKILL_REF });
    await expect(userMessage).toBeVisible({ timeout: 20_000 });
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-desktop-message-sent.png"),
    });

    const persistedResponse = await request.get(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
    });
    expect(persistedResponse.ok()).toBeTruthy();
    expect(hasVisibleSkillMessage(await persistedResponse.json())).toBeTruthy();

    const renameResponse = await request.patch(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
      headers: authHeaders(),
      data: { title: historyTitle },
    });
    expect(renameResponse.ok()).toBeTruthy();

    await page.reload();
    await expect(page.getByRole("button", { name: historyTitle, exact: true })).toBeVisible({
      timeout: 20_000,
    });
    await page.getByRole("button", { name: historyTitle, exact: true }).click();
    await expect(page.locator(".chatMessage-user", { hasText: USER_MESSAGE })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.locator(".chatMessage-user", { hasText: VISIBLE_SKILL_REF })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-reloaded-history-message.png"),
    });

    const mobilePage = await browser.newPage({ viewport: { width: 390, height: 740 } });
    mobilePage.on("console", recordConsoleError);
    mobilePage.on("pageerror", (error) => {
      consoleErrors.push(error.message);
    });
    try {
      await mobilePage.goto(BASE_URL);
      await mobilePage.getByRole("button", { name: /新建会话/ }).click();
      await expectSkillPickerOptions(mobilePage);
      await mobilePage.screenshot({
        fullPage: true,
        path: path.join(evidenceDir, "05-mobile-skill-picker.png"),
      });
    } finally {
      await mobilePage.close();
    }

    fs.writeFileSync(
      path.join(evidenceDir, "assertions.json"),
      `${JSON.stringify(
        {
          historyTitle,
          messagePayload: messagePayloads[0],
          persistedVisibleSkillRef: true,
          reloadedHistoryVisible: true,
          skillName: SKILL_NAME,
          taskId,
          userMessage: USER_MESSAGE,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );

    expect(consoleErrors).toEqual([]);
  } finally {
    await cleanupTask(request, taskId);
  }
});
