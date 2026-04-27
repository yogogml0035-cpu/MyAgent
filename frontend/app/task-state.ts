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
};

export type ExecutionLog = {
  id: string;
  type?: string;
  title: string;
  detail?: string;
  level?: "info" | "success" | "warning" | "error";
  createdAt?: string;
  runId?: string | null;
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

function readOptionalString(value: unknown) {
  return typeof value === "string" ? value : undefined;
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

export function formatNeedsInput(value: Record<string, unknown>) {
  const message = readString(value.message, "Additional input is required.");
  const details = Object.entries(value)
    .filter(([key]) => key !== "message")
    .map(([key, entry]) => `${key}: ${formatValue(entry)}`);
  return details.length > 0 ? `${message} ${details.join(" · ")}` : message;
}

function normalizeStatus(value: unknown): TaskStatus {
  const rawStatus = readString(value, "unknown");
  return KNOWN_STATUSES.has(rawStatus) ? (rawStatus as TaskStatus) : "unknown";
}

function statusLabel(status: TaskStatus, rawStatus: string) {
  return status === "unknown" ? `unknown: ${rawStatus || "missing"}` : status;
}

function readOptionalNeedsInput(value: unknown) {
  return isRecord(value) ? value : null;
}

function maybeRunId(record: Record<string, unknown>) {
  const runId = readOptionalString(record.run_id ?? record.runId);
  return runId || null;
}

function normalizeMessage(value: unknown, index: number): ChatMessage {
  const record = isRecord(value) ? value : {};
  const role = readString(record.role, "assistant");
  return {
    id: readString(record.id, `message-${index}`),
    role: role === "user" || role === "system" ? role : "assistant",
    content: readString(record.content ?? record.text ?? record.message, ""),
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    runId: maybeRunId(record),
  };
}

export function normalizeLog(value: unknown, index: number): ExecutionLog {
  const record = isRecord(value) ? value : {};
  const level = readString(record.level, "info");
  return {
    id: readString(record.id, `log-${index}`),
    type: readOptionalString(record.type),
    title: readString(record.title ?? record.event ?? record.type, "Agent event"),
    detail: readOptionalString(record.detail ?? record.message ?? record.content),
    level: level === "success" || level === "warning" || level === "error" ? level : "info",
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
    runId: maybeRunId(record),
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
  const name = readString(record.name ?? record.title ?? record.filename, `Artifact ${index + 1}`);
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
    error: readOptionalString(record.error),
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
  if (body) {
    try {
      const parsed: unknown = JSON.parse(body);
      if (isRecord(parsed) && typeof parsed.detail === "string") {
        return parsed.detail;
      }
    } catch {
      return body;
    }
    return body;
  }
  return `${status} ${statusText}`;
}

export function formatRequestFailure(caught: unknown, apiBaseUrl: string) {
  if (caught instanceof TypeError) {
    return backendDownMessage(apiBaseUrl);
  }
  return caught instanceof Error ? caught.message : "Request failed.";
}
