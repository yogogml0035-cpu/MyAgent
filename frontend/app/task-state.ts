export type TaskStatus =
  | "idle"
  | "running"
  | "complete"
  | "cancelled"
  | "failed"
  | "needs_input"
  | "interrupted"
  | "unknown";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt?: string;
  runId?: string | null;
  level?: "info" | "warning" | "error";
};

export type ExecutionLog = {
  id: string;
  type?: string;
  title: string;
  detail?: string;
  level?: "info" | "success" | "warning" | "error";
  createdAt?: string;
  runId?: string | null;
  reasoning?: ReasoningTrace;
};

export type ReasoningPhase = "plan" | "observe" | "decide" | "next_step" | "final_summary" | "risk";
export type ReasoningConfidence = "low" | "medium" | "high";

export type ReasoningTrace = {
  agentId: string;
  phase: ReasoningPhase;
  summary: string;
  confidence?: ReasoningConfidence;
  evidenceRefs: string[];
};

export type Artifact = {
  id: string;
  name: string;
  kind?: string;
  url?: string;
  path?: string;
  runId?: string | null;
};

export type ArtifactRequest = {
  url: string;
  headers: Record<string, string>;
};

export type ModelOption = {
  id: string;
  label: string;
};

export type MessageMode = "auto" | "chat" | "search" | "document_analysis" | "deep_agent";
export type MessageInputScope = "auto" | "none" | "task_uploads";

export type MessageInputScopeOption = {
  value: MessageInputScope;
  label: string;
};

export type MessageRequestPayload = {
  content: string;
  message: string;
  model: string;
  mode: MessageMode;
  input_scope: MessageInputScope;
};

export type TaskRunRecord = {
  id: string;
  status: TaskStatus;
  message?: string;
  model?: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  needsInput?: Record<string, unknown> | null;
  artifactBasePath?: string;
  artifactNames: string[];
};

export type TaskSummary = {
  id: string;
  title: string;
  status: TaskStatus;
  model?: string;
  createdAt?: string;
  updatedAt?: string;
  runCount: number;
  lastMessageAt?: string;
};

export type TaskState = {
  id: string;
  status: TaskStatus;
  statusLabel: string;
  model?: string;
  runs: TaskRunRecord[];
  messages: ChatMessage[];
  logs: ExecutionLog[];
  artifacts: Artifact[];
  uploadCount: number;
  error?: string;
  needsInput?: Record<string, unknown> | null;
};

const KNOWN_STATUSES = new Set([
  "idle",
  "running",
  "complete",
  "cancelled",
  "failed",
  "needs_input",
  "interrupted",
]);

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function readString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

type BrowserLocation = {
  hostname?: string;
  protocol?: string;
};

const DEFAULT_API_BASE_URL = "http://localhost:8001";
const DEFAULT_API_PORT = "8001";
const DEFAULT_MESSAGE_MODE: MessageMode = "auto";
const DEFAULT_MESSAGE_INPUT_SCOPE: MessageInputScope = "auto";

export const MESSAGE_INPUT_SCOPE_OPTIONS: MessageInputScopeOption[] = [
  { value: "auto", label: "自动" },
  { value: "none", label: "不用文件" },
  { value: "task_uploads", label: "使用文件" },
];

function formatUrlHostname(hostname: string) {
  return hostname.includes(":") && !hostname.startsWith("[") ? `[${hostname}]` : hostname;
}

export function resolveApiBaseUrl(configuredApiBaseUrl?: string, location?: BrowserLocation) {
  const configured = configuredApiBaseUrl?.trim();
  if (configured && configured.toLowerCase() !== "auto") {
    return configured.replace(/\/+$/, "");
  }

  const browserLocation =
    location ?? (typeof window === "undefined" ? undefined : window.location);
  const hostname = browserLocation?.hostname?.trim();
  if (!hostname) {
    return DEFAULT_API_BASE_URL;
  }

  const protocol = browserLocation?.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${formatUrlHostname(hostname)}:${DEFAULT_API_PORT}`;
}

export function buildMessageRequestPayload(
  message: string,
  model: string,
  options: { mode?: MessageMode; inputScope?: MessageInputScope } = {},
): MessageRequestPayload {
  return {
    content: message,
    message,
    model,
    mode: options.mode ?? DEFAULT_MESSAGE_MODE,
    input_scope: options.inputScope ?? DEFAULT_MESSAGE_INPUT_SCOPE,
  };
}

function readOptionalString(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function readLevel(value: unknown) {
  const level = readString(value);
  return level === "info" || level === "success" || level === "warning" || level === "error"
    ? level
    : undefined;
}

function readReasoningPhase(value: unknown): ReasoningPhase | undefined {
  const phase = readString(value);
  return phase === "plan" ||
    phase === "observe" ||
    phase === "decide" ||
    phase === "next_step" ||
    phase === "final_summary" ||
    phase === "risk"
    ? phase
    : undefined;
}

function readReasoningConfidence(value: unknown): ReasoningConfidence | undefined {
  const confidence = readString(value);
  return confidence === "low" || confidence === "medium" || confidence === "high"
    ? confidence
    : undefined;
}

function readNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function formatValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value) ?? String(value);
}

const KNOWN_DISPLAY_TEXT: Record<string, string> = {
  "Additional input is required.": "需要补充输入。",
  "Agent event": "任务事件",
  "Request failed.": "请求失败。",
  "Task directory created": "任务目录已创建。",
  "User message accepted; workflow started": "已接收用户消息，工作流开始执行。",
  "Run input manifest recorded": "已记录本轮输入清单。",
  "Model provider configuration warning": "模型服务配置提醒。",
  "Simple chat response completed": "简单对话回复已完成。",
  "Task completed": "任务已完成。",
  "Task failed": "任务执行失败。",
  "Task cancelled; intermediate artifacts were kept": "任务已取消，已保留中间产物。",
  "Cancellation requested": "已请求取消任务。",
  "Cancellation ignored because the task is not running": "任务未在运行，已忽略取消请求。",
  "Cancellation ignored because the task is no longer running": "任务已不再运行，已忽略取消请求。",
  "Task was interrupted by backend startup or reload.": "后端启动或重载时中断了任务。",
  "Task was interrupted because no active runner owns it.": "任务已中断：当前没有运行器接管该任务。",
  "Upload Markdown or JSON files before starting a document-analysis task.": "开始文档分析任务前，请先上传 Markdown 或 JSON 文件。",
  "At least two uploaded bidder documents are required for comparison.": "至少需要上传两份投标人文档才能进行对比。",
  "Execution plan generated": "已生成执行计划。",
  "Concurrent sub-agent analysis started": "并发子任务分析已开始。",
  "Final report artifacts were written": "最终报告产物已写入。",
  "No evidence recorded": "未记录证据",
  "Invalid or missing access token": "访问令牌无效或缺失。",
};

const REQUEST_VALIDATION_ERROR_MESSAGE = "请求参数校验失败，请检查输入内容。";

export function translateKnownDisplayText(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return value;
  }

  const exact = KNOWN_DISPLAY_TEXT[trimmed];
  if (exact) {
    return exact;
  }

  if (trimmed === "unknown: missing") {
    return "未知状态：缺失";
  }

  const unknownStatus = trimmed.match(/^unknown: (.+)$/);
  if (unknownStatus) {
    return `未知状态：${unknownStatus[1]}`;
  }

  const uploaded = trimmed.match(/^Uploaded (.+)$/);
  if (uploaded) {
    return `已上传 ${uploaded[1]}`;
  }

  const retry = trimmed.match(/^Retrying (.+) after failure$/);
  if (retry) {
    return `${retry[1]} 失败后重试。`;
  }

  const subagentCompleted = trimmed.match(/^(subagent-[\w.-]+) completed (.+)$/);
  if (subagentCompleted) {
    return `${subagentCompleted[1]} 已完成 ${subagentCompleted[2]}。`;
  }

  const subagentCalled = trimmed.match(/^(subagent-[\w.-]+) called (.+)$/);
  if (subagentCalled) {
    return `${subagentCalled[1]} 调用了 ${subagentCalled[2]}。`;
  }

  const boundedPrompt = trimmed.match(/^(subagent-[\w.-]+) received a bounded prompt$/);
  if (boundedPrompt) {
    return `${boundedPrompt[1]} 已收到限定范围的分析提示。`;
  }

  const modelCall = trimmed.match(/^(subagent-[\w.-]+) requested model reasoning$/);
  if (modelCall) {
    return `${modelCall[1]} 已请求模型推理。`;
  }

  const modelResult = trimmed.match(/^(subagent-[\w.-]+) completed model reasoning$/);
  if (modelResult) {
    return `${modelResult[1]} 已完成模型推理。`;
  }

  const modelWarning = trimmed.match(
    /^(subagent-[\w.-]+) model reasoning failed; deterministic analysis continued$/,
  );
  if (modelWarning) {
    return `${modelWarning[1]} 模型推理失败，已继续执行确定性分析。`;
  }

  const modelFallback = trimmed.match(
    /^MODEL_FALLBACK: model reasoning failed \((.+)\); deterministic evidence extraction continued\.$/,
  );
  if (modelFallback) {
    return `模型推理失败（${modelFallback[1]}），已继续使用本地确定性证据提取。`;
  }

  if (trimmed.startsWith("MODEL_FALLBACK: DEEPSEEK_API_KEY is not configured")) {
    return "模型推理未启用：后端未配置 DEEPSEEK_API_KEY，本轮子任务已使用本地确定性证据引擎。";
  }

  if (trimmed.startsWith("DeepSeek is selected, but DEEPSEEK_API_KEY is not configured")) {
    return "已选择 DeepSeek，但后端 .env 未配置 DEEPSEEK_API_KEY。配置后可启用实时模型回复；文档分析仍可使用本地确定性分析器。";
  }

  return value;
}

function formatNeedsInputKey(key: string) {
  const labels: Record<string, string> = {
    minimum_bidder_documents: "至少投标人文档数",
    current_bidder_documents: "当前投标人文档数",
    required_file_type: "所需文件类型",
  };
  return labels[key] ?? key;
}

function formatNeedsInputValue(key: string, value: unknown) {
  if (key === "required_file_type" && value === "markdown_or_json") {
    return "Markdown 或 JSON 文件";
  }
  return formatValue(value);
}

export function formatNeedsInput(value: Record<string, unknown>) {
  const message = translateKnownDisplayText(readString(value.message, "Additional input is required."));
  const details = Object.entries(value)
    .filter(([key]) => key !== "message")
    .map(([key, entry]) => `${formatNeedsInputKey(key)}：${formatNeedsInputValue(key, entry)}`);
  return details.length > 0 ? `${message} ${details.join(" · ")}` : message;
}

function normalizeStatus(value: unknown): TaskStatus {
  const rawStatus = readString(value, "unknown");
  return KNOWN_STATUSES.has(rawStatus) ? (rawStatus as TaskStatus) : "unknown";
}

function statusLabel(status: TaskStatus, rawStatus: string) {
  return status === "unknown" ? `未知状态：${rawStatus || "缺失"}` : status;
}

function readOptionalNeedsInput(value: unknown) {
  return isRecord(value) ? value : null;
}

function maybeRunId(record: Record<string, unknown>) {
  const runId = readOptionalString(record.run_id ?? record.runId);
  return runId || null;
}

function normalizeReasoningTrace(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "reasoning_trace") {
    return undefined;
  }
  const agentId = readString(payload.agent_id);
  const phase = readReasoningPhase(payload.phase);
  const summary = readString(payload.summary).trim();
  if (!agentId || !phase || !summary) {
    return undefined;
  }
  const confidence = readReasoningConfidence(payload.confidence);
  const rawEvidenceRefs = Array.isArray(payload.evidence_refs) ? payload.evidence_refs : [];
  const evidenceRefs = rawEvidenceRefs.filter((value): value is string => typeof value === "string");
  return {
    agentId,
    phase,
    summary,
    confidence,
    evidenceRefs,
  };
}

function normalizeMessage(value: unknown, index: number): ChatMessage {
  const record = isRecord(value) ? value : {};
  const role = readString(record.role, "assistant");
  const level = readLevel(record.level);
  const rawContent = readString(record.content ?? record.text ?? record.message, "");
  return {
    id: readString(record.id, `message-${index}`),
    role: role === "user" || role === "system" ? role : "assistant",
    content: translateKnownDisplayText(rawContent),
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    runId: maybeRunId(record),
    level: level === "success" ? undefined : level,
  };
}

export function normalizeLog(value: unknown, index: number): ExecutionLog {
  const record = isRecord(value) ? value : {};
  const payload = isRecord(record.payload) ? record.payload : {};
  const level = readLevel(record.level ?? payload.level) ?? "info";
  const type = readOptionalString(record.type);
  const fallbackTitle = readString(record.message ?? record.event ?? record.type, "Agent event");
  const rawTitle = readString(record.title ?? fallbackTitle, fallbackTitle);
  const rawDetail = readOptionalString(record.detail ?? record.content);
  return {
    id: readString(record.id, `log-${index}`),
    type,
    title: translateKnownDisplayText(rawTitle),
    detail: rawDetail ? translateKnownDisplayText(rawDetail) : undefined,
    level,
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    runId: maybeRunId(record),
    reasoning: normalizeReasoningTrace(type, payload),
  };
}

function runIdFromArtifactUrl(url?: string) {
  if (!url) {
    return null;
  }
  const match = url.match(/\/runs\/([^/]+)\/artifacts\//);
  return match ? decodeURIComponent(match[1]) : null;
}

function normalizeArtifact(value: unknown, index: number): Artifact {
  const record = isRecord(value) ? value : {};
  const name = readString(record.name ?? record.title ?? record.filename, `产物 ${index + 1}`);
  const url = readOptionalString(record.url ?? record.href);
  const runId = maybeRunId(record) ?? runIdFromArtifactUrl(url);
  return {
    id: readString(record.id, runId ? `${runId}:${name}` : `artifact-${index}`),
    name,
    kind: readOptionalString(record.kind ?? record.type),
    url,
    path: readOptionalString(record.path),
    runId,
  };
}

function normalizeTaskRun(value: unknown, index: number): TaskRunRecord {
  const record = isRecord(value) ? value : {};
  const rawStatus = readString(record.status, "unknown");
  const rawNeedsInput = record.needs_input ?? record.needsInput;
  const rawArtifactNames = record.artifact_names ?? record.artifactNames;
  const id = readString(record.id ?? record.run_id ?? record.runId, `run-${index + 1}`);

  return {
    id,
    status: normalizeStatus(rawStatus),
    message: readOptionalString(record.message),
    model: readOptionalString(record.model),
    startedAt: readOptionalString(record.started_at ?? record.startedAt),
    completedAt: readOptionalString(record.completed_at ?? record.completedAt),
    error: readOptionalString(record.error),
    needsInput: readOptionalNeedsInput(rawNeedsInput),
    artifactBasePath: readOptionalString(record.artifact_base_path ?? record.artifactBasePath),
    artifactNames: Array.isArray(rawArtifactNames)
      ? rawArtifactNames.map((name) => readString(name)).filter(Boolean)
      : [],
  };
}

export function normalizeModelOption(value: unknown): ModelOption | null {
  const record = isRecord(value) ? value : {};
  const id = readString(record.id);
  if (!id) {
    return null;
  }
  return {
    id,
    label: readString(record.label, id),
  };
}

export function deriveConversationTitle(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "新对话";
  }

  const segmenter = (
    Intl as unknown as {
      Segmenter?: new (
        locale?: string,
        options?: { granularity: "grapheme" },
      ) => { segment(input: string): Iterable<{ segment: string }> };
    }
  ).Segmenter;

  const graphemes = segmenter
    ? Array.from(new segmenter("zh-CN", { granularity: "grapheme" }).segment(normalized), (item) => item.segment)
    : Array.from(normalized);

  return graphemes.slice(0, 5).join("") || "新对话";
}

export function normalizeTaskSummary(value: unknown): TaskSummary | null {
  const record = isRecord(value) ? value : {};
  const id = readString(record.id ?? record.task_id ?? record.taskId);
  if (!id) {
    return null;
  }

  const rawStatus = readString(record.status, "unknown");
  const firstUserMessage = readString(record.first_user_message ?? record.firstUserMessage);

  return {
    id,
    title: readString(record.title) || deriveConversationTitle(firstUserMessage) || `任务 ${id}`,
    status: normalizeStatus(rawStatus),
    model: readOptionalString(record.model),
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    updatedAt: readOptionalString(record.updated_at ?? record.updatedAt),
    runCount: readNumber(record.run_count ?? record.runCount),
    lastMessageAt: readOptionalString(record.last_message_at ?? record.lastMessageAt),
  };
}

export function normalizeTaskSummaries(value: unknown): TaskSummary[] {
  return Array.isArray(value)
    ? value.map(normalizeTaskSummary).filter((summary): summary is TaskSummary => summary !== null)
    : [];
}

export function normalizeTaskState(value: unknown, fallbackTaskId: string): TaskState {
  const record = isRecord(value) ? value : {};
  const rawRuns = Array.isArray(record.runs) ? record.runs : [];
  const rawMessages = Array.isArray(record.messages) ? record.messages : [];
  const rawLogs = Array.isArray(record.logs)
    ? record.logs
    : Array.isArray(record.events)
      ? record.events
      : [];
  const rawArtifacts = Array.isArray(record.artifacts) ? record.artifacts : [];
  const rawStatus = readString(record.status, "unknown");
  const status = normalizeStatus(rawStatus);
  const rawNeedsInput = record.needs_input ?? record.needsInput;
  const needsInput = readOptionalNeedsInput(rawNeedsInput);

  return {
    id: readString(record.id ?? record.task_id ?? record.taskId, fallbackTaskId),
    status,
    statusLabel: statusLabel(status, rawStatus),
    model: readOptionalString(record.model),
    runs: rawRuns.map(normalizeTaskRun),
    messages: rawMessages.map(normalizeMessage),
    logs: rawLogs.map(normalizeLog),
    artifacts: rawArtifacts.map(normalizeArtifact),
    uploadCount: readNumber(record.upload_count ?? record.uploadCount),
    error: readOptionalString(record.error)
      ? translateKnownDisplayText(readString(record.error))
      : undefined,
    needsInput,
  };
}

export function normalizeEventRecords(value: unknown): ExecutionLog[] {
  return Array.isArray(value) ? value.map(normalizeLog) : [];
}

export function buildArtifactRequest(
  artifact: Artifact,
  taskId: string,
  apiBaseUrl: string,
  accessToken = "",
): ArtifactRequest {
  let url: string;
  if (artifact.url) {
    url = artifact.url.startsWith("http") ? artifact.url : `${apiBaseUrl}${artifact.url}`;
  } else if (artifact.runId) {
    url = `${apiBaseUrl}/api/tasks/${taskId}/runs/${encodeURIComponent(
      artifact.runId,
    )}/artifacts/${encodeURIComponent(artifact.name)}`;
  } else if (artifact.path) {
    url = `${apiBaseUrl}/api/tasks/${taskId}/artifacts/open?path=${encodeURIComponent(artifact.path)}`;
  } else {
    url = `${apiBaseUrl}/api/tasks/${taskId}/artifacts/${artifact.id}`;
  }
  return {
    url,
    headers: accessToken ? { "X-MyAgent-Token": accessToken } : {},
  };
}

export function mergeExecutionLogs(
  existing: ExecutionLog[],
  incoming: ExecutionLog[],
): ExecutionLog[] {
  const seen = new Set(existing.map((log) => log.id));
  const merged = [...existing];
  incoming.forEach((log) => {
    if (!seen.has(log.id)) {
      seen.add(log.id);
      merged.push(log);
    }
  });
  return merged;
}

export function mergeTaskState(existing: TaskState, incoming: TaskState): TaskState {
  return {
    ...incoming,
    messages: incoming.messages.length > 0 ? incoming.messages : existing.messages,
    logs: mergeExecutionLogs(existing.logs, incoming.logs),
  };
}

export function isTaskActive(status: TaskStatus) {
  return status === "running";
}

export function backendDownMessage(apiBaseUrl: string) {
  return `无法连接后端服务（${apiBaseUrl}）。请确认后端已启动并监听 8001 端口，然后重试。`;
}

export function formatHttpErrorMessage(status: number, statusText: string, body: string) {
  const isValidationError = status === 422;
  if (!body) {
    return isValidationError ? REQUEST_VALIDATION_ERROR_MESSAGE : `${status} ${statusText}`;
  }

  try {
    const parsed: unknown = JSON.parse(body);
    if (isRecord(parsed) && typeof parsed.detail === "string") {
      return translateKnownDisplayText(parsed.detail);
    }
    if (isValidationError && isRecord(parsed) && Array.isArray(parsed.detail)) {
      return REQUEST_VALIDATION_ERROR_MESSAGE;
    }
  } catch {
    return isValidationError ? REQUEST_VALIDATION_ERROR_MESSAGE : translateKnownDisplayText(body);
  }
  return isValidationError ? REQUEST_VALIDATION_ERROR_MESSAGE : translateKnownDisplayText(body);
}

export function formatRequestFailure(caught: unknown, apiBaseUrl: string) {
  if (caught instanceof TypeError) {
    return backendDownMessage(apiBaseUrl);
  }
  return caught instanceof Error ? translateKnownDisplayText(caught.message) : "请求失败。";
}
