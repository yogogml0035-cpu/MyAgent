"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  type Artifact,
  type ChatMessage,
  type ExecutionLog,
  type ModelOption,
  type TaskState,
  type TaskStatus,
  buildArtifactRequest,
  formatNeedsInput,
  isRecord,
  isTaskActive,
  mergeExecutionLogs,
  normalizeEventRecords,
  normalizeModelOption,
  normalizeTaskState,
  readString,
} from "./task-state";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_MYAGENT_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";
const API_ACCESS_TOKEN =
  process.env.NEXT_PUBLIC_MYAGENT_TOKEN || process.env.NEXT_PUBLIC_AGENT_CHAT_TOKEN || "";
const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    id: "deepseek-reasoner",
    label: "DeepSeek Reasoner",
  },
];

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(API_ACCESS_TOKEN ? { "X-MyAgent-Token": API_ACCESS_TOKEN } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export default function Home() {
  const [taskId, setTaskId] = useState<string>("");
  const [status, setStatus] = useState<TaskStatus>("idle");
  const [statusLabel, setStatusLabel] = useState("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [logs, setLogs] = useState<ExecutionLog[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [uploadCount, setUploadCount] = useState(0);
  const [taskModel, setTaskModel] = useState("");
  const [backendError, setBackendError] = useState("");
  const [needsInput, setNeedsInput] = useState<Record<string, unknown> | null>(null);
  const [input, setInput] = useState("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS);
  const [model, setModel] = useState(DEFAULT_MODEL_OPTIONS[0].id);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string>("");

  const canSend = input.trim().length > 0 || selectedFiles.length > 0;
  const activeTask = isTaskActive(status);

  const reportArtifacts = useMemo(
    () =>
      artifacts.filter((artifact) => {
        const marker = `${artifact.name} ${artifact.kind ?? ""} ${artifact.path ?? ""}`.toLowerCase();
        return marker.includes("report") || marker.includes(".html");
      }),
    [artifacts],
  );

  const applyTaskState = useCallback((state: TaskState, mergeLogs = false) => {
    setTaskId(state.id);
    setStatus(state.status);
    setStatusLabel(state.statusLabel);
    setMessages((current) => (mergeLogs && state.messages.length === 0 ? current : state.messages));
    setLogs((current) => (mergeLogs ? mergeExecutionLogs(current, state.logs) : state.logs));
    setArtifacts(state.artifacts);
    setUploadCount(state.uploadCount);
    setTaskModel(state.model ?? "");
    setBackendError(state.error ?? "");
    setNeedsInput(state.needsInput ?? null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadModels() {
      const response = await requestJson<unknown>("/api/models");
      if (!Array.isArray(response)) {
        return;
      }
      const options = response
        .map(normalizeModelOption)
        .filter((option): option is ModelOption => option !== null);
      if (cancelled || options.length === 0) {
        return;
      }
      setModelOptions(options);
      setModel((current) => (options.some((option) => option.id === current) ? current : options[0].id));
    }

    void loadModels().catch(() => {
      if (!cancelled) {
        setModelOptions(DEFAULT_MODEL_OPTIONS);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const ensureTask = useCallback(async () => {
    if (taskId) {
      return taskId;
    }

    const created = await requestJson<unknown>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ model }),
    });
    const record = isRecord(created) ? created : {};
    const createdTaskId = readString(record.id ?? record.task_id);

    if (!createdTaskId) {
      throw new Error("Backend did not return a task id.");
    }

    applyTaskState(normalizeTaskState(created, createdTaskId));
    return createdTaskId;
  }, [applyTaskState, model, taskId]);

  const refreshTask = useCallback(
    async (id = taskId) => {
      if (!id) {
        return;
      }

      const state = normalizeTaskState(await requestJson<unknown>(`/api/tasks/${id}`), id);
      applyTaskState(state);
    },
    [applyTaskState, taskId],
  );

  const refreshTaskSummary = useCallback(
    async (id = taskId) => {
      if (!id) {
        return;
      }
      const state = normalizeTaskState(
        await requestJson<unknown>(`/api/tasks/${id}?include_events=false`),
        id,
      );
      applyTaskState(state, true);
    },
    [applyTaskState, taskId],
  );

  const refreshTaskEvents = useCallback(
    async (id = taskId) => {
      if (!id) {
        return;
      }
      const afterId = logs.at(-1)?.id;
      const query = afterId ? `?after_id=${encodeURIComponent(afterId)}` : "";
      const incoming = normalizeEventRecords(await requestJson<unknown>(`/api/tasks/${id}/events${query}`));
      if (incoming.length > 0) {
        setLogs((current) => mergeExecutionLogs(current, incoming));
      }
    },
    [logs, taskId],
  );

  useEffect(() => {
    if (!taskId || !activeTask) {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshTaskSummary();
      void refreshTaskEvents();
    }, 2000);

    return () => window.clearInterval(timer);
  }, [activeTask, refreshTaskEvents, refreshTaskSummary, taskId]);

  async function uploadFiles(id: string, files: File[]) {
    if (files.length === 0) {
      return;
    }

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));

    await requestJson<unknown>(`/api/tasks/${id}/files`, {
      method: "POST",
      body: formData,
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSend || isBusy) {
      return;
    }

    setError("");
    setIsBusy(true);
    const content = input.trim();
    const taskContent = content || "Analyze the uploaded Markdown files for bid-collusion suspicion.";
    const files = selectedFiles;
    let requestTaskId = taskId;

    if (content) {
      setMessages((current) => [
        ...current,
        { id: `local-${Date.now()}`, role: "user", content, createdAt: new Date().toISOString() },
      ]);
    }

    try {
      const id = await ensureTask();
      requestTaskId = id;
      await uploadFiles(id, files);

      await requestJson<unknown>(`/api/tasks/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: taskContent, message: taskContent, model }),
      });

      setInput("");
      setSelectedFiles([]);
      await refreshTask(id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
      if (requestTaskId) {
        try {
          await refreshTask(requestTaskId);
        } catch {
          setStatus((current) => (current === "idle" ? "idle" : "failed"));
        }
      }
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStop() {
    if (!taskId || isBusy) {
      return;
    }

    setError("");
    setIsBusy(true);

    try {
      await requestJson<unknown>(`/api/tasks/${taskId}/cancel`, { method: "POST" });
      await refreshTask(taskId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Stop request failed.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []).filter((file) => {
      return file.name.toLowerCase().endsWith(".md") || file.type === "text/markdown";
    });
    setSelectedFiles(files);
  }

  async function fetchArtifactBlob(artifact: Artifact) {
    const request = buildArtifactRequest(artifact, taskId, API_BASE_URL, API_ACCESS_TOKEN);
    const response = await fetch(request.url, { headers: request.headers });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `${response.status} ${response.statusText}`);
    }
    return response.blob();
  }

  async function handleOpenArtifact(artifact: Artifact) {
    setError("");
    const artifactWindow = window.open("about:blank", "_blank");
    if (!artifactWindow) {
      setError("The report window was blocked by the browser.");
      return;
    }
    artifactWindow.opener = null;
    try {
      const blob = await fetchArtifactBlob(artifact);
      const objectUrl = URL.createObjectURL(blob);
      artifactWindow.location.replace(objectUrl);
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (caught) {
      artifactWindow.close();
      setError(caught instanceof Error ? caught.message : "Could not open artifact.");
    }
  }

  return (
    <main className="workspace">
      <header className="topbar">
        <div>
          <h1>MyAgent</h1>
          <p>Local task workspace with visible execution trace</p>
        </div>
        <div className="taskMeta">
          <span className={`status status-${status}`}>{statusLabel}</span>
          <span className="taskStat">Uploads {uploadCount}</span>
          {taskModel ? <span className="taskStat">{taskModel}</span> : null}
          <span className="taskId">{taskId ? `Task ${taskId}` : "No task yet"}</span>
        </div>
      </header>

      {backendError ? <div className="stateBanner stateBanner-error">{backendError}</div> : null}
      {needsInput ? (
        <div className="stateBanner stateBanner-warning">{formatNeedsInput(needsInput)}</div>
      ) : null}

      <section className="workArea">
        <section className="chatPanel" aria-label="Chat messages">
          <div className="panelHeader">
            <h2>Messages</h2>
          </div>
          <div className="messageList">
            {messages.length === 0 ? (
              <div className="emptyState">
                Upload Markdown files and describe the task. The backend will create a task, plan execution,
                and stream updates into the log panel.
              </div>
            ) : (
              messages.map((message) => (
                <article className={`message message-${message.role}`} key={message.id}>
                  <div className="messageRole">{message.role}</div>
                  <p>{message.content}</p>
                </article>
              ))
            )}
          </div>

          {reportArtifacts.length > 0 ? (
            <div className="artifactStrip" aria-label="Report artifacts">
              {reportArtifacts.map((artifact) => (
                <button key={artifact.id} onClick={() => void handleOpenArtifact(artifact)} type="button">
                  Open {artifact.name}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <aside className="logPanel" aria-label="Execution log">
          <div className="panelHeader">
            <h2>Execution Log</h2>
          </div>
          <div className="logList">
            {logs.length === 0 ? (
              <div className="emptyState compact">Plans, sub-agent assignments, tool calls, and artifacts appear here.</div>
            ) : (
              logs.map((log) => (
                <article className={`logItem log-${log.level ?? "info"}`} key={log.id}>
                  <div className="logTitle">{log.title}</div>
                  {log.detail ? <p>{log.detail}</p> : null}
                </article>
              ))
            )}
          </div>
        </aside>
      </section>

      <form className="composer" onSubmit={handleSubmit}>
        <div className="composerTools">
          <label className="filePicker">
            <span>Markdown files</span>
            <input accept=".md,text/markdown" multiple onChange={handleFileChange} type="file" />
          </label>

          <label className="modelSelect">
            <span>Model</span>
            <select onChange={(event) => setModel(event.target.value)} value={model}>
              {modelOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button disabled={!activeTask || isBusy} onClick={handleStop} type="button">
            Stop
          </button>
        </div>

        {selectedFiles.length > 0 ? (
          <div className="selectedFiles">
            {selectedFiles.map((file) => (
              <span key={`${file.name}-${file.lastModified}`}>{file.name}</span>
            ))}
          </div>
        ) : null}

        <div className="inputRow">
          <textarea
            onChange={(event) => setInput(event.target.value)}
            placeholder="Describe the task for the agent..."
            rows={3}
            value={input}
          />
          <button disabled={!canSend || isBusy} type="submit">
            {isBusy ? "Sending" : "Send"}
          </button>
        </div>

        {error ? <div className="errorBanner">{error}</div> : null}
      </form>
    </main>
  );
}
