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
    throw new Error(`${name} is required for multi-session thinking audit E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function nowIso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
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
  ${sqlString(randomUUID().replaceAll("-", ""))},
  ${sqlString(taskId)},
  latest_event_seq,
  ${sqlString(event.type)},
  ${sqlString(event.message)},
  ${sqlString(event.createdAt)},
  ${sqlJson(event.payload)},
  ${event.runId ? sqlString(event.runId) : "NULL"},
  ${event.level ? sqlString(event.level) : "NULL"},
  NULL
FROM next_seq;
`;
}

function seedVisibleIdleTask(taskId, title, userMessage, model = "deepseek-v4-flash-thinking") {
  const createdAt = nowIso();
  runSql(`
UPDATE tasks
SET title = ${sqlString(title)},
    model = ${sqlString(model)},
    status = 'idle',
    updated_at = ${sqlString(createdAt)},
    error = NULL,
    needs_input = NULL,
    active_run_id = NULL
WHERE task_id = ${sqlString(taskId)};

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, NULL, 'user', ${sqlString(userMessage)}, ${sqlString(createdAt)}, NULL);
`);
}

function seedRunningThinkingTask(taskId, options) {
  const startedAt = nowIso();
  const updatedAt = nowIso(4500);
  const runId = options.runId;
  const toolCallId = options.toolCallId;
  const answerPreview = options.answerPreview;
  const reasoningContent = options.reasoningContent;
  const searchQuery = options.searchQuery;
  const toolLabel = options.toolLabel || "联网搜索";
  const toolName = options.toolName || "searxng_search";
  const toolResultContent = options.toolResultContent;
  const userMessage = options.userMessage;
  const model = options.model || "deepseek-v4-flash-thinking";

  const eventSeeds = [
    {
      type: "assistant_thinking_delta",
      message: "Reasoning chunk received",
      createdAt: nowIso(600),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 1,
        content: reasoningContent,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "think",
          stage: "thinking",
          display_text: "AI正在思考...",
          diagnostic_label: "model.reasoning_content",
          parameter_items: [],
        },
      },
    },
    {
      type: "tool_call",
      message: `Tool call: ${toolName}`,
      createdAt: nowIso(1200),
      level: "info",
      payload: {
        id: toolCallId,
        name: toolName,
        args: { query: searchQuery, max_results: 2, topic: "general" },
        raw_args: JSON.stringify({ query: searchQuery, max_results: 2, topic: "general" }),
        partial: false,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "using_tool",
          tool_name: toolName,
          tool_label: toolLabel,
          tool_call_id: toolCallId,
          parameter_items: [
            { key: "query", value: searchQuery },
            { key: "max_results", value: 2 },
          ],
        },
      },
    },
    {
      type: "tool_result",
      message: `Tool result: ${toolName}`,
      createdAt: nowIso(2100),
      level: "success",
      payload: {
        name: toolName,
        status: "success",
        content: toolResultContent,
        live: {
          schema_version: 1,
          kind: "tool_result",
          stage: "completed",
          tool_name: toolName,
          tool_label: toolLabel,
          tool_call_id: toolCallId,
          result_status: "success",
          result_count: 1,
          parameter_items: [],
        },
      },
    },
    {
      type: "assistant_answer_delta",
      message: "Answer stream chunk received",
      createdAt: nowIso(3200),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 1,
        content: answerPreview,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "answer_status",
          stage: "generating_answer",
          display_text: "AI正在生成结果",
          diagnostic_label: "model.output_text",
          parameter_items: [],
        },
      },
    },
    {
      type: "status_update",
      message: "State update: answer",
      createdAt: nowIso(3900),
      level: "info",
      payload: {
        node: "answer",
        live: {
          schema_version: 1,
          kind: "status",
          stage: "generating_answer",
          display_text: "模型输出已完成",
          diagnostic_label: "answer",
          parameter_items: [],
        },
      },
    },
  ];

  runSql(`
UPDATE tasks
SET status = 'running',
    title = ${sqlString(options.title)},
    model = ${sqlString(model)},
    updated_at = ${sqlString(updatedAt)},
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
  ${sqlString(userMessage)},
  ${sqlString(model)},
  ${sqlString(startedAt)},
  NULL,
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(userMessage)}, ${sqlString(startedAt)}, NULL);

${eventSeeds.map((event) => appendEventSql(taskId, { ...event, runId })).join("\n")}
`);

  return {
    answerPreview,
    reasoningContent,
    runId,
    taskId,
    title: options.title,
    toolCallId,
    toolName,
  };
}

function markTaskComplete(taskId, runId) {
  const completedAt = nowIso();
  runSql(`
UPDATE tasks
SET status = 'complete',
    active_run_id = NULL,
    updated_at = ${sqlString(completedAt)},
    error = NULL,
    needs_input = NULL
WHERE task_id = ${sqlString(taskId)};

UPDATE runs
SET status = 'complete',
    completed_at = ${sqlString(completedAt)},
    error = NULL,
    needs_input = NULL
WHERE task_id = ${sqlString(taskId)}
  AND id = ${sqlString(runId)};
`);
}

async function deleteTaskIfPresent(request, taskId) {
  if (!taskId) {
    return;
  }
  await request.delete(`${API_URL}/api/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(),
  }).catch(() => {});
}

test.use({ baseURL: BASE_URL });

test("real services keep multi-session thinking audit isolated per run", async ({
  context,
  page,
  request,
}) => {
  test.setTimeout(75_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });

  const uniqueSuffix = randomUUID().slice(0, 8);
  const titleA = `US016-A-${uniqueSuffix}`;
  const titleB = `US016-B-${uniqueSuffix}`;
  const reasoningA =
    "US016_A_REASONING_CANARY: 先校验会话 A 仍然只有当前 run，再调用搜索工具，并把后续诊断严格限制在 run-A 内。";
  const reasoningB =
    "US016_B_REASONING_CANARY: 会话 B 在 A 运行期间独立推进，只记录属于 run-B 的搜索与回答片段。";
  const browserErrors = [];
  const pageErrors = [];

  let taskIdA = "";
  let taskIdB = "";
  let seededRunA = null;
  let seededRunB = null;

  page.on("console", (message) => {
    if (message.type() === "error") {
      browserErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(String(error));
  });

  try {
    const createdAResponse = await request.post(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
      data: { model: "deepseek-v4-flash-thinking" },
    });
    expect(createdAResponse.status()).toBe(201);
    taskIdA = (await createdAResponse.json()).task_id;

    const createdBResponse = await request.post(`${API_URL}/api/tasks`, {
      headers: authHeaders(),
      data: { model: "deepseek-v4-flash-thinking" },
    });
    expect(createdBResponse.status()).toBe(201);
    taskIdB = (await createdBResponse.json()).task_id;

    seededRunA = seedRunningThinkingTask(taskIdA, {
      title: titleA,
      runId: `run-us016-a-${uniqueSuffix}`,
      toolCallId: `call-us016-a-${uniqueSuffix}`,
      userMessage: "会话 A 正在执行跨会话并行验收。",
      reasoningContent: reasoningA,
      searchQuery: "multi session audit conversation A",
      toolResultContent: "A_RESULT_CANARY: session A result only",
      answerPreview: "A_ANSWER_CANARY: 会话 A 正在整理独立结果。",
      model: "deepseek-v4-flash-thinking",
    });
    seedVisibleIdleTask(
      taskIdB,
      titleB,
      "会话 B 待启动，用于验证 A 运行期间仍可切换并独立发起新 run。",
      "deepseek-v4-flash-thinking",
    );

    await page.goto("/");
    await expect(page.getByRole("button", { name: titleA, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: titleB, exact: true })).toBeVisible();

    await page.getByRole("button", { name: titleA, exact: true }).click();
    const composer = page.locator("textarea.promptTextarea");
    await expect(page.locator(".historyItemShell-active", { hasText: titleA })).toBeVisible();
    await expect(composer).toHaveAttribute("placeholder", "当前会话正在生成回复，请稍候...");
    await expect(page.getByRole("button", { name: "停止当前会话任务" })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-conversation-a-running.png"),
    });

    let sameTaskPostCount = 0;
    page.on("request", (browserRequest) => {
      if (
        browserRequest.method() === "POST" &&
        browserRequest.url() === `${API_URL}/api/tasks/${encodeURIComponent(taskIdA)}/messages`
      ) {
        sameTaskPostCount += 1;
      }
    });

    await composer.fill(`同会话互斥尝试 ${uniqueSuffix}`);
    await composer.press("Enter");
    await page.waitForTimeout(600);
    expect(sameTaskPostCount).toBe(0);

    const taskAAfterRetryResponse = await request.get(
      `${API_URL}/api/tasks/${encodeURIComponent(taskIdA)}`,
      {
        headers: authHeaders(),
      },
    );
    expect(taskAAfterRetryResponse.ok()).toBeTruthy();
    const taskAAfterRetry = await taskAAfterRetryResponse.json();
    expect(taskAAfterRetry.status).toBe("running");
    expect(taskAAfterRetry.runs).toHaveLength(1);
    expect(taskAAfterRetry.runs[0].id).toBe(seededRunA.runId);

    seededRunB = seedRunningThinkingTask(taskIdB, {
      title: titleB,
      runId: `run-us016-b-${uniqueSuffix}`,
      toolCallId: `call-us016-b-${uniqueSuffix}`,
      userMessage: "会话 B 在 A 运行期间独立启动。",
      reasoningContent: reasoningB,
      searchQuery: "multi session audit conversation B",
      toolResultContent: "B_RESULT_CANARY: session B result only",
      answerPreview: "B_ANSWER_CANARY: 会话 B 也在独立生成。",
      model: "deepseek-v4-flash-thinking",
    });

    const [taskACurrentResponse, taskBCurrentResponse] = await Promise.all([
      request.get(`${API_URL}/api/tasks/${encodeURIComponent(taskIdA)}`, {
        headers: authHeaders(),
      }),
      request.get(`${API_URL}/api/tasks/${encodeURIComponent(taskIdB)}`, {
        headers: authHeaders(),
      }),
    ]);
    expect(taskACurrentResponse.ok()).toBeTruthy();
    expect(taskBCurrentResponse.ok()).toBeTruthy();
    const taskACurrent = await taskACurrentResponse.json();
    const taskBCurrent = await taskBCurrentResponse.json();
    expect(taskACurrent.status).toBe("running");
    expect(taskBCurrent.status).toBe("running");
    expect(taskACurrent.runs[0].id).toBe(seededRunA.runId);
    expect(taskBCurrent.runs[0].id).toBe(seededRunB.runId);
    expect(taskACurrent.runs[0].id).not.toBe(taskBCurrent.runs[0].id);

    await page.getByRole("button", { name: titleB, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: titleB })).toBeVisible();
    await expect(composer).toHaveValue("");
    await expect(composer).toHaveAttribute("placeholder", "当前会话正在生成回复，请稍候...");
    await expect(page.getByRole("button", { name: "停止当前会话任务" })).toBeVisible();
    const logPanelB = page.getByRole("region", { name: /第 1 轮进度日志/ }).first();
    await expect(logPanelB).toBeVisible();
    const bSummaryText = (
      await logPanelB.locator(".liveStatusRow summary, .liveToolCard summary").allTextContents()
    ).join("\n");
    expect(bSummaryText).toContain("AI正在思考");
    expect(bSummaryText).toContain("调用联网搜索");
    expect(bSummaryText).toContain("联网搜索已返回结果");
    expect(bSummaryText).toContain("AI正在生成结果");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-conversation-b-running-while-a-running.png"),
    });

    await expect(logPanelB.locator("details.runDiagnosticsPanel")).toHaveCount(0);
    await expect(logPanelB.locator(".traceHeader .traceCopyButton")).toHaveCount(0);
    const downloadLogsButtonB = logPanelB.getByRole("button", { name: /下载.*完整日志/ });
    await expect(downloadLogsButtonB).toBeVisible();
    const downloadEventB = page.waitForEvent("download");
    await downloadLogsButtonB.click();
    const downloadB = await downloadEventB;
    expect(downloadB.suggestedFilename()).toBe(`${seededRunB.runId}-logs.jsonl`);
    const downloadBPath = path.join(evidenceDir, "03-conversation-b-diagnostics.jsonl");
    await downloadB.saveAs(downloadBPath);
    const downloadBContent = fs.readFileSync(downloadBPath, "utf-8");
    expect(downloadBContent).toContain(reasoningB);
    expect(downloadBContent).toContain(seededRunB.runId);
    expect(downloadBContent).toContain('"type": "tool_call"');
    expect(downloadBContent).toContain('"type": "tool_result"');
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-conversation-b-diagnostics-expanded.png"),
    });

    await page.getByRole("button", { name: titleA, exact: true }).click();
    await expect(page.locator(".historyItemShell-active", { hasText: titleA })).toBeVisible();
    await expect(composer).toHaveAttribute("placeholder", "当前会话正在生成回复，请稍候...");
    const logPanelA = page.getByRole("region", { name: /第 1 轮进度日志/ }).first();
    await expect(logPanelA).toBeVisible();
    await expect(logPanelA.locator("details.runDiagnosticsPanel")).toHaveCount(0);
    await expect(logPanelA.locator(".traceHeader .traceCopyButton")).toHaveCount(0);
    const downloadLogsButtonA = logPanelA.getByRole("button", { name: /下载.*完整日志/ });
    await expect(downloadLogsButtonA).toBeVisible();
    const downloadEventA = page.waitForEvent("download");
    await downloadLogsButtonA.click();
    const downloadA = await downloadEventA;
    expect(downloadA.suggestedFilename()).toBe(`${seededRunA.runId}-logs.jsonl`);
    const downloadAPath = path.join(evidenceDir, "04-conversation-a-diagnostics.jsonl");
    await downloadA.saveAs(downloadAPath);
    const downloadAContent = fs.readFileSync(downloadAPath, "utf-8");
    expect(downloadAContent).toContain(reasoningA);
    expect(downloadAContent).toContain(seededRunA.runId);
    expect(downloadAContent).toContain('"type": "tool_call"');
    expect(downloadAContent).toContain('"type": "tool_result"');
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-conversation-a-diagnostics-expanded.png"),
    });

    expect(browserErrors).toEqual([]);
    expect(pageErrors).toEqual([]);

    writeJson(path.join(evidenceDir, "assertions.json"), {
      taskA: { id: taskIdA, runId: seededRunA.runId, title: titleA },
      taskB: { id: taskIdB, runId: seededRunB.runId, title: titleB },
      sameTaskPostCount,
      copiedARecordCount: copiedALines.length,
      copiedBRecordCount: copiedBLines.length,
      browserErrors,
      pageErrors,
    });
  } finally {
    if (seededRunA) {
      markTaskComplete(taskIdA, seededRunA.runId);
    }
    if (seededRunB) {
      markTaskComplete(taskIdB, seededRunB.runId);
    }
    await deleteTaskIfPresent(request, taskIdA);
    await deleteTaskIfPresent(request, taskIdB);
  }
});
