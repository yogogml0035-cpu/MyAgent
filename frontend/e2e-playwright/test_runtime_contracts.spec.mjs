import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const API_URL = process.env.MYAGENT_E2E_API_URL || "http://127.0.0.1:8001";
const TASK_ROOT = process.env.MYAGENT_E2E_TASK_ROOT;
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;

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

function writeEvents(taskDir, taskId, runId, timestamp) {
  const eventsDir = path.join(taskDir, "logs");
  fs.mkdirSync(eventsDir, { recursive: true });
  const events = [
    {
      id: randomUUID().replaceAll("-", ""),
      session_id: taskId,
      seq: 0,
      type: "task_created",
      message: "任务目录已创建。",
      created_at: timestamp,
      payload: { model: "deepseek:deepseek-chat" },
      run_id: null,
      level: null,
      idempotency_key: null,
    },
    {
      id: randomUUID().replaceAll("-", ""),
      session_id: taskId,
      seq: 1,
      type: "task_completed",
      message: "任务已完成。",
      created_at: timestamp,
      payload: { previous_status: "running" },
      run_id: runId,
      level: "success",
      idempotency_key: null,
    },
    {
      id: randomUUID().replaceAll("-", ""),
      session_id: taskId,
      seq: 2,
      type: "final_answer",
      message: "Final answer generated",
      created_at: timestamp,
      payload: { content: "E2E 报告已生成，可打开或下载。" },
      run_id: runId,
      level: "success",
      idempotency_key: null,
    },
  ];
  fs.writeFileSync(
    path.join(eventsDir, "events.jsonl"),
    `${events.map((event) => JSON.stringify(event)).join("\n")}\n`,
    "utf8",
  );
}

function seedCompletedArtifactTask(taskRoot, taskId) {
  const timestamp = nowIso();
  const runId = `run-e2e-${Date.now()}`;
  const artifactName = "report.html";
  const taskDir = path.join(taskRoot, taskId);
  const artifactDir = path.join(taskDir, "artifacts", "runs", runId);
  const statePath = path.join(taskDir, "state.json");
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(
    path.join(artifactDir, artifactName),
    [
      "<!doctype html>",
      "<html><head><meta charset=\"utf-8\"><title>E2E Report</title></head>",
      "<body><h1>E2E 运行契约报告</h1><p>产物打开与下载链路可用。</p></body></html>",
    ].join(""),
    "utf8",
  );

  Object.assign(state, {
    status: "complete",
    model: "deepseek:deepseek-chat",
    updated_at: timestamp,
    active_run_id: null,
    run_count: 1,
    upload_count: 0,
    error: null,
    needs_input: null,
    messages: [
      {
        role: "user",
        content: "E2E 运行契约验收",
        created_at: timestamp,
        run_id: runId,
        level: null,
      },
      {
        role: "assistant",
        content: "E2E 报告已生成，可打开或下载。",
        created_at: timestamp,
        run_id: runId,
        level: null,
      },
    ],
    runs: [
      {
        id: runId,
        status: "complete",
        message: "E2E 运行契约验收",
        model: "deepseek:deepseek-chat",
        started_at: timestamp,
        completed_at: timestamp,
        error: null,
        needs_input: null,
        artifact_base_path: `artifacts/runs/${runId}`,
        artifact_names: [artifactName],
      },
    ],
    events: [],
    artifacts: [],
  });

  writeJson(statePath, state);
  writeEvents(taskDir, taskId, runId, timestamp);
  return { artifactName, runId };
}

test.use({ acceptDownloads: true, baseURL: BASE_URL });

test("runtime task contracts expose artifacts and upload errors in the browser", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);

  const taskRoot = requirePath(TASK_ROOT, "MYAGENT_E2E_TASK_ROOT");
  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });

  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    data: { model: "deepseek:deepseek-chat" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  const { artifactName, runId } = seedCompletedArtifactTask(taskRoot, taskId);

  const lightweightResponse = await request.get(`${API_URL}/api/tasks/${taskId}?include_events=false`);
  expect(lightweightResponse.ok()).toBeTruthy();
  const lightweightTask = await lightweightResponse.json();
  expect(lightweightTask.events).toEqual([]);
  expect(lightweightTask.artifacts.some((artifact) => artifact.name === artifactName)).toBeTruthy();

  const modelsResponse = await request.get(`${API_URL}/api/models`);
  expect(modelsResponse.ok()).toBeTruthy();
  const models = await modelsResponse.json();
  expect(models.some((model) => typeof model.available === "boolean")).toBeTruthy();

  await page.goto("/");
  await expect(page.getByRole("button", { name: /新建会话/ })).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "01-history-loaded.png") });

  await page.getByRole("button", { name: /E2E/ }).first().click();
  await expect(page.getByText(artifactName)).toBeVisible();
  await expect(page.getByText("AI回复")).toBeVisible();
  await expect(page.getByText("已完成").first()).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "02-artifact-card.png") });

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "打开" }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded");
  await expect(popup.locator("body")).toContainText("E2E 运行契约报告");
  await popup.screenshot({ fullPage: true, path: path.join(evidenceDir, "03-opened-report.png") });
  await popup.close();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(artifactName);
  await download.saveAs(path.join(evidenceDir, "downloaded-report.html"));
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "04-download-finished.png") });

  await page.getByRole("button", { name: "新建会话" }).click();
  const invalidJsonPath = path.join(evidenceDir, "invalid-upload.json");
  fs.writeFileSync(invalidJsonPath, "{ invalid json", "utf8");
  await page.locator("#document-files").setInputFiles(invalidJsonPath);
  await expect(page.getByText("invalid-upload.json")).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "05-invalid-json-selected.png") });

  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/HTTP 400|内容不是合法 JSON|JSON 文件/)).toBeVisible();
  await page.screenshot({ fullPage: true, path: path.join(evidenceDir, "06-invalid-json-error.png") });

  writeJson(path.join(evidenceDir, "assertions.json"), {
    artifactName,
    downloadedArtifact: "downloaded-report.html",
    includeEventsFalseReturnedEmptyEvents: true,
    modelsExposeAvailable: true,
    runId,
    taskId,
  });
});
