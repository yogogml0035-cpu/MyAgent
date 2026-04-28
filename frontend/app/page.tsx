"use client";

import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  type Artifact,
  type ChatMessage,
  type ExecutionLog,
  type ModelOption,
  type TaskState,
  type TaskStatus,
  type TaskSummary,
  buildArtifactRequest,
  formatHttpErrorMessage,
  formatNeedsInput,
  formatRequestFailure,
  isRecord,
  isTaskActive,
  mergeExecutionLogs,
  normalizeEventRecords,
  normalizeModelOption,
  normalizeTaskSummaries,
  normalizeTaskState,
  readString,
  resolveApiBaseUrl,
} from "./task-state";
import {
  buildModelDisplayOptions,
  selectedModelDisplayOption,
} from "./model-ui";
import { FILE_INPUT_ACCEPT, partitionSupportedUploadFiles } from "./file-upload";
import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildRunActivityGroups,
  buildStateNoticeMessages,
  buildWorkspaceNoticeMessages,
  buildLogClipboardText,
  calculateLogProgress,
  formatFileSize,
  formatMessagePanelStatus,
  formatLogLevelLabel,
  formatRunLogStatus,
  formatTime,
  getMessagePanelTone,
  shouldSubmitComposerKey,
} from "./workspace-view";

const API_BASE_URL = resolveApiBaseUrl(
  process.env.NEXT_PUBLIC_MYAGENT_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL,
);
const API_ACCESS_TOKEN =
  process.env.NEXT_PUBLIC_MYAGENT_TOKEN || process.env.NEXT_PUBLIC_AGENT_CHAT_TOKEN || "";
const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    id: "deepseek-reasoner",
    label: "Deepseek",
  },
];
const FILE_INPUT_ID = "document-files";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(API_ACCESS_TOKEN ? { "X-MyAgent-Token": API_ACCESS_TOKEN } : {}),
        ...init?.headers,
      },
    });
  } catch (caught) {
    throw new Error(formatRequestFailure(caught, API_BASE_URL));
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatHttpErrorMessage(response.status, response.statusText, text));
  }

  return response.json() as Promise<T>;
}

export default function Home() {
  const [taskId, setTaskId] = useState<string>("");
  const [status, setStatus] = useState<TaskStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [logs, setLogs] = useState<ExecutionLog[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [runs, setRuns] = useState<TaskState["runs"]>([]);
  const [taskSummaries, setTaskSummaries] = useState<TaskSummary[]>([]);
  const [uploadCount, setUploadCount] = useState(0);
  const [backendError, setBackendError] = useState("");
  const [needsInput, setNeedsInput] = useState<Record<string, unknown> | null>(null);
  const [input, setInput] = useState("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS);
  const [model, setModel] = useState(DEFAULT_MODEL_OPTIONS[0].id);
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [errorLevel, setErrorLevel] = useState<"warning" | "error">("error");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const modelPickerRef = useRef<HTMLDivElement | null>(null);
  const conversationCanvasRef = useRef<HTMLElement | null>(null);

  const canSend = input.trim().length > 0 || selectedFiles.length > 0;
  const activeTask = isTaskActive(status);
  const selectedFileNames = selectedFiles.map((file) => file.name).join("、");
  const selectedFileSize = selectedFiles.reduce((total, file) => total + file.size, 0);
  const needsInputMessage = needsInput ? formatNeedsInput(needsInput) : "";
  const stateNoticeMessages = useMemo(
    () => buildStateNoticeMessages(backendError, needsInputMessage),
    [backendError, needsInputMessage],
  );
  const workspaceNoticeMessages = useMemo(
    () => buildWorkspaceNoticeMessages(error, errorLevel),
    [error, errorLevel],
  );
  const noticeMessages = useMemo(
    () => [...stateNoticeMessages, ...workspaceNoticeMessages],
    [stateNoticeMessages, workspaceNoticeMessages],
  );
  const hasConversation =
    messages.length > 0 || logs.length > 0 || artifacts.length > 0 || noticeMessages.length > 0;
  const historyItems = useMemo(
    () => buildConversationHistoryItems(taskSummaries, taskId),
    [taskId, taskSummaries],
  );
  const modelDisplayOptions = useMemo(
    () => buildModelDisplayOptions(modelOptions),
    [modelOptions],
  );
  const selectedModelDisplay = useMemo(
    () => selectedModelDisplayOption(modelDisplayOptions, model),
    [model, modelDisplayOptions],
  );

  const runActivityGroups = useMemo(
    () => buildRunActivityGroups(runs, logs, artifacts),
    [artifacts, logs, runs],
  );
  const conversationStreamItems = useMemo(
    () => buildConversationStreamItems(messages, runActivityGroups),
    [messages, runActivityGroups],
  );

  useEffect(() => {
    if (!hasConversation) {
      return;
    }
    const canvas = conversationCanvasRef.current;
    if (!canvas) {
      return;
    }
    canvas.scrollTo({ top: canvas.scrollHeight, behavior: "smooth" });
  }, [conversationStreamItems, hasConversation, noticeMessages]);

  const applyTaskState = useCallback((state: TaskState, mergeLogs = false) => {
    setTaskId(state.id);
    setStatus(state.status);
    setMessages((current) => (mergeLogs && state.messages.length === 0 ? current : state.messages));
    setLogs((current) => (mergeLogs ? mergeExecutionLogs(current, state.logs) : state.logs));
    setArtifacts(state.artifacts);
    setRuns(state.runs);
    setUploadCount(state.uploadCount);
    setBackendError(state.error ?? "");
    setNeedsInput(state.needsInput ?? null);
  }, []);

  const refreshTaskSummaries = useCallback(async () => {
    const summaries = normalizeTaskSummaries(await requestJson<unknown>("/api/tasks"));
    setTaskSummaries(summaries);
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

    void refreshTaskSummaries().catch((caught) => {
      if (!cancelled) {
        setErrorLevel("error");
        setError(formatRequestFailure(caught, API_BASE_URL));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [refreshTaskSummaries]);

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
      throw new Error("后端没有返回任务 ID。");
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

  useEffect(() => {
    if (!isModelPickerOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && modelPickerRef.current?.contains(target)) {
        return;
      }
      setIsModelPickerOpen(false);
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setIsModelPickerOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isModelPickerOpen]);

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
    if (!canSend || isBusy || activeTask) {
      return;
    }

    setError("");
    setIsBusy(true);
    const content = input.trim();
    const taskContent = content || "请分析已上传的 Markdown 或 JSON 文件是否存在串标围标嫌疑。";
    const files = selectedFiles;
    let requestTaskId = taskId;

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
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatRequestFailure(caught, API_BASE_URL));
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
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatRequestFailure(caught, API_BASE_URL));
    } finally {
      setIsBusy(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const chosenFiles = Array.from(event.target.files ?? []);
    const { supportedFiles, rejectedFiles } = partitionSupportedUploadFiles(chosenFiles);
    setSelectedFiles(supportedFiles);
    setErrorLevel("warning");
    setError(
      rejectedFiles.length > 0
        ? `当前仅支持上传 Markdown 或 JSON 文件，已忽略 ${rejectedFiles.length} 个其他类型文件。`
        : "",
    );
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
    setMessages([]);
    setLogs([]);
    setArtifacts([]);
    setRuns([]);
    setUploadCount(0);
    setBackendError("");
    setNeedsInput(null);
    setInput("");
    setSelectedFiles([]);
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleSelectConversation(id: string) {
    if (!id || id === taskId || isBusy) {
      return;
    }

    setError("");
    setInput("");
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    try {
      await refreshTask(id);
    } catch (caught) {
      setErrorLevel("error");
      setError(formatRequestFailure(caught, API_BASE_URL));
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      shouldSubmitComposerKey({
        key: event.key,
        shiftKey: event.shiftKey,
        nativeIsComposing: event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229,
      })
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function handleCopyLogs(copiedLogs = logs) {
    await handleCopyText(buildLogClipboardText(copiedLogs), "复制日志失败，请检查浏览器权限。");
  }

  async function handleCopyText(text: string, failureMessage = "复制内容失败，请检查浏览器权限。") {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setErrorLevel("error");
      setError(failureMessage);
    }
  }

  function renderChatMessage(message: ChatMessage, key: string) {
    const tone = getMessagePanelTone(message);
    const messageClassName = [
      "chatMessage",
      `chatMessage-${message.role}`,
      message.role === "user" ? "" : `chatMessage-${tone}`,
    ]
      .filter(Boolean)
      .join(" ");

    if (message.role === "user") {
      return (
        <div className="userMessageRow" key={key}>
          <div className="userMessageFrame">
            <article className={messageClassName}>
              <p>{message.content}</p>
            </article>
            <time className="userMessageTime">{formatTime(message.createdAt, "short")}</time>
          </div>
          <div className="userMarker" aria-hidden="true" />
        </div>
      );
    }

    return (
      <section className="assistantMessageRow" key={key}>
        <div className="agentMarker" aria-hidden="true" />
        <article className={messageClassName}>
          <header className="messageCardHeader">
            <div className="messageCardTitle">
              <span className="messageBotIcon" aria-hidden="true" />
              <strong>{message.role === "system" ? "系统消息" : "AI 生成内容"}</strong>
              <span className={`statusGlyph statusGlyph-${tone}`} aria-hidden="true" />
              <span>{formatMessagePanelStatus(message)}</span>
            </div>
            <button
              aria-label="复制AI内容"
              className="copyButton"
              disabled={!message.content}
              onClick={() => void handleCopyText(message.content)}
              title="复制AI内容"
              type="button"
            >
              <span aria-hidden="true" />
            </button>
          </header>

          {tone === "error" ? <div className="messageErrorStrip">{message.content}</div> : null}

          {tone !== "error" ? (
            <div className="messageCardBody">
              <p>{message.content}</p>
            </div>
          ) : null}

          {message.createdAt ? (
            <time className="messageCardTime">{formatTime(message.createdAt, "short")}</time>
          ) : null}
        </article>
      </section>
    );
  }

  function renderArtifactMessage(groupTitle: string, artifact: Artifact, key: string) {
    const artifactKind = artifact.kind ?? (artifact.name.toLowerCase().endsWith(".html") ? "html" : "file");
    const canOpen = artifactKind === "html" || artifact.name.toLowerCase().endsWith(".html");

    return (
      <section className="artifactMessageRow" key={key}>
        <div className="agentMarker" aria-hidden="true" />
        <article className="downloadCard">
          <header className="downloadCardHeader">
            <div className="downloadCardTitle">
              <span className="downloadStatusIcon" aria-hidden="true" />
              <strong>{canOpen ? "报告已生成" : "文件已生成"}</strong>
              <span className="runRoundLabel">{groupTitle}</span>
            </div>
            <div className="downloadActions">
              {canOpen ? (
                <button
                  className="downloadSecondaryButton"
                  onClick={() => void handleOpenArtifact(artifact)}
                  type="button"
                >
                  打开报告
                </button>
              ) : null}
              <button
                className="downloadPrimaryButton"
                onClick={() => void handleDownloadArtifact(artifact)}
                type="button"
              >
                <span className="downloadButtonIcon" aria-hidden="true" />
                下载文件
              </button>
            </div>
          </header>

          <div className="downloadCardBody">
            <span className="downloadFileIcon" aria-hidden="true" />
            <span className="downloadFileName">{artifact.name}</span>
          </div>
        </article>
      </section>
    );
  }

  async function fetchArtifactBlob(artifact: Artifact) {
    const request = buildArtifactRequest(artifact, taskId, API_BASE_URL, API_ACCESS_TOKEN);
    let response: Response;
    try {
      response = await fetch(request.url, { headers: request.headers });
    } catch (caught) {
      throw new Error(formatRequestFailure(caught, API_BASE_URL));
    }
    if (!response.ok) {
      const text = await response.text();
      throw new Error(formatHttpErrorMessage(response.status, response.statusText, text));
    }
    return response.blob();
  }

  async function handleDownloadArtifact(artifact: Artifact) {
    setError("");
    try {
      const blob = await fetchArtifactBlob(artifact);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = artifact.name || "artifact";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (caught) {
      setErrorLevel("error");
      setError(formatRequestFailure(caught, API_BASE_URL));
    }
  }

  async function handleOpenArtifact(artifact: Artifact) {
    setError("");
    const artifactWindow = window.open("about:blank", "_blank");
    if (!artifactWindow) {
      setErrorLevel("error");
      setError("报告窗口被浏览器拦截，请允许弹窗后重试。");
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
      setErrorLevel("error");
      setError(formatRequestFailure(caught, API_BASE_URL));
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
                onClick={() => void handleSelectConversation(item.id)}
                type="button"
              >
                <strong>{item.title}</strong>
              </button>
            ))}
          </div>
        </nav>
      </aside>

      <section className={hasConversation ? "chatWorkspace hasConversation" : "chatWorkspace isEmpty"}>
        <section className="conversationCanvas" aria-label="任务对话" ref={conversationCanvasRef}>
          <div className="conversationStream">
            {!hasConversation ? (
              <h1 className="heroMark">MYAGENT</h1>
            ) : (
              <>
                {conversationStreamItems.map((item) => {
                  if (item.kind === "message") {
                    return renderChatMessage(item.message, item.id);
                  }

                  if (item.kind === "artifact") {
                    return renderArtifactMessage(item.group.title, item.artifact, item.id);
                  }

                  const group = item.group;
                  const groupActive = isTaskActive(group.status);
                  const groupProgress = calculateLogProgress(group.logs.length);
                  const groupLogStatusText = formatRunLogStatus(group.status);

                  return (
                    <section className="traceRow" aria-label={`${group.title}进度日志`} key={item.id}>
                      <div className="agentMarker" aria-hidden="true" />
                      <article className={`traceCard traceCard-${group.status}`}>
                        <header className="traceHeader">
                          <div className="traceTitle">
                            <span className="documentIcon" aria-hidden="true" />
                            <strong>进度日志</strong>
                            <span className="runRoundLabel">{group.title}</span>
                            <span
                              className={groupActive ? "spinner" : `statusGlyph statusGlyph-${group.status}`}
                              aria-hidden="true"
                            />
                            <span>{groupLogStatusText}</span>
                          </div>
                          <button
                            aria-label={`复制${group.title}日志`}
                            className="copyButton"
                            disabled={group.logs.length === 0}
                            onClick={() => void handleCopyLogs(group.logs)}
                            type="button"
                          >
                            <span aria-hidden="true" />
                          </button>
                        </header>

                        <div className="progressSummary">
                          {`${groupProgress.count}/${groupProgress.total} (${groupProgress.percent}%)`}
                        </div>

                        <div className="logList">
                          {group.logs.length === 0 ? (
                            <p className="emptyLog">计划、子任务分派、工具调用和产物会显示在这里。</p>
                          ) : (
                            group.logs.map((log) => (
                              <article className={`logItem log-${log.level ?? "info"}`} key={log.id}>
                                <time>{formatTime(log.createdAt)}</time>
                                <span className="logLevel">{formatLogLevelLabel(log.level)}</span>
                                <div>
                                  <strong>{log.title}</strong>
                                  {log.detail ? <p>{log.detail}</p> : null}
                                </div>
                              </article>
                            ))
                          )}
                        </div>

                      </article>
                    </section>
                  );
                })}
                {noticeMessages.map((message) => renderChatMessage(message, `notice:${message.id}`))}
              </>
            )}
          </div>
        </section>

        <form className="composerShell" onSubmit={handleSubmit}>
          <input
            accept={FILE_INPUT_ACCEPT}
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
                  <span>Markdown / JSON</span>
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
              onKeyDown={handleComposerKeyDown}
              placeholder={activeTask ? "回复生成中，请稍候..." : "尽管问..."}
              rows={2}
              value={input}
            />

            <div className="composerControls">
              <label
                aria-label="上传 Markdown 或 JSON 文件"
                className="roundButton addFileButton"
                htmlFor={FILE_INPUT_ID}
              >
                <span aria-hidden="true" />
              </label>

              {uploadCount > 0 ? <span className="uploadMeta">已上传 {uploadCount} 个文件</span> : null}

              <div className="composerSpacer" />

              <div className="modelPicker" ref={modelPickerRef}>
                <button
                  aria-expanded={isModelPickerOpen}
                  aria-haspopup="listbox"
                  className="modelPickerTrigger"
                  onClick={() => setIsModelPickerOpen((current) => !current)}
                  type="button"
                >
                  <span className="modelPickerLabel">{selectedModelDisplay.label}</span>
                  <span className="modelChevron" aria-hidden="true" />
                </button>

                {isModelPickerOpen ? (
                  <div aria-label="模型" className="modelPickerMenu" role="listbox">
                    {modelDisplayOptions.map((option) => {
                      const isSelected = option.id === model;
                      return (
                        <button
                          aria-selected={isSelected}
                          className={isSelected ? "modelOption modelOption-active" : "modelOption"}
                          key={option.id}
                          onClick={() => {
                            setModel(option.id);
                            setIsModelPickerOpen(false);
                          }}
                          role="option"
                          type="button"
                        >
                          <span className="modelOptionCopy">
                            <span className="modelOptionTitle">
                              <span>{option.label}</span>
                              {option.badge ? <span className="modelBadge">{option.badge}</span> : null}
                            </span>
                            <small>{option.description}</small>
                          </span>
                          <span className="modelCheck" aria-hidden="true" />
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>

              {activeTask ? (
                <button
                  aria-label="停止任务"
                  className="sendButton stopAction"
                  disabled={isBusy}
                  onClick={handleStop}
                  type="button"
                >
                  <svg aria-hidden="true" className="sendButtonIcon" fill="none" viewBox="0 0 24 24">
                    <rect fill="currentColor" height="12" rx="2.5" width="12" x="6" y="6" />
                  </svg>
                </button>
              ) : (
                <button
                  aria-label={isBusy ? "发送中" : "发送"}
                  className="sendButton"
                  disabled={!canSend || isBusy}
                  type="submit"
                >
                  <svg aria-hidden="true" className="sendButtonIcon" fill="none" viewBox="0 0 24 24">
                    <path
                      d="M12 19V5m0 0-6 6m6-6 6 6"
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2.4"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </form>
      </section>
    </main>
  );
}
