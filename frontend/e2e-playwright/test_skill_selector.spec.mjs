import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for skill selector E2E`);
  }
  return value;
}

function skillPayload() {
  return [
    {
      name: "code-review",
      description: "Review code changes for correctness and regressions.",
    },
    {
      name: "web-research",
      description: "Search current web sources and cite findings.",
    },
  ];
}

function modelPayload() {
  return [
    {
      id: "deepseek-v4-flash",
      label: "DeepSeek V4 Flash",
      description: "默认快速模型",
      available: true,
    },
    {
      id: "deepseek-v4-flash-thinking",
      label: "DeepSeek V4 Flash Thinking",
      description: "深度思考模型",
      available: true,
    },
  ];
}

test.use({ baseURL: BASE_URL });

test("composer slash skill selector creates and removes chips without sending", async ({
  page,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const consoleErrors = [];
  const messageRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });
  await page.route(/\/api\/models$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(modelPayload()),
    });
  });
  await page.route(/\/api\/tasks$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route(/\/api\/skills$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(skillPayload()),
    });
  });
  await page.route(/\/api\/tasks\/[^/]+\/messages$/, async (route) => {
    messageRequests.push(route.request().postData() || "");
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "skill selector test should not send" }),
    });
  });

  await page.goto("/");
  const textarea = page.locator("textarea.promptTextarea");
  await expect(textarea).toBeVisible();
  await textarea.fill("/");

  const picker = page.getByRole("listbox", { name: "Skill 选择器" });
  await expect(picker).toBeVisible();
  await expect(picker.getByRole("option", { name: /code-review/ })).toBeVisible();
  await expect(picker.getByRole("option", { name: /web-research/ })).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: path.join(evidenceDir, "01-slash-picker-open.png"),
  });

  await textarea.fill("/web");
  await expect(picker.getByRole("option", { name: /web-research/ })).toBeVisible();
  await expect(picker.getByRole("option", { name: /code-review/ })).toHaveCount(0);

  await textarea.fill("/code");
  await expect(picker.getByRole("option", { name: /code-review/ })).toBeVisible();
  await expect(picker.getByRole("option", { name: /web-research/ })).toHaveCount(0);

  await textarea.fill("/missing");
  await expect(picker.getByText("没有匹配的 skill")).toBeVisible();
  await expect(textarea).toHaveValue("/missing");

  await textarea.press("Escape");
  await expect(picker).toHaveCount(0);
  await expect(textarea).toHaveValue("/missing");

  await textarea.fill("/");
  await expect(picker).toBeVisible();
  await page.mouse.click(520, 120);
  await expect(picker).toHaveCount(0);
  await expect(textarea).toHaveValue("/");

  await textarea.fill("/web");
  await picker.getByRole("option", { name: /web-research/ }).click();
  await expect(page.getByTestId("selected-skill-shelf")).toBeVisible();
  const chip = page.getByRole("button", { name: "移除 web-research skill" });
  await expect(chip).toBeVisible();
  await expect(textarea).toHaveValue("");
  await expect(textarea).toBeFocused();
  await page.screenshot({
    fullPage: true,
    path: path.join(evidenceDir, "02-web-research-chip.png"),
  });

  await textarea.type("继续写需求");
  await expect(textarea).toHaveValue("继续写需求");
  await chip.click();
  await expect(chip).toHaveCount(0);
  await expect(textarea).toHaveValue("继续写需求");
  await page.screenshot({
    fullPage: true,
    path: path.join(evidenceDir, "03-chip-removed.png"),
  });

  await textarea.fill("/");
  await expect(picker).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("selected-skill-shelf")).toBeVisible();
  await expect(textarea).toBeFocused();

  expect(messageRequests).toHaveLength(0);
  expect(consoleErrors).toEqual([]);
});
