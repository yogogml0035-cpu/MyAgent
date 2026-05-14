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
  streaming?: boolean;
};

export type ExecutionLog = {
  id: string;
  seq?: number;
  type?: string;
  title: string;
  detail?: string;
  level?: "info" | "success" | "warning" | "error";
  createdAt?: string;
  runId?: string | null;
  live?: LiveEventMetadata;
  agentActivity?: AgentActivityTrace;
  fileAudit?: FileToolAuditTrace;
  reasoning?: ReasoningTrace;
  searchTrace?: SearchTrace;
  orchestration?: OrchestrationTrace;
  memoryContext?: MemoryContextTrace;
  answerStream?: AssistantAnswerStreamTrace;
  thinkingStream?: AssistantThinkingStreamTrace;
  rawRecord?: Record<string, unknown>;
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

export type AgentActivityKind = "lifecycle" | "progress";
export type AgentActivityPhase =
  | "planning"
  | "reasoning"
  | "tool_use"
  | "file_operation"
  | "finalizing";
export type AgentActivityStatus = "started" | "running" | "completed" | "failed" | "skipped";

export type AgentActivityTrace = {
  schemaVersion: 1;
  source: "deepagents";
  activityKind: AgentActivityKind;
  phase: AgentActivityPhase;
  status: AgentActivityStatus;
  title: string;
  summary: string;
  iterationIndex?: number;
  agentId?: string;
  parentAgentId?: string;
  taskLabel?: string;
  sourceEventId?: string;
  toolName?: string;
  parameterSummary?: string;
  resultSummary?: string;
  subgraphPath: string[];
  relatedEventId?: string;
  truncated: boolean;
};

export type FileToolAuditTrace = {
  toolName?: string;
  operation: string;
  status: string;
  virtualPath: string;
  source?: string;
  bytes?: number;
  sha256?: string;
  reason?: string;
  promotedArtifactId?: string;
  partial?: boolean;
};

export type SearchTraceKind = "tool_call" | "tool_result" | "synthesis";

export type SearchSourceTrace = {
  title: string;
  url?: string;
  snippet?: string;
};

export type SearchTrace = {
  kind: SearchTraceKind;
  toolName?: string;
  parameterSummary?: string;
  resultSummary?: string;
  resultCount?: number;
  sourceCount?: number;
  sources: SearchSourceTrace[];
  usedModel?: boolean;
  warningCode?: string;
};

export type MemoryContextTrace = {
  schemaVersion: 1;
  kind: "conversation" | "long_term";
  summaryPreview?: string;
  memoryPreviews: string[];
  recentMessageCount?: number;
  cachedToolResultCount?: number;
  memoryCount?: number;
  userId?: string;
};

export type AssistantAnswerStreamTrace = {
  schemaVersion: 1;
  streamIndex: number;
  content: string;
  isSubgraph?: boolean;
};

export type AssistantThinkingStreamTrace = {
  schemaVersion: 1;
  streamIndex: number;
  content: string;
  isSubgraph?: boolean;
};

export type LiveEventKind = "think" | "tool_call" | "tool_result" | "answer_status" | "status";
export type LiveEventStage =
  | "preparing"
  | "thinking"
  | "analyzing_intent"
  | "selecting_tool"
  | "using_tool"
  | "reading_input"
  | "organizing_state"
  | "generating_answer"
  | "completed"
  | "needs_input"
  | "failed";
export type LiveResultStatus = "success" | "empty" | "failed" | "cancelled" | "skipped";
export type LiveParameterItem = {
  key: string;
  value: string | number | boolean;
  truncated?: boolean;
};
export type LiveEventMetadata = {
  schemaVersion: 1;
  kind: LiveEventKind;
  stage?: LiveEventStage;
  agentName?: string;
  toolName?: string;
  toolLabel?: string;
  toolCallId?: string;
  displayText?: string;
  diagnosticLabel?: string;
  parameterItems: LiveParameterItem[];
  resultStatus?: LiveResultStatus;
  resultCount?: number;
};

export type OrchestrationTrace = {
  schemaVersion: 1;
  strategy: "single_agent" | "multi_agent";
  reasonCode?: string;
  chosenProfileId?: string;
  chosenProfileLabel?: string;
  plannedSubagents: string[];
  messageClass?: string;
  route?: string;
  bidderCount?: number;
  decisionSummary?: string;
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
  available?: boolean;
};

export type MessageMode = "auto" | "chat" | "analysis";

export type MessageRequestPayload = {
  content: string;
  message: string;
  model: string;
  mode: MessageMode;
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
  activeRunId?: string | null;
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
  "unknown",
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
const UNTRUSTED_ARTIFACT_URL_MESSAGE = "产物 URL 不受信任，已阻止访问。";

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
  options: { mode?: MessageMode } = {},
): MessageRequestPayload {
  return {
    content: message,
    message,
    model,
    mode: options.mode ?? DEFAULT_MESSAGE_MODE,
  };
}

export function isModelRunnable(option?: ModelOption | null) {
  return option?.available !== false;
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

function readAgentActivityKind(value: unknown): AgentActivityKind | undefined {
  const kind = readString(value);
  return kind === "lifecycle" || kind === "progress" ? kind : undefined;
}

function readAgentActivityPhase(value: unknown): AgentActivityPhase | undefined {
  const phase = readString(value);
  return phase === "planning" ||
    phase === "reasoning" ||
    phase === "tool_use" ||
    phase === "file_operation" ||
    phase === "finalizing"
    ? phase
    : undefined;
}

function readAgentActivityStatus(value: unknown): AgentActivityStatus | undefined {
  const status = readString(value);
  return status === "started" ||
    status === "running" ||
    status === "completed" ||
    status === "failed" ||
    status === "skipped"
    ? status
    : undefined;
}

function readNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readOptionalNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function readOptionalBoundedInteger(value: unknown, min: number, max: number) {
  const number = readOptionalNumber(value);
  if (number === undefined || !Number.isInteger(number) || number < min || number > max) {
    return undefined;
  }
  return number;
}

function readLiveKind(value: unknown): LiveEventKind | undefined {
  const kind = readString(value);
  return kind === "think" ||
    kind === "tool_call" ||
    kind === "tool_result" ||
    kind === "answer_status" ||
    kind === "status"
    ? kind
    : undefined;
}

function readLiveStage(value: unknown): LiveEventStage | undefined {
  const stage = readString(value);
  return stage === "preparing" ||
    stage === "thinking" ||
    stage === "analyzing_intent" ||
    stage === "selecting_tool" ||
    stage === "using_tool" ||
    stage === "reading_input" ||
    stage === "organizing_state" ||
    stage === "generating_answer" ||
    stage === "completed" ||
    stage === "needs_input" ||
    stage === "failed"
    ? stage
    : undefined;
}

function readLiveResultStatus(value: unknown): LiveResultStatus | undefined {
  const status = readString(value);
  return status === "success" ||
    status === "empty" ||
    status === "failed" ||
    status === "cancelled" ||
    status === "skipped"
    ? status
    : undefined;
}

function normalizeLiveParameterValue(value: unknown): string | number | boolean | undefined {
  if (typeof value === "string") {
    return readBoundedString(value, 160);
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "boolean") {
    return value;
  }
  return undefined;
}

function normalizeLiveParameterItems(value: unknown): LiveParameterItem[] | undefined {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    return undefined;
  }

  const items: LiveParameterItem[] = [];
  for (const entry of value.slice(0, 8)) {
    if (!isRecord(entry)) {
      return undefined;
    }
    const key = readBoundedString(entry.key, 60);
    const parameterValue = normalizeLiveParameterValue(entry.value);
    if (!key || parameterValue === undefined) {
      return undefined;
    }
    items.push({
      key,
      value: parameterValue,
      truncated: readOptionalBoolean(entry.truncated),
    });
  }
  return items;
}

function readOptionalBoolean(value: unknown) {
  return typeof value === "boolean" ? value : undefined;
}

function truncateDisplayText(value: string, maxChars: number) {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

function readBoundedString(value: unknown, maxChars: number) {
  const text = readString(value).trim();
  return text ? truncateDisplayText(text, maxChars) : undefined;
}

function readBoundedContent(value: unknown, maxChars: number) {
  const text = readString(value);
  return text ? truncateDisplayText(text, maxChars) : undefined;
}

function readBoundedStringList(value: unknown, maxItems: number, maxChars: number) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((entry): entry is string => typeof entry === "string")
    .map((entry) => truncateDisplayText(entry.trim(), maxChars))
    .filter(Boolean)
    .slice(0, maxItems);
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
  "Context loaded": "已载入会话上下文。",
  "Memory recalled": "已载入长期记忆。",
  "Task failed": "任务执行失败。",
  "Task cancelled; intermediate artifacts were kept": "任务已取消，已保留中间产物。",
  "Cancellation requested": "已请求取消任务。",
  "Cancellation ignored because the task is not running": "任务未在运行，已忽略取消请求。",
  "Cancellation ignored because the task is no longer running": "任务已不再运行，已忽略取消请求。",
  "Task was interrupted by backend startup or reload.": "后端启动或重载时中断了任务。",
  "Task was interrupted because no active runner owns it.": "任务已中断：当前没有运行器接管该任务。",
  "Upload Markdown or JSON files before starting a document-analysis task.": "开始文档分析任务前，请先上传 Markdown、JSON、TXT、DOCX、XLSX 或 XLSM 文件。",
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
    return "Markdown、JSON、TXT、DOCX、XLSX 或 XLSM 文件";
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

function normalizeAgentActivity(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "deep_agent_activity") {
    return undefined;
  }

  const schemaVersion = payload.schema_version ?? payload.schemaVersion;
  const source = readString(payload.source);
  const activityKind = readAgentActivityKind(payload.activity_kind ?? payload.activityKind);
  const phase = readAgentActivityPhase(payload.phase);
  const status = readAgentActivityStatus(payload.status);
  const title = readBoundedString(payload.title, 120);
  const summary = readBoundedString(payload.summary, 1000);

  if (schemaVersion !== 1 || source !== "deepagents" || !activityKind || !phase || !status || !title || !summary) {
    return undefined;
  }

  return {
    schemaVersion: 1 as const,
    source: "deepagents" as const,
    activityKind,
    phase,
    status,
    title,
    summary,
    iterationIndex: readOptionalBoundedInteger(
      payload.iteration_index ?? payload.iterationIndex,
      0,
      9999,
    ),
    agentId: readBoundedString(payload.agent_id ?? payload.agentId, 120),
    parentAgentId: readBoundedString(payload.parent_agent_id ?? payload.parentAgentId, 120),
    taskLabel: readBoundedString(payload.task_label ?? payload.taskLabel, 160),
    sourceEventId: readBoundedString(payload.source_event_id ?? payload.sourceEventId, 160),
    toolName: readBoundedString(payload.tool_name ?? payload.toolName, 80),
    parameterSummary: readBoundedString(payload.parameter_summary ?? payload.parameterSummary, 240),
    resultSummary: readBoundedString(payload.result_summary ?? payload.resultSummary, 360),
    subgraphPath: readBoundedStringList(payload.subgraph_path ?? payload.subgraphPath, 8, 80),
    relatedEventId: readBoundedString(payload.related_event_id ?? payload.relatedEventId, 160),
    truncated: readOptionalBoolean(payload.truncated) ?? false,
  };
}

function normalizeFileToolAudit(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "file_tool_audit") {
    return undefined;
  }

  const operation = readBoundedString(payload.op ?? payload.operation, 80);
  const status = readBoundedString(payload.status, 80);
  const virtualPath = readBoundedString(
    payload.virtual_path ?? payload.relative_path ?? payload.requested_path,
    240,
  );

  if (!operation || !status || !virtualPath) {
    return undefined;
  }

  return {
    toolName: readBoundedString(payload.tool_name ?? payload.tool, 80),
    operation,
    status,
    virtualPath,
    source: readBoundedString(payload.source, 80),
    bytes: readOptionalNumber(payload.bytes),
    sha256: readBoundedString(payload.sha256, 80),
    reason: readBoundedString(payload.reason, 240),
    promotedArtifactId: readBoundedString(payload.promoted_artifact_id ?? payload.promotedArtifactId, 160),
    partial: readOptionalBoolean(payload.partial),
  };
}

function normalizeSearchSources(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .map((source) => ({
      title: readBoundedString(source.title, 120) ?? "未命名来源",
      url: readBoundedString(source.url, 240),
      snippet: readBoundedString(source.snippet, 260),
    }))
    .slice(0, 5);
}

function normalizeSearchParameterSummary(value: unknown) {
  if (!isRecord(value)) {
    return readBoundedString(value, 240);
  }
  const query = readBoundedString(value.query, 160);
  const maxResults = readOptionalNumber(value.max_results ?? value.maxResults);
  const useUploads = readOptionalBoolean(value.use_uploads ?? value.useUploads);
  const parts = [
    query ? `query=${query}` : "",
    typeof maxResults === "number" ? `max_results=${maxResults}` : "",
    typeof useUploads === "boolean" ? `use_uploads=${useUploads}` : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join("; ") : undefined;
}

function normalizeSearchTrace(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "search_tool_call" && type !== "search_tool_result" && type !== "search_synthesis_completed") {
    return undefined;
  }
  const sources = normalizeSearchSources(payload.sources);
  const warningCode = readBoundedString(payload.warning_code ?? payload.warningCode, 80);
  if (type === "search_tool_call") {
    return {
      kind: "tool_call" as const,
      toolName: readBoundedString(payload.tool_name ?? payload.toolName, 80),
      parameterSummary: normalizeSearchParameterSummary(payload.parameter_summary ?? payload.parameterSummary),
      sources,
      warningCode,
    };
  }
  if (type === "search_tool_result") {
    const resultCount = readOptionalNumber(payload.result_count ?? payload.resultCount);
    return {
      kind: "tool_result" as const,
      toolName: readBoundedString(payload.tool_name ?? payload.toolName, 80),
      resultSummary:
        typeof resultCount === "number"
          ? `结果数量：${resultCount}`
          : readBoundedString(payload.result_summary ?? payload.resultSummary, 240),
      resultCount,
      sourceCount: sources.length,
      sources,
      warningCode,
    };
  }
  const sourceCount = readOptionalNumber(payload.source_count ?? payload.sourceCount);
  const usedModel = readOptionalBoolean(payload.used_model ?? payload.usedModel);
  return {
    kind: "synthesis" as const,
    resultSummary: [
      typeof usedModel === "boolean" ? `模型合成：${usedModel ? "已使用" : "未使用"}` : "",
      typeof sourceCount === "number" ? `来源数：${sourceCount}` : "",
    ].filter(Boolean).join("；") || undefined,
    sourceCount,
    sources,
    usedModel,
    warningCode,
  };
}

function normalizeLiveMetadata(payload: Record<string, unknown>) {
  const live = payload.live;
  if (live === undefined) {
    return undefined;
  }
  if (!isRecord(live)) {
    return undefined;
  }

  const schemaVersion = live.schema_version ?? live.schemaVersion;
  const kind = readLiveKind(live.kind);
  const parameterItems = normalizeLiveParameterItems(
    live.parameter_items ?? live.parameterItems,
  );

  if (schemaVersion !== 1 || !kind || !parameterItems) {
    return undefined;
  }

  return {
    schemaVersion: 1 as const,
    kind,
    stage: readLiveStage(live.stage),
    agentName: readBoundedString(live.agent_name ?? live.agentName, 120),
    toolName: readBoundedString(live.tool_name ?? live.toolName, 80),
    toolLabel: readBoundedString(live.tool_label ?? live.toolLabel, 80),
    toolCallId: readBoundedString(live.tool_call_id ?? live.toolCallId, 160),
    displayText: readBoundedString(live.display_text ?? live.displayText, 160),
    diagnosticLabel: readBoundedString(live.diagnostic_label ?? live.diagnosticLabel, 160),
    parameterItems,
    resultStatus: readLiveResultStatus(live.result_status ?? live.resultStatus),
    resultCount: readOptionalBoundedInteger(live.result_count ?? live.resultCount, 0, 9999),
  };
}

function normalizeOrchestrationTrace(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "orchestration_decision") {
    return undefined;
  }
  const schemaVersion = payload.schema_version ?? payload.schemaVersion;
  const strategy = readString(payload.strategy);
  const normalizedStrategy: OrchestrationTrace["strategy"] | undefined =
    strategy === "single_agent" || strategy === "multi_agent" ? strategy : undefined;
  if (schemaVersion !== 1 || !normalizedStrategy) {
    return undefined;
  }
  return {
    schemaVersion: 1 as const,
    strategy: normalizedStrategy,
    reasonCode: readBoundedString(payload.reason_code ?? payload.reasonCode, 120),
    chosenProfileId: readBoundedString(payload.chosen_profile_id ?? payload.chosenProfileId, 80),
    chosenProfileLabel: readBoundedString(
      payload.chosen_profile_label ?? payload.chosenProfileLabel,
      120,
    ),
    plannedSubagents: readBoundedStringList(
      payload.planned_subagents ?? payload.plannedSubagents,
      8,
      80,
    ),
    messageClass: readBoundedString(payload.message_class ?? payload.messageClass, 80),
    route: readBoundedString(payload.route, 80),
    bidderCount: readOptionalBoundedInteger(payload.bidder_count ?? payload.bidderCount, 0, 9999),
    decisionSummary: readBoundedString(
      payload.decision_summary ?? payload.decisionSummary,
      360,
    ),
  };
}

function normalizeMemoryContextTrace(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "context_loaded" && type !== "memory_recalled") {
    return undefined;
  }
  const schemaVersion = payload.schema_version ?? payload.schemaVersion;
  if (schemaVersion !== 1) {
    return undefined;
  }
  if (type === "context_loaded") {
    return {
      schemaVersion: 1 as const,
      kind: "conversation" as const,
      summaryPreview: readBoundedString(payload.summary_preview ?? payload.summaryPreview, 320),
      memoryPreviews: readBoundedStringList(
        payload.cached_tool_previews ?? payload.cachedToolPreviews,
        3,
        220,
      ),
      recentMessageCount: readOptionalBoundedInteger(
        payload.recent_message_count ?? payload.recentMessageCount,
        0,
        200,
      ),
      cachedToolResultCount: readOptionalBoundedInteger(
        payload.cached_tool_result_count ?? payload.cachedToolResultCount,
        0,
        20,
      ),
    };
  }
  return {
    schemaVersion: 1 as const,
    kind: "long_term" as const,
    memoryPreviews: readBoundedStringList(payload.memory_previews ?? payload.memoryPreviews, 5, 240),
    memoryCount: readOptionalBoundedInteger(payload.memory_count ?? payload.memoryCount, 0, 100),
    userId: readBoundedString(payload.user_id ?? payload.userId, 120),
  };
}

function normalizeAssistantAnswerStream(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "assistant_answer_delta") {
    return undefined;
  }
  const schemaVersion = payload.schema_version ?? payload.schemaVersion;
  const content = readBoundedContent(payload.content, 8000);
  if (schemaVersion !== 1 || !content) {
    return undefined;
  }
  return {
    schemaVersion: 1 as const,
    streamIndex: readOptionalBoundedInteger(
      payload.stream_index ?? payload.streamIndex,
      0,
      9999,
    ) ?? 0,
    content,
    isSubgraph: readOptionalBoolean(payload.is_subgraph ?? payload.isSubgraph) ?? false,
  };
}

function normalizeAssistantThinkingStream(type: string | undefined, payload: Record<string, unknown>) {
  if (type !== "assistant_thinking_delta") {
    return undefined;
  }
  const schemaVersion = payload.schema_version ?? payload.schemaVersion;
  const content = readBoundedContent(payload.content, 8000);
  if (schemaVersion !== 1 || !content) {
    return undefined;
  }
  return {
    schemaVersion: 1 as const,
    streamIndex: readOptionalBoundedInteger(
      payload.stream_index ?? payload.streamIndex,
      0,
      9999,
    ) ?? 0,
    content,
    isSubgraph: readOptionalBoolean(payload.is_subgraph ?? payload.isSubgraph) ?? false,
  };
}

function normalizeMessage(value: unknown, index: number): ChatMessage {
  const record = isRecord(value) ? value : {};
  const role = readString(record.role, "assistant");
  const normalizedRole = role === "user" || role === "system" ? role : "assistant";
  const level = readLevel(record.level);
  const rawContent = readString(record.content ?? record.text ?? record.message, "");
  return {
    id: readString(record.id, `message-${index}`),
    role: normalizedRole,
    content: normalizedRole === "user" ? rawContent : translateKnownDisplayText(rawContent),
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
  const log: ExecutionLog = {
    id: readString(record.id, `log-${index}`),
    seq: readOptionalBoundedInteger(record.seq, -9999, 999999),
    type,
    title: translateKnownDisplayText(rawTitle),
    detail: rawDetail ? translateKnownDisplayText(rawDetail) : undefined,
    level,
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    runId: maybeRunId(record),
    live: normalizeLiveMetadata(payload),
    agentActivity: normalizeAgentActivity(type, payload),
    fileAudit: normalizeFileToolAudit(type, payload),
    reasoning: normalizeReasoningTrace(type, payload),
    searchTrace: normalizeSearchTrace(type, payload),
    orchestration: normalizeOrchestrationTrace(type, payload),
    memoryContext: normalizeMemoryContextTrace(type, payload),
    answerStream: normalizeAssistantAnswerStream(type, payload),
    thinkingStream: normalizeAssistantThinkingStream(type, payload),
  };
  Object.defineProperty(log, "rawRecord", {
    value: record,
    enumerable: false,
    configurable: true,
  });
  return log;
}

function runIdFromArtifactUrl(url?: string) {
  if (!url) {
    return null;
  }
  const match = url.match(/\/runs\/([^/]+)\/artifacts\//);
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
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
    available: readOptionalBoolean(record.available),
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

  return graphemes.slice(0, 10).join("") || "新对话";
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
    activeRunId: readOptionalString(record.active_run_id ?? record.activeRunId),
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
  const apiOrigin = trustedApiOrigin(apiBaseUrl);
  let url: URL;
  if (artifact.url) {
    url = new URL(artifact.url, `${apiOrigin}/`);
    assertTrustedArtifactUrl(url, artifact, taskId, apiOrigin);
  } else if (artifact.runId) {
    url = new URL(`/api/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(
      artifact.runId,
    )}/artifacts/${encodeURIComponent(artifact.name)}`, apiOrigin);
  } else {
    url = new URL(
      `/api/tasks/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifact.name)}`,
      apiOrigin,
    );
  }
  return {
    url: url.toString(),
    headers: accessToken ? { "X-MyAgent-Token": accessToken } : {},
  };
}

type TrustedArtifactPath = {
  taskId: string;
  runId?: string;
  artifactName: string;
};

function trustedApiOrigin(apiBaseUrl: string) {
  try {
    const url = new URL(apiBaseUrl, DEFAULT_API_BASE_URL);
    if (url.protocol === "http:" || url.protocol === "https:") {
      return url.origin;
    }
  } catch {
    // Fall through to a consistent user-facing validation error.
  }
  throw new Error(UNTRUSTED_ARTIFACT_URL_MESSAGE);
}

function assertTrustedArtifactUrl(
  url: URL,
  artifact: Artifact,
  taskId: string,
  apiOrigin: string,
) {
  const path = parseTrustedArtifactPath(url.pathname);
  if (
    url.origin !== apiOrigin ||
    url.search ||
    url.hash ||
    !path ||
    path.taskId !== taskId ||
    (path.runId && artifact.runId && path.runId !== artifact.runId) ||
    path.artifactName !== artifact.name
  ) {
    throw new Error(UNTRUSTED_ARTIFACT_URL_MESSAGE);
  }
}

function parseTrustedArtifactPath(pathname: string): TrustedArtifactPath | null {
  const segments = pathname.split("/").filter(Boolean);

  if (
    segments.length === 5 &&
    segments[0] === "api" &&
    segments[1] === "tasks" &&
    segments[3] === "artifacts"
  ) {
    const taskId = decodeSafePathSegment(segments[2]);
    const artifactName = decodeSafePathSegment(segments[4]);
    return taskId && artifactName ? { taskId, artifactName } : null;
  }

  if (
    segments.length === 7 &&
    segments[0] === "api" &&
    segments[1] === "tasks" &&
    segments[3] === "runs" &&
    segments[5] === "artifacts"
  ) {
    const taskId = decodeSafePathSegment(segments[2]);
    const runId = decodeSafePathSegment(segments[4]);
    const artifactName = decodeSafePathSegment(segments[6]);
    return taskId && runId && artifactName ? { taskId, runId, artifactName } : null;
  }

  return null;
}

function decodeSafePathSegment(segment: string) {
  if (!segment || /%2f|%5c/i.test(segment)) {
    return null;
  }
  try {
    const decoded = decodeURIComponent(segment);
    if (
      !decoded ||
      decoded === "." ||
      decoded === ".." ||
      decoded.includes("/") ||
      decoded.includes("\\") ||
      decoded.includes("\0")
    ) {
      return null;
    }
    return decoded;
  } catch {
    return null;
  }
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
