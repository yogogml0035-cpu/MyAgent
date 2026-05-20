import {
  type Artifact,
  type ExecutionLog,
  type ModelOption,
  type SkillOption,
  type TaskState,
  type TaskSummary,
  buildArtifactRequest,
  buildMessageRequestPayload,
  formatHttpErrorMessage,
  formatRequestFailure,
  isRecord,
  normalizeEventRecords,
  normalizeModelOption,
  normalizeSkillOptions,
  normalizeTaskState,
  normalizeTaskSummaries,
  readString,
  resolveApiBaseUrl,
} from "../app/task-state";

export const TASK_API_BASE_URL = resolveApiBaseUrl(
  process.env.NEXT_PUBLIC_MYAGENT_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL,
);

export const TASK_API_ACCESS_TOKEN =
  process.env.NEXT_PUBLIC_MYAGENT_TOKEN || process.env.NEXT_PUBLIC_AGENT_CHAT_TOKEN || "";

export async function requestTaskJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${TASK_API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(TASK_API_ACCESS_TOKEN ? { "X-MyAgent-Token": TASK_API_ACCESS_TOKEN } : {}),
        ...init?.headers,
      },
    });
  } catch (caught) {
    throw new Error(formatRequestFailure(caught, TASK_API_BASE_URL));
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatHttpErrorMessage(response.status, response.statusText, text));
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("后端返回了非预期的响应格式。");
  }
}

export function formatTaskApiFailure(caught: unknown) {
  return formatRequestFailure(caught, TASK_API_BASE_URL);
}

export async function fetchModelOptions(fallbackOptions: ModelOption[]) {
  const response = await requestTaskJson<unknown>("/api/models");
  if (!Array.isArray(response)) {
    return fallbackOptions;
  }

  const options = response
    .map(normalizeModelOption)
    .filter((option): option is ModelOption => option !== null);

  return options.length > 0 ? options : fallbackOptions;
}

export async function fetchSkillOptions(): Promise<SkillOption[]> {
  return normalizeSkillOptions(await requestTaskJson<unknown>("/api/skills"));
}

export async function fetchTaskSummaries(): Promise<TaskSummary[]> {
  return normalizeTaskSummaries(await requestTaskJson<unknown>("/api/tasks"));
}

export async function createTask(model: string): Promise<{ id: string; state: TaskState }> {
  const created = await requestTaskJson<unknown>("/api/tasks", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
  const record = isRecord(created) ? created : {};
  const id = readString(record.id ?? record.task_id);

  if (!id) {
    throw new Error("后端没有返回任务 ID。");
  }

  return { id, state: normalizeTaskState(created, id) };
}

export async function fetchTask(id: string, options: { includeEvents?: boolean } = {}) {
  const query = options.includeEvents === false ? "?include_events=false" : "";
  return normalizeTaskState(
    await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}${query}`),
    id,
  );
}

export async function renameTask(id: string, title: string) {
  return normalizeTaskState(
    await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
    id,
  );
}

export async function deleteTask(id: string) {
  let response: Response;
  try {
    response = await fetch(`${TASK_API_BASE_URL}/api/tasks/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: {
        ...(TASK_API_ACCESS_TOKEN ? { "X-MyAgent-Token": TASK_API_ACCESS_TOKEN } : {}),
      },
    });
  } catch (caught) {
    throw new Error(formatRequestFailure(caught, TASK_API_BASE_URL));
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatHttpErrorMessage(response.status, response.statusText, text));
  }
}

export async function fetchTaskEvents(id: string, afterId?: string): Promise<ExecutionLog[]> {
  const query = afterId ? `?after_id=${encodeURIComponent(afterId)}` : "";
  return normalizeEventRecords(
    await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}/events${query}`),
  );
}

export async function uploadTaskFiles(id: string, files: File[]) {
  if (files.length === 0) {
    return;
  }

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}/files`, {
    method: "POST",
    body: formData,
  });
}

export async function postTaskMessage(
  id: string,
  content: string,
  model: string,
  skills: readonly string[] = [],
) {
  await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    body: JSON.stringify(buildMessageRequestPayload(content, model, { skills })),
  });
}

export async function cancelTask(id: string) {
  await requestTaskJson<unknown>(`/api/tasks/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
  });
}

export function createTaskEventSource(
  taskId: string,
  onEvent: (event: MessageEvent) => void,
  onError?: (error: Event) => void,
): EventSource {
  const url = new URL(
    `${TASK_API_BASE_URL}/api/tasks/${encodeURIComponent(taskId)}/stream`,
    window.location.origin,
  );

  if (TASK_API_ACCESS_TOKEN) {
    url.searchParams.set("token", TASK_API_ACCESS_TOKEN);
  }

  const es = new EventSource(url.toString());
  es.onmessage = onEvent;
  if (onError) {
    es.onerror = onError;
  }
  return es;
}

export async function fetchArtifactBlob(artifact: Artifact, taskId: string) {
  const request = buildArtifactRequest(
    artifact,
    taskId,
    TASK_API_BASE_URL,
    TASK_API_ACCESS_TOKEN,
  );
  let response: Response;

  try {
    response = await fetch(request.url, { headers: request.headers });
  } catch (caught) {
    throw new Error(formatRequestFailure(caught, TASK_API_BASE_URL));
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatHttpErrorMessage(response.status, response.statusText, text));
  }

  return response.blob();
}
