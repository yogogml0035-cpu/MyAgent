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
};

export type ExecutionLog = {
  id: string;
  title: string;
  detail?: string;
  level?: "info" | "success" | "warning" | "error";
  createdAt?: string;
};

export type Artifact = {
  id: string;
  name: string;
  kind?: string;
  url?: string;
  path?: string;
};

export type ArtifactRequest = {
  url: string;
  headers: Record<string, string>;
};

export type ModelOption = {
  id: string;
  label: string;
};

export type TaskState = {
  id: string;
  status: TaskStatus;
  statusLabel: string;
  model?: string;
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

function normalizeMessage(value: unknown, index: number): ChatMessage {
  const record = isRecord(value) ? value : {};
  const role = readString(record.role, "assistant");
  return {
    id: readString(record.id, `message-${index}`),
    role: role === "user" || role === "system" ? role : "assistant",
    content: readString(record.content ?? record.text ?? record.message, ""),
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
  };
}

export function normalizeLog(value: unknown, index: number): ExecutionLog {
  const record = isRecord(value) ? value : {};
  const level = readString(record.level, "info");
  return {
    id: readString(record.id, `log-${index}`),
    title: readString(record.title ?? record.event ?? record.type, "Agent event"),
    detail: readOptionalString(record.detail ?? record.message ?? record.content),
    level: level === "success" || level === "warning" || level === "error" ? level : "info",
    createdAt: readOptionalString(record.created_at ?? record.createdAt),
  };
}

function normalizeArtifact(value: unknown, index: number): Artifact {
  const record = isRecord(value) ? value : {};
  return {
    id: readString(record.id, `artifact-${index}`),
    name: readString(record.name ?? record.title ?? record.filename, `Artifact ${index + 1}`),
    kind: readOptionalString(record.kind ?? record.type),
    url: readOptionalString(record.url ?? record.href),
    path: readOptionalString(record.path),
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

export function normalizeTaskState(value: unknown, fallbackTaskId: string): TaskState {
  const record = isRecord(value) ? value : {};
  const rawMessages = Array.isArray(record.messages) ? record.messages : [];
  const rawLogs = Array.isArray(record.logs)
    ? record.logs
    : Array.isArray(record.events)
      ? record.events
      : [];
  const rawArtifacts = Array.isArray(record.artifacts) ? record.artifacts : [];
  const rawStatus = readString(record.status, "unknown");
  const status = KNOWN_STATUSES.has(rawStatus) ? (rawStatus as TaskStatus) : "unknown";
  const rawNeedsInput = record.needs_input ?? record.needsInput;
  const needsInput = isRecord(rawNeedsInput) ? rawNeedsInput : null;

  return {
    id: readString(record.id ?? record.task_id, fallbackTaskId),
    status,
    statusLabel: status === "unknown" ? `unknown: ${rawStatus || "missing"}` : status,
    model: readOptionalString(record.model),
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
