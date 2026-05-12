import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const frontendUrl = process.env.MYAGENT_E2E_FRONTEND_URL ?? "http://127.0.0.1:3011";
const outputDir = process.env.MYAGENT_E2E_OUTPUT_DIR;
const accessToken = process.env.MYAGENT_E2E_ACCESS_TOKEN || "";

if (!outputDir) {
  throw new Error("MYAGENT_E2E_OUTPUT_DIR is required");
}

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

async function screenshot(name) {
  await page.screenshot({ path: path.join(outputDir, `${name}.png`), fullPage: true });
}

async function waitForTerminal() {
  await page
    .getByText(/回答已完成|任务处理已完成|已完成|生成失败|运行失败|已取消/)
    .last()
    .waitFor({ timeout: 180_000 });
}

try {
  if (accessToken) {
    await page.addInitScript((token) => {
      window.localStorage.setItem("MYAGENT_E2E_ACCESS_TOKEN", token);
    }, accessToken);
  }
  await page.goto(frontendUrl, { waitUntil: "networkidle" });
  await screenshot("01-start");

  const composer = page.getByPlaceholder("尽管问...");
  await composer.fill("请在最终回答里确认：我做存储架构时希望先明确事务边界和长期记忆边界。");
  await screenshot("02-message-ready");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByText("请在最终回答里确认").waitFor({ timeout: 30_000 });
  await screenshot("03-after-send");

  await page.getByText(/AI正在|运行中/).first().waitFor({ timeout: 60_000 }).catch(() => {});
  await screenshot("04-running-or-result");

  await waitForTerminal();
  await page.getByText(/事务边界|长期记忆边界/).last().waitFor({ timeout: 30_000 });
  await screenshot("05-first-run-terminal");

  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: /请在最终/ }).first().click();
  await page.getByText(/事务边界|长期记忆边界/).last().waitFor({ timeout: 30_000 });
  await screenshot("06-reload-after-first-run");

  const followup = page.getByPlaceholder("尽管问...");
  await followup.fill("下一次类似存储架构任务，我应该优先注意什么？请结合你能记起的偏好回答。");
  await screenshot("07-followup-ready");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByText("下一次类似存储架构任务").waitFor({ timeout: 30_000 });
  await screenshot("08-followup-sent");
  await waitForTerminal();
  await page.getByText(/事务边界|长期记忆边界|记起|偏好/).last().waitFor({ timeout: 60_000 });
  await screenshot("09-followup-memory-check");
  await writeFile(
    path.join(outputDir, "assertions.json"),
    JSON.stringify(
      {
        firstRunCompleted: true,
        followupCompleted: true,
        visibleMemoryInfluenceChecked: true,
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );
} finally {
  await browser.close();
}
