import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const DEFAULT_FILE_PROMPT = "请分析已上传文件，先按需读取资源内容，再总结关键差异。";

const submitPlan = [
  "checkCanSend",
  "guardModel",
  "ensureTask",
  "uploadFiles",
  "chooseTaskContent",
  "postMessage",
  "refreshTask",
  "refreshHistory",
];

function assertSubmitPlan(plan) {
  const position = Object.fromEntries(plan.map((name, index) => [name, index]));
  if (position.guardModel > position.ensureTask) {
    throw new Error("模型不可用必须在创建 task 前拦截");
  }
  if (position.guardModel > position.uploadFiles) {
    throw new Error("模型不可用必须在上传文件前拦截");
  }
  if (position.ensureTask > position.postMessage) {
    throw new Error("发送消息前必须先有 task id");
  }
}

function chooseTaskContent(input) {
  const content = input.trim();
  return content || DEFAULT_FILE_PROMPT;
}

function buildSandboxedPreview(name, blobUrl) {
  return `<iframe sandbox="" referrerpolicy="no-referrer" src="${blobUrl}" title="${name}"></iframe>`;
}

function assertSourceContracts() {
  const hook = readFileSync(resolve(repoRoot, "frontend/hooks/use-task-workspace.ts"), "utf-8");
  const workspace = readFileSync(
    resolve(repoRoot, "frontend/components/chat/TaskWorkspace.tsx"),
    "utf-8",
  );
  const api = readFileSync(resolve(repoRoot, "frontend/lib/task-api.ts"), "utf-8");

  const submitStart = hook.indexOf("const handleSubmit = useCallback");
  const submitEnd = hook.indexOf("const handleStop = useCallback");
  const submitBody = hook.slice(submitStart, submitEnd);
  const guardIndex = submitBody.indexOf("if (!selectedModelRunnable)");
  const ensureIndex = submitBody.indexOf("ensureTask()");
  const uploadIndex = submitBody.indexOf("uploadTaskFiles");
  const defaultPromptIndex = submitBody.indexOf("const taskContent = content || DEFAULT_FILE_PROMPT");
  if (guardIndex < 0 || ensureIndex < 0 || uploadIndex < 0 || defaultPromptIndex < 0) {
    throw new Error("handleSubmit 应包含模型可用性检查、ensureTask、uploadTaskFiles 和默认文件提示词");
  }
  if (!(guardIndex < ensureIndex && guardIndex < uploadIndex)) {
    throw new Error("模型不可用必须在创建 task 和上传文件前拦截");
  }
  for (const component of ["ChatSidebar", "TaskConversation", "ChatComposer"]) {
    if (!workspace.includes(component)) {
      throw new Error(`TaskWorkspace 应组合 ${component}`);
    }
  }
  if (!api.includes("requestTaskJson")) {
    throw new Error("API 请求应集中封装在 task-api.ts");
  }
  if (!hook.includes("buildSandboxedArtifactPreviewDocument")) {
    throw new Error("HTML artifact 预览应走 sandbox document");
  }
}

assertSubmitPlan(submitPlan);
if (chooseTaskContent("   ") !== DEFAULT_FILE_PROMPT) {
  throw new Error("只上传文件时，前端应改发默认文件分析提示词");
}
const preview = buildSandboxedPreview("report.html", "blob:http://localhost/report");
if (!preview.includes('sandbox=""')) {
  throw new Error("HTML artifact 必须在禁用脚本的 sandbox iframe 中预览");
}
assertSourceContracts();

console.log(submitPlan.join(" -> "));
console.log("OK: 你已经理解前端工作区的提交流程和 artifact 预览边界。");
