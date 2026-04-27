"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import {
  buildConversationHistoryItems,
  buildLogClipboardText,
  calculateLogProgress,
  formatFileSize,
  formatTime,
} from "./workspace-view";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_MYAGENT_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8001";
const API_ACCESS_TOKEN =
  process.env.NEXT_PUBLIC_MYAGENT_TOKEN || process.env.NEXT_PUBLIC_AGENT_CHAT_TOKEN || "";
const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    id: "deepseek-reasoner",
    label: "DeepSeek Reasoner",
  },
];
const FILE_INPUT_ID = "markdown-files";

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
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const canSend = input.trim().length > 0 || selectedFiles.length > 0;
  const activeTask = isTaskActive(status);
  const logProgress = calculateLogProgress(logs.length);
  const logStatusText = activeTask ? "日志收集中..." : logs.length > 0 ? "日志已同步" : "等待日志";
  const selectedFileNames = selectedFiles.map((file) => file.name).join("、");
  const selectedFileSize = selectedFiles.reduce((total, file) => total + file.size, 0);
  const messageCount = messages.length;
  const hasConversation =
    messages.length > 0 || logs.length > 0 || artifacts.length > 0 || Boolean(backendError || needsInput);
  const historyItems = useMemo(
    () => buildConversationHistoryItems(messages, taskId, status),
    [messages, status, taskId],
  );

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

  function handleClearFiles() {
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handleNewConversation() {
    setTaskId("");
    setStatus("idle");
    setStatusLabel("idle");
    setMessages([]);
    setLogs([]);
    setArtifacts([]);
    setUploadCount(0);
    setTaskModel("");
    setBackendError("");
    setNeedsInput(null);
    setInput("");
    setSelectedFiles([]);
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleCopyLogs() {
    try {
      await navigator.clipboard.writeText(buildLogClipboardText(logs));
    } catch {
      setError("复制日志失败，请检查浏览器权限。");
    }
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
    <main className="agentShell">
      <aside className="chatSidebar" aria-label="历史会话">
        <button className="newChatButton" onClick={handleNewConversation} type="button">
          <span aria-hidden="true" />
          新建会话
        </button>

        <nav className="historyPanel" aria-label="聊天历史">
          <p>聊天历史</p>
          <div className="historyList">
            {historyItems.map((item) => (
              <button
                aria-current={item.active ? "page" : undefined}
                className={item.active ? "historyItem historyItem-active" : "historyItem"}
                key={item.id}
                type="button"
              >
                <strong>{item.title}</strong>
                <span>{item.subtitle}</span>
              </button>
            ))}
          </div>
        </nav>
      </aside>

      <section className={hasConversation ? "chatWorkspace hasConversation" : "chatWorkspace isEmpty"}>
        <div className="workspaceMetaBar" aria-label="任务状态">
          <span className="messageCounter">{messageCount} 条消息</span>
          <span className={`status status-${status}`}>{statusLabel}</span>
          <span className="taskId">{taskId ? `Task ${taskId}` : "No task yet"}</span>
        </div>

        <section className="conversationCanvas" aria-label="任务对话">
        <div className="conversationStream">
          {backendError ? <div className="stateBanner stateBanner-error">{backendError}</div> : null}
          {needsInput ? (
            <div className="stateBanner stateBanner-warning">{formatNeedsInput(needsInput)}</div>
          ) : null}

          {!hasConversation ? (
            <h1 className="heroMark">MYAGENT</h1>
          ) : (
            <>
              {messages.map((message) => (
                <article className={`chatMessage chatMessage-${message.role}`} key={message.id}>
                  <p>{message.content}</p>
                  <time>{formatTime(message.createdAt, "short")}</time>
                </article>
              ))}

              <section className="traceRow" aria-label="进度日志">
                <div className="agentMarker" aria-hidden="true">
                  <span />
                </div>
                <article className="traceCard">
                  <header className="traceHeader">
                    <div className="traceTitle">
                      <span className="documentIcon" aria-hidden="true" />
                      <strong>进度日志</strong>
                      <span className={activeTask ? "spinner" : "syncDot"} aria-hidden="true" />
                      <span>{logStatusText}</span>
                    </div>
                    <button
                      aria-label="复制日志"
                      className="copyButton"
                      disabled={logs.length === 0}
                      onClick={() => void handleCopyLogs()}
                      type="button"
                    >
                      <span aria-hidden="true" />
                    </button>
                  </header>

                  <div className="progressSummary">
                    {`${logProgress.count}/${logProgress.total} (${logProgress.percent}%)`}
                  </div>

                  <div className="logList">
                    {logs.length === 0 ? (
                      <p className="emptyLog">计划、子任务分派、工具调用和产物会显示在这里。</p>
                    ) : (
                      logs.map((log) => (
                        <article className={`logItem log-${log.level ?? "info"}`} key={log.id}>
                          <time>{formatTime(log.createdAt)}</time>
                          <span className="logLevel">{(log.level ?? "info").toUpperCase()}</span>
                          <div>
                            <strong>{log.title}</strong>
                            {log.detail ? <p>{log.detail}</p> : null}
                          </div>
                        </article>
                      ))
                    )}
                  </div>

                  {reportArtifacts.length > 0 ? (
                    <div className="artifactDock" aria-label="报告产物">
                      {reportArtifacts.map((artifact) => (
                        <button key={artifact.id} onClick={() => void handleOpenArtifact(artifact)} type="button">
                          打开 {artifact.name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </article>
              </section>
            </>
          )}
        </div>
      </section>

      <form className="composerShell" onSubmit={handleSubmit}>
        <input
          accept=".md,text/markdown"
          className="fileInput"
          id={FILE_INPUT_ID}
          multiple
          onChange={handleFileChange}
          ref={fileInputRef}
          type="file"
        />

        <div className="composerPanel">
          {selectedFiles.length > 0 ? (
            <div className="fileCard">
              <span className="fileIcon" aria-hidden="true" />
              <div className="fileInfo">
                <span>Markdown</span>
                <strong>{selectedFileNames}</strong>
                <small>{formatFileSize(selectedFileSize)}</small>
              </div>
              <label className="replaceFileButton" htmlFor={FILE_INPUT_ID}>
                更换
              </label>
              <button aria-label="移除文件" className="removeFileButton" onClick={handleClearFiles} type="button">
                ×
              </button>
            </div>
          ) : null}

          <textarea
            className="promptTextarea"
            onChange={(event) => setInput(event.target.value)}
            placeholder={activeTask ? "回复生成中，请稍候..." : "尽管问..."}
            rows={2}
            value={input}
          />

          <div className="composerControls">
            <label aria-label="上传 Markdown 文件" className="roundButton addFileButton" htmlFor={FILE_INPUT_ID}>
              <span aria-hidden="true" />
            </label>

            <span className="agentModePill">
              <span aria-hidden="true" />
              Agent
            </span>

            <label className="modelSelect">
              <span className="srOnly">模型</span>
              <select onChange={(event) => setModel(event.target.value)} value={model}>
                {modelOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            {uploadCount > 0 ? <span className="uploadMeta">Uploads {uploadCount}</span> : null}
            {taskModel ? <span className="uploadMeta">{taskModel}</span> : null}

            <div className="composerSpacer" />

            {activeTask ? (
              <button
                aria-label="停止任务"
                className="roundButton primaryAction stopAction"
                disabled={isBusy}
                onClick={handleStop}
                type="button"
              >
                <span aria-hidden="true" />
              </button>
            ) : (
              <button aria-label={isBusy ? "发送中" : "发送"} className="sendButton" disabled={!canSend || isBusy} type="submit">
                <span aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        {error ? <div className="errorBanner">{error}</div> : null}
      </form>
      </section>
    </main>
  );
}
