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
    throw new Error(`${name} is required for progress-log E2E`);
  }
  return value;
}

function authHeaders() {
  return ACCESS_TOKEN ? { "X-MyAgent-Token": ACCESS_TOKEN } : {};
}

function nowIso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d{3}Z$/, "Z");
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

function seedCompletedProgressLogTask(taskId, title) {
  const runId = `run-progress-e2e-${Date.now()}`;
  const startedAt = nowIso();
  const completedAt = nowIso(9000);
  const eventSeeds = [
    {
      type: "values_snapshot",
      message: "State snapshot",
      createdAt: nowIso(500),
      level: "info",
      payload: {
        snapshot_keys: ["messages", "is_subgraph"],
        is_subgraph: false,
      },
    },
    {
      type: "assistant_thinking_delta",
      message: "I should search for recent news.",
      createdAt: nowIso(1000),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 1,
        content: "I should search for recent news.",
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
      message: "Calling tool: tavily_search",
      createdAt: nowIso(1500),
      level: "info",
      payload: {
        id: "tool-progress-e2e-1",
        name: "tavily_search",
        args: "{\"query\"",
        raw_args: "{\"query\"",
        partial: true,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "selecting_tool",
          tool_name: "tavily_search",
          tool_label: "联网搜索",
          tool_call_id: "tool-progress-e2e-1",
          parameter_items: [{ key: "args", value: "{\"query\"" }],
        },
      },
    },
    {
      type: "tool_call",
      message: "Tool call: tavily_search",
      createdAt: nowIso(2000),
      level: "info",
      payload: {
        id: "tool-progress-e2e-1",
        name: "tavily_search",
        args: { query: "progress log e2e", max_results: 5 },
        raw_args: "{\"query\":\"progress log e2e\",\"max_results\":5}",
        partial: false,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "using_tool",
          tool_name: "tavily_search",
          tool_label: "联网搜索",
          tool_call_id: "tool-progress-e2e-1",
          parameter_items: [
            { key: "query", value: "progress log e2e" },
            { key: "max_results", value: 5 },
          ],
        },
      },
    },
    {
      type: "tool_result",
      message: "Tool result: tavily_search",
      createdAt: nowIso(3000),
      level: "success",
      payload: {
        name: "tavily_search",
        status: "success",
        content: "2 results",
        live: {
          schema_version: 1,
          kind: "tool_result",
          stage: "completed",
          tool_name: "tavily_search",
          tool_label: "联网搜索",
          tool_call_id: "tool-progress-e2e-1",
          result_status: "success",
          result_count: 2,
          parameter_items: [],
        },
      },
    },
    {
      type: "values_snapshot",
      message: "State snapshot",
      createdAt: nowIso(3200),
      level: "info",
      payload: {
        snapshot_keys: ["messages", "skills_metadata", "is_subgraph"],
        is_subgraph: false,
      },
    },
    {
      type: "status_update",
      message: "State update: tools",
      createdAt: nowIso(3400),
      level: "info",
      payload: {
        node: "tools",
        live: {
          schema_version: 1,
          kind: "status",
          stage: "organizing_state",
          display_text: "正在整理工具结果...",
          diagnostic_label: "tools",
          parameter_items: [],
        },
      },
    },
    {
      type: "assistant_thinking_delta",
      message: "I should verify with another source.",
      createdAt: nowIso(3600),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 2,
        content: "I should verify with another source.",
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
      message: "Tool call: tavily_search",
      createdAt: nowIso(4200),
      level: "info",
      payload: {
        id: "tool-progress-e2e-2",
        name: "tavily_search",
        args: { query: "progress log e2e BBC" },
        partial: false,
        is_subgraph: false,
        live: {
          schema_version: 1,
          kind: "tool_call",
          stage: "using_tool",
          tool_name: "tavily_search",
          tool_label: "联网搜索",
          tool_call_id: "tool-progress-e2e-2",
          parameter_items: [{ key: "query", value: "progress log e2e BBC" }],
        },
      },
    },
    {
      type: "tool_result",
      message: "Tool result: tavily_search",
      createdAt: nowIso(5200),
      level: "success",
      payload: {
        name: "tavily_search",
        status: "success",
        content: "1 result",
        live: {
          schema_version: 1,
          kind: "tool_result",
          stage: "completed",
          tool_name: "tavily_search",
          tool_label: "联网搜索",
          tool_call_id: "tool-progress-e2e-2",
          result_status: "success",
          result_count: 1,
          parameter_items: [],
        },
      },
    },
    {
      type: "assistant_answer_delta",
      message: "AI reply chunk",
      createdAt: nowIso(6200),
      level: "info",
      payload: {
        schema_version: 1,
        stream_index: 3,
        content: "这段原始流式内容会显示在展开日志里。",
        is_subgraph: false,
      },
    },
    {
      type: "status_update",
      message: "State update: TodoListMiddleware.after_model",
      createdAt: nowIso(7200),
      level: "info",
      payload: {
        node: "TodoListMiddleware.after_model",
        live: {
          schema_version: 1,
          kind: "status",
          stage: "organizing_state",
          display_text: "模型输出已完成",
          diagnostic_label: "TodoListMiddleware.after_model",
          parameter_items: [],
        },
      },
    },
    {
      type: "task_completed",
      message: "任务已完成。",
      createdAt: nowIso(8200),
      level: "success",
      payload: {
        previous_status: "running",
        live: {
          schema_version: 1,
          kind: "status",
          stage: "completed",
          display_text: "任务已完成",
          diagnostic_label: "runner.terminal",
          parameter_items: [{ key: "previous_status", value: "running" }],
        },
      },
    },
    {
      type: "final_answer",
      message: "Final answer generated",
      createdAt: nowIso(8300),
      level: "success",
      payload: {
        content: "最终回答已生成。",
        live: {
          schema_version: 1,
          kind: "answer_status",
          stage: "completed",
          display_text: "回答已完成",
          diagnostic_label: "runner.final_answer",
          parameter_items: [],
          result_status: "success",
        },
      },
    },
  ];

  runSql(`
UPDATE tasks
SET status = 'complete',
    title = ${sqlString(title)},
    model = 'deepseek-v4-flash',
    updated_at = ${sqlString(completedAt)},
    error = NULL,
    needs_input = NULL,
    active_run_id = NULL
WHERE task_id = ${sqlString(taskId)};

INSERT INTO runs (
  task_id, id, status, message, model, started_at, completed_at,
  error, needs_input, artifact_base_path, artifact_names
)
VALUES (
  ${sqlString(taskId)},
  ${sqlString(runId)},
  'complete',
  ${sqlString(title)},
  'deepseek-v4-flash',
  ${sqlString(startedAt)},
  ${sqlString(completedAt)},
  NULL,
  NULL,
  ${sqlString(`artifacts/runs/${runId}`)},
  '[]'::jsonb
);

INSERT INTO messages (task_id, run_id, role, content, created_at, level)
VALUES (${sqlString(taskId)}, ${sqlString(runId)}, 'user', ${sqlString(title)}, ${sqlString(startedAt)}, NULL);

${eventSeeds.map((event) => appendEventSql(taskId, { ...event, runId })).join("\n")}
`);

  return runId;
}

test.use({ baseURL: BASE_URL });

test("progress log rows keep left timestamps and all rows expand diagnostics", async ({
  context,
  page,
  request,
}) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });

  const title = `进度日志验收-${randomUUID().slice(0, 8)}`;
  const createdResponse = await request.post(`${API_URL}/api/tasks`, {
    headers: authHeaders(),
    data: { model: "deepseek-v4-flash" },
  });
  expect(createdResponse.status()).toBe(201);
  const createdTask = await createdResponse.json();
  const taskId = createdTask.task_id;
  const runId = seedCompletedProgressLogTask(taskId, title);

  try {
    await page.goto("/");
    await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "01-history-with-seeded-task.png"),
    });

    await page.getByRole("button", { name: title, exact: true }).click();
    const logPanel = page.getByRole("region", { name: /进度日志/ }).first();
    await expect(logPanel).toBeVisible();
    const rows = logPanel.locator(".liveStatusRow, .liveToolCard");
    await expect(rows).toHaveCount(11);
    await expect(rows.nth(0).locator("summary").getByText("AI正在思考")).toBeVisible();
    await expect(rows.nth(1).locator("summary").getByText("准备调用联网搜索")).toBeVisible();
    await expect(rows.nth(2).locator("summary").getByText("调用联网搜索")).toBeVisible();
    await expect(rows.nth(3).locator("summary").getByText("联网搜索已返回结果")).toBeVisible();
    await expect(rows.nth(4).locator("summary").getByText("状态已更新")).toBeVisible();
    await expect(rows.nth(5).locator("summary").getByText("AI正在思考")).toBeVisible();
    await expect(rows.nth(6).locator("summary").getByText("调用联网搜索")).toBeVisible();
    await expect(rows.nth(7).locator("summary").getByText("联网搜索已返回结果")).toBeVisible();
    await expect(rows.nth(8).locator("summary").getByText("AI正在生成结果")).toBeVisible();
    await expect(rows.nth(9).locator("summary").getByText("状态已更新")).toBeVisible();
    await expect(rows.nth(10).locator("summary").getByText("任务已完成")).toBeVisible();
    const collapsedSummaryText = (await logPanel.locator("summary").allTextContents()).join("\n");
    expect(collapsedSummaryText).not.toContain("State snapshot");
    expect(collapsedSummaryText).not.toContain("正在准备任务...");
    expect(collapsedSummaryText).not.toContain("正在整理工具结果...");
    expect(collapsedSummaryText).not.toContain("模型输出已完成");
    expect(collapsedSummaryText).not.toContain("回答已完成");
    expect(collapsedSummaryText).toContain("状态已更新");
    await expect(logPanel.locator("summary .liveLogCopyButton")).toHaveCount(11);
    await expect(rows.nth(8).locator("pre")).toBeHidden();
    await expect(rows.nth(1).locator("summary time")).not.toContainText("-");
    const toolSummaryLine = rows.nth(1).locator("summary .liveToolSummaryText");
    await expect(toolSummaryLine).toContainText("准备调用联网搜索");
    await expect(toolSummaryLine).not.toContainText("tavily_search");
    await expect(toolSummaryLine).not.toContainText("query=progress log e2e");
    await expect(rows.nth(1).locator("summary .liveToolSummaryMeta")).toHaveCount(0);
    await expect(toolSummaryLine.locator("code")).toHaveCount(0);
    expect(await toolSummaryLine.evaluate((element) => getComputedStyle(element).whiteSpace)).toBe("nowrap");
    const logToggleButton = logPanel.locator(".traceHeader .traceLogToggleButton");
    const rawLogCopyButton = logPanel.locator(".traceHeader .traceCopyButton");
    await expect(logToggleButton).toHaveText("全部展开");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "false");
    await expect(logToggleButton).toHaveAttribute("aria-label", "展开第 1 轮全部日志");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-progress-log-collapsed.png"),
    });
    await rows.nth(1).screenshot({
      path: path.join(evidenceDir, "02-tool-row-collapsed-detail.png"),
    });
    await logToggleButton.screenshot({
      path: path.join(evidenceDir, "02-log-toggle-collapsed-detail.png"),
    });
    await rows.nth(1).locator("summary").click();
    await expect(rows.nth(1)).toHaveAttribute("open", "");
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(1);
    await expect(logToggleButton).toHaveText("全部折叠");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    await expect(logToggleButton).toHaveAttribute("aria-label", "折叠第 1 轮全部日志");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-partial-log-row-expanded.png"),
    });
    await logToggleButton.screenshot({
      path: path.join(evidenceDir, "02-log-toggle-partial-expanded-detail.png"),
    });
    await logToggleButton.click();
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(0);
    await expect(logToggleButton).toHaveText("全部展开");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "false");

    await logToggleButton.click();
    await expect(logToggleButton).toHaveText("全部折叠", { timeout: 500 });
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(11);
    await page.mouse.move(0, 0);
    await page.waitForTimeout(220);
    await expect(logToggleButton).toHaveText("全部折叠");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    const expandedToggleStyles = await logToggleButton.evaluate((element) => {
      const button = getComputedStyle(element);
      return {
        backgroundColor: button.backgroundColor,
        borderColor: button.borderColor,
      };
    });
    const rawLogCopyButtonStylesInitial = await rawLogCopyButton.evaluate((element) => {
      const button = getComputedStyle(element);
      return {
        backgroundColor: button.backgroundColor,
        borderColor: button.borderColor,
      };
    });
    expect(expandedToggleStyles.backgroundColor).toBe(rawLogCopyButtonStylesInitial.backgroundColor);
    expect(expandedToggleStyles.borderColor).toBe(rawLogCopyButtonStylesInitial.borderColor);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "02-all-log-rows-expanded-by-toggle.png"),
    });
    await logToggleButton.screenshot({
      path: path.join(evidenceDir, "02-log-toggle-expanded-detail.png"),
    });
    await logToggleButton.click();
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(0);
    await expect(logToggleButton).toHaveText("全部展开");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "false");

    await rawLogCopyButton.click();
    const copiedRawJsonl = await page.evaluate(() => navigator.clipboard.readText());
    const copiedRawLines = copiedRawJsonl.trim().split("\n").map((line) => JSON.parse(line));
    expect(copiedRawLines.some((line) => line.type === "tool_call" && line.payload?.partial === true)).toBe(true);
    expect(copiedRawLines.some((line) => line.type === "tool_result" && line.payload?.content === "2 results")).toBe(true);

    const collapsedGenerationCopyButton = rows.nth(8).locator("summary .liveLogCopyButton");
    await collapsedGenerationCopyButton.click();
    await expect(rows.nth(8)).not.toHaveAttribute("open", "");
    const collapsedCopiedGenerationJson = await page.evaluate(() => navigator.clipboard.readText());
    expect(JSON.parse(collapsedCopiedGenerationJson).payload.answer_stream.content).toContain(
      "这段原始流式内容会显示在展开日志里。",
    );

    for (let index = 0; index < 11; index += 1) {
      const row = rows.nth(index);
      await expect(row).toHaveJSProperty("tagName", "DETAILS");
      const summary = row.locator("summary");
      const timeBox = await summary.locator("time").boundingBox();
      const labelBox = await summary.locator("span:not(.thinkingDots), strong").first().boundingBox();
      const rowBox = await row.boundingBox();
      expect(timeBox).toBeTruthy();
      expect(labelBox).toBeTruthy();
      expect(rowBox).toBeTruthy();
      expect(timeBox.x).toBeLessThan(labelBox.x);
      expect(timeBox.x - rowBox.x).toBeLessThan(20);
    }

    await rows.nth(8).locator("summary").click();
    await expect(rows.nth(8)).toHaveAttribute("open", "");
    await expect(rows.nth(8).locator("dl")).toHaveCount(0);
    await expect(rows.nth(8).locator(".liveLogDiagnosticRows")).toHaveCount(0);
    await expect(rows.nth(8).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(8).locator("pre")).toContainText('"type": "assistant_answer_delta"');
    await expect(rows.nth(8).locator("pre")).toContainText('"content"');
    await expect(rows.nth(8).locator("pre")).not.toContainText('"accumulated_content"');
    await expect(rows.nth(8).locator("pre")).not.toContainText('"chunks"');
    await expect(rows.nth(8).locator("pre")).not.toContainText('"chunk_count"');
    await expect(rows.nth(8).locator("pre")).toContainText("这段原始流式内容会显示在展开日志里。");
    await expect(rows.nth(8)).not.toContainText("事件类型");
    await expect(rows.nth(8)).not.toContainText("显示方式");
    const generationCopyButton = rows.nth(8).locator("summary .liveLogCopyButton");
    const generationSummaryBox = await rows.nth(8).locator("summary").boundingBox();
    const generationCopyBox = await generationCopyButton.boundingBox();
    expect(generationSummaryBox).toBeTruthy();
    expect(generationCopyBox).toBeTruthy();
    expect(generationCopyBox.y).toBeLessThan(generationSummaryBox.y + generationSummaryBox.height);
    await generationCopyButton.click();
    await expect(generationCopyButton).toHaveAttribute("aria-label", "已复制此行日志JSON");
    await expect(rows.nth(8)).toHaveAttribute("open", "");
    const copiedGenerationJson = await page.evaluate(() => navigator.clipboard.readText());
    expect(JSON.parse(copiedGenerationJson).payload.answer_stream.content).toContain(
      "这段原始流式内容会显示在展开日志里。",
    );
    await expect(rows.nth(8).locator("dt")).toHaveCount(0);
    await expect(rows.nth(8).locator("pre")).not.toContainText('"content_hidden": true');
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "03-answer-row-expanded.png"),
    });
    await rows.nth(8).screenshot({
      path: path.join(evidenceDir, "03-answer-row-expanded-detail.png"),
    });

    await rows.nth(1).locator("summary").click();
    await expect(rows.nth(1)).toHaveAttribute("open", "");
    await expect(rows.nth(1).locator("dl")).toHaveCount(0);
    await expect(rows.nth(1).locator("p")).toHaveCount(0);
    await expect(rows.nth(1).locator(".liveToolPayload")).toHaveCount(0);
    await expect(rows.nth(1).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(1).locator("pre")).toContainText('"type": "tool_call"');
    await expect(rows.nth(1).locator("pre")).toContainText('"tool_name": "tavily_search"');
    await expect(rows.nth(1).locator("pre")).toContainText('"stage": "selecting_tool"');
    await expect(rows.nth(1).locator("pre")).not.toContainText('"tool_result"');
    await expect(rows.nth(1).locator("pre")).not.toContainText('"content": "2 results"');
    await expect(rows.nth(1).locator("pre")).not.toContainText('"records"');
    await expect(rows.nth(1)).not.toContainText("事件类型");
    await expect(rows.nth(1)).not.toContainText("结果状态");
    await expect(rows.nth(1).locator("dt")).toHaveCount(0);
    const toolCopyButton = rows.nth(1).locator("summary .liveLogCopyButton");
    await toolCopyButton.click();
    await expect(rows.nth(1)).toHaveAttribute("open", "");
    const copiedToolJson = await page.evaluate(() => navigator.clipboard.readText());
    const copiedToolRecord = JSON.parse(copiedToolJson);
    expect(copiedToolRecord.type).toBe("tool_call");
    expect(copiedToolRecord.tool_name).toBe("tavily_search");
    expect(copiedToolRecord.stage).toBe("selecting_tool");
    expect(copiedToolRecord.args).toBe('{"query"');
    const successfulToolOpenBorderColor = await rows.nth(1).evaluate(
      (element) => getComputedStyle(element).borderTopColor,
    );
    expect(successfulToolOpenBorderColor).not.toMatch(/204,\s*120,\s*92/);
    expect(successfulToolOpenBorderColor).not.toMatch(/198,\s*69,\s*69/);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "04-tool-row-expanded.png"),
    });
    await rows.nth(1).screenshot({
      path: path.join(evidenceDir, "04-tool-row-expanded-detail.png"),
    });

    await rows.nth(3).locator("summary").click();
    await expect(rows.nth(3)).toHaveAttribute("open", "");
    await expect(rows.nth(3).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(3).locator("pre")).toContainText('"type": "tool_result"');
    await expect(rows.nth(3).locator("pre")).toContainText('"status": "success"');
    await expect(rows.nth(3).locator("pre")).toContainText('"content": "2 results"');

    await rows.nth(4).locator("summary").click();
    await expect(rows.nth(4)).toHaveAttribute("open", "");
    await expect(rows.nth(4).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(4).locator("pre")).toContainText('"type": "status_update"');
    await expect(rows.nth(4).locator("pre")).toContainText('"type": "values_snapshot"');
    await expect(rows.nth(4).locator("pre")).toContainText('"display_text": "正在整理工具结果..."');

    await rows.nth(5).locator("summary").click();
    await expect(rows.nth(5)).toHaveAttribute("open", "");
    await expect(rows.nth(5).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(5).locator("pre")).toContainText('"type": "assistant_thinking_delta"');
    await expect(rows.nth(5).locator("pre")).toContainText("I should verify with another source.");
    await expect(rows.nth(5).locator("pre")).not.toContainText('"chunks"');

    await rows.nth(0).locator("summary").click();
    await expect(rows.nth(0)).toHaveAttribute("open", "");
    await expect(rows.nth(0).locator("dl")).toHaveCount(0);
    await expect(rows.nth(0).locator(".liveLogDiagnosticRows")).toHaveCount(0);
    await expect(rows.nth(0).locator("summary .liveLogCopyButton")).toBeVisible();
    await expect(rows.nth(0).locator("pre")).toContainText('"type": "assistant_thinking_delta"');
    await expect(rows.nth(0).locator("pre")).not.toContainText('"type": "values_snapshot"');
    await expect(rows.nth(0).locator("pre")).not.toContainText('"chunks"');
    await expect(rows.nth(0).locator("pre")).not.toContainText('"chunk_count"');
    await expect(rows.nth(0).locator("pre")).not.toContainText('"accumulated_content"');
    await expect(rows.nth(0).locator("pre")).toContainText("I should search for recent news.");
    await expect(rows.nth(0).locator("pre")).not.toContainText("I should verify with another source.");
    await expect(rows.nth(0)).not.toContainText("思考内容");
    const thinkingCopyButton = rows.nth(0).locator("summary .liveLogCopyButton");
    await thinkingCopyButton.click();
    await expect(rows.nth(0)).toHaveAttribute("open", "");
    const copiedThinkingJson = await page.evaluate(() => navigator.clipboard.readText());
    const copiedThinkingRecord = JSON.parse(copiedThinkingJson);
    expect(copiedThinkingRecord.payload.thinking_stream.content).toContain(
      "I should search for recent news.",
    );
    await expect(rows.nth(0).locator("dt")).toHaveCount(0);
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "06-thinking-row-expanded.png"),
    });
    await rows.nth(0).screenshot({
      path: path.join(evidenceDir, "06-thinking-row-expanded-detail.png"),
    });

    await rows.nth(9).locator("summary").click();
    await expect(rows.nth(9)).toHaveAttribute("open", "");
    await expect(rows.nth(9).locator("pre")).toContainText('"type": "status_update"');
    await expect(rows.nth(9).locator("pre")).toContainText('"display_text": "模型输出已完成"');
    await rows.nth(10).locator("summary").click();
    await expect(rows.nth(10)).toHaveAttribute("open", "");
    await expect(rows.nth(10).locator("pre")).toContainText('"type": "task_completed"');
    await expect(rows.nth(10).locator("pre")).toContainText('"display_text": "任务已完成"');
    await expect(rows.nth(10).locator("pre")).toContainText('"type": "final_answer"');
    await expect(rows.nth(10).locator("pre")).toContainText('"display_text": "回答已完成"');
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "07-terminal-rows-expanded.png"),
    });

    await expect(logToggleButton).toHaveText("全部折叠");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    await expect(logToggleButton).toHaveAttribute("aria-label", "折叠第 1 轮全部日志");
    await expect(rawLogCopyButton).not.toHaveClass(/copyButton-copied/);
    const toggleButtonStyles = await logToggleButton.evaluate((element) => {
      const button = getComputedStyle(element);
      const before = getComputedStyle(element, "::before");
      const after = getComputedStyle(element, "::after");
      return {
        backgroundColor: button.backgroundColor,
        borderColor: button.borderColor,
        borderRadius: button.borderRadius,
        textDecorationLine: button.textDecorationLine,
        afterMaskImage: after.webkitMaskImage || after.maskImage,
        beforeDisplay: before.display,
      };
    });
    const rawLogCopyButtonStyles = await rawLogCopyButton.evaluate((element) => {
      const button = getComputedStyle(element);
      return {
        backgroundColor: button.backgroundColor,
        borderColor: button.borderColor,
      };
    });
    expect(toggleButtonStyles.backgroundColor).toBe(rawLogCopyButtonStyles.backgroundColor);
    expect(toggleButtonStyles.borderColor).toBe(rawLogCopyButtonStyles.borderColor);
    expect(toggleButtonStyles.backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
    expect(toggleButtonStyles.borderRadius).not.toBe("0px");
    expect(toggleButtonStyles.textDecorationLine).toBe("none");
    expect(toggleButtonStyles.beforeDisplay).toBe("none");
    await logToggleButton.screenshot({
      path: path.join(evidenceDir, "07-log-toggle-partial-detail.png"),
    });
    await logToggleButton.hover();
    await logToggleButton.focus();
    await logPanel.locator(".traceHeader").screenshot({
      path: path.join(evidenceDir, "07-log-toggle-hover-focus.png"),
    });
    await logToggleButton.click();
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(0);
    await expect(logToggleButton).toHaveText("全部展开", { timeout: 500 });
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "false");

    await logToggleButton.click();
    await expect(logToggleButton).toHaveText("全部折叠", { timeout: 500 });
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(11);
    await page.mouse.move(0, 0);
    await page.waitForTimeout(220);
    await expect(logToggleButton).toHaveText("全部折叠");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "true");
    const expandedToggleStylesLater = await logToggleButton.evaluate((element) => {
      const button = getComputedStyle(element);
      return {
        backgroundColor: button.backgroundColor,
        borderColor: button.borderColor,
      };
    });
    expect(expandedToggleStylesLater.backgroundColor).toBe(rawLogCopyButtonStyles.backgroundColor);
    expect(expandedToggleStylesLater.borderColor).toBe(rawLogCopyButtonStyles.borderColor);
    await logToggleButton.screenshot({
      path: path.join(evidenceDir, "07-log-toggle-expanded-detail.png"),
    });
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "07-all-log-rows-expanded-by-toggle.png"),
    });
    await logToggleButton.click();
    await expect
      .poll(async () => rows.evaluateAll((elements) => elements.filter((element) => element.hasAttribute("open")).length))
      .toBe(0);
    await expect(logToggleButton).toHaveText("全部展开");
    await expect(logToggleButton).toHaveAttribute("aria-expanded", "false");
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "08-all-log-rows-collapsed-by-button.png"),
    });
    await page.setViewportSize({ width: 500, height: 760 });
    await expect(logPanel.locator(".traceHeader")).toBeVisible();
    await page.screenshot({
      fullPage: true,
      path: path.join(evidenceDir, "09-narrow-collapsed-log-header.png"),
    });
  } finally {
    runSql(`
UPDATE tasks
SET status = 'complete',
    active_run_id = NULL,
    updated_at = ${sqlString(nowIso())}
WHERE task_id = ${sqlString(taskId)};

UPDATE runs
SET status = 'complete',
    completed_at = ${sqlString(nowIso())}
WHERE task_id = ${sqlString(taskId)}
  AND id = ${sqlString(runId)};
`);

    const deleteResponse = await request.delete(`${API_URL}/api/tasks/${taskId}`, {
      headers: authHeaders(),
    });
    expect(deleteResponse.ok()).toBeTruthy();
  }
});
