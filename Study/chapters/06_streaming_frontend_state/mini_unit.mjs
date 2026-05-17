import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

function normalizeEventRecord(raw) {
  return {
    id: String(raw.id),
    seq: Number.isFinite(raw.seq) ? raw.seq : undefined,
    type: String(raw.type || "log"),
    title: raw.message || raw.type || "事件",
    createdAt: raw.created_at || raw.createdAt || "",
  };
}

function mergeById(current, incoming) {
  const byId = new Map();
  for (const item of [...current, ...incoming].map(normalizeEventRecord)) {
    byId.set(item.id, item);
  }
  return [...byId.values()];
}

function orderForDisplay(logs) {
  return [...logs].sort((a, b) => {
    if (a.seq !== undefined && b.seq !== undefined) {
      return a.seq - b.seq;
    }
    return a.createdAt.localeCompare(b.createdAt);
  });
}

function assertSourceContracts() {
  const taskState = readFileSync(resolve(repoRoot, "frontend/app/task-state.ts"), "utf-8");
  const workspaceView = readFileSync(resolve(repoRoot, "frontend/app/workspace-view.ts"), "utf-8");
  const streamingApi = readFileSync(resolve(repoRoot, "backend/app/api/streaming.py"), "utf-8");

  if (!taskState.includes("export function mergeExecutionLogs")) {
    throw new Error("task-state.ts 应导出 mergeExecutionLogs");
  }
  if (!taskState.includes("if (!seen.has(log.id))")) {
    throw new Error("mergeExecutionLogs 应按 id 去重追加");
  }
  if (!workspaceView.includes("function byLogOrder")) {
    throw new Error("workspace-view.ts 应包含展示排序函数 byLogOrder");
  }
  if (!workspaceView.includes("return left.seq - right.seq")) {
    throw new Error("展示排序应优先使用 seq");
  }
  if (!streamingApi.includes("remaining = storage.read_events")) {
    throw new Error("SSE 结束前应 drain remaining events");
  }
  if (!streamingApi.includes("format_sse_done")) {
    throw new Error("SSE 应发送 done 信号");
  }
}

const merged = mergeById(
  [
    { id: "b", seq: 2, type: "tool_result", message: "工具返回", created_at: "10:00:00" },
  ],
  [
    { id: "a", seq: 1, type: "tool_call", message: "调用工具", created_at: "10:00:00" },
    { id: "c", seq: 3, type: "final_answer", message: "最终回答", created_at: "10:00:00" },
  ],
);
const logs = orderForDisplay(merged);

if (logs.map((item) => item.id).join(",") !== "a,b,c") {
  throw new Error("日志必须优先按 backend seq 排序，而不是只按显示时间排序");
}
assertSourceContracts();

console.log(logs);
console.log("OK: 你已经理解了 SSE 事件合并和 seq 排序。");
