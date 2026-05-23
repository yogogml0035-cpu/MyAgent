"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type Artifact,
  type ChatMessage,
  type ExecutionLog,
  type ModelOption,
  type SkillOption,
  type TaskState,
  type TaskStatus,
  type TaskSummary,
  formatNeedsInput,
  isRecord,
  isModelRunnable,
  isTaskActive,
  mergeExecutionLogs,
  normalizeEventRecords,
  readString,
} from "../app/task-state";
import {
  buildModelDisplayOptions,
  selectedModelDisplayOption,
} from "../app/model-ui";
import { SUPPORTED_UPLOAD_LABEL, partitionSupportedUploadFiles } from "../app/file-upload";
import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildLogClipboardText,
  buildRunActivityGroups,
  buildStateNoticeMessages,
  buildWorkspaceNoticeMessages,
} from "../app/workspace-view";
import {
  cancelTask,
  createTask,
  createTaskEventSource,
  deleteTask,
  fetchArtifactBlob,
  fetchModelOptions,
  fetchSkillOptions,
  fetchTask,
  fetchTaskEvents,
  fetchTaskSummaries,
  formatTaskApiFailure,
  postTaskMessage,
  renameTask,
  uploadTaskFiles,
} from "../lib/task-api";

const DEFAULT_MODEL_ID = "deepseek-v4-flash";
const ALLOWED_MODEL_IDS = new Set([
  "deepseek-v4-flash",
  "deepseek-v4-flash-thinking",
]);
const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    id: "deepseek-v4-flash",
    label: "DeepSeek V4 Flash",
  },
  {
    id: "deepseek-v4-flash-thinking",
    label: "DeepSeek V4 Flash Thinking",
  },
];

const DEFAULT_FILE_PROMPT = "请分析已上传文件，先按需读取资源内容，再总结关键差异。";
export const MAX_SSE_RETRIES = 5;
export const ARTIFACT_OBJECT_URL_REVOKE_DELAY_MS = 60_000;
export const TASK_WORKSPACE_STREAM_EVENT_TYPES = new Set([
  "log",
  "tool_call",
  "tool_result",
  "assistant_thinking_delta",
  "assistant_answer_delta",
  "status_update",
  "context_loaded",
  "memory_recalled",
  "final_answer",
  "task_completed",
  "task_failed",
  "task_cancelled",
]);

export function calculateSseRetryDelay(retryCount: number) {
  return Math.min(3000 * Math.pow(2, retryCount), 30000);
}

export function getSseErrorDetail(payload: unknown) {
  if (!isRecord(payload) || payload.type !== "error") {
    return "";
  }
  return readString(payload.detail, "流传输异常，请刷新页面。");
}

function escapePreviewHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function buildSandboxedArtifactPreviewDocument(
  artifactName: string,
  artifactObjectUrl: string,
) {
  const title = escapePreviewHtml(artifactName || "HTML 产物预览");
  const iframeSrc = escapePreviewHtml(artifactObjectUrl);

  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src blob:; style-src 'unsafe-inline';" />
    <title>${title}</title>
    <style>
      html,
      body {
        height: 100%;
        margin: 0;
        background: #f6f3ed;
        color: #26221b;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      body {
        display: grid;
        grid-template-rows: auto 1fr;
      }
      header {
        border-bottom: 1px solid rgba(38, 34, 27, 0.16);
        background: #fffaf0;
        padding: 12px 16px;
      }
      h1 {
        font-size: 15px;
        line-height: 1.4;
        margin: 0;
      }
      p {
        font-size: 12px;
        line-height: 1.5;
        margin: 4px 0 0;
        color: #6f6758;
      }
      iframe {
        border: 0;
        height: 100%;
        width: 100%;
        background: white;
      }
    </style>
  </head>
  <body>
    <header>
      <h1>${title}</h1>
      <p>此 HTML 产物已在禁用脚本的沙箱 iframe 中预览。</p>
    </header>
    <iframe sandbox="" referrerpolicy="no-referrer" src="${iframeSrc}" title="${title}"></iframe>
  </body>
</html>`;
}

export function buildRunLogDownloadName(runId: string) {
  const normalizedRunId = runId
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${normalizedRunId || "run"}-logs.jsonl`;
}

export function useTaskWorkspace() {
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
  const latestEventIdRef = useRef<string | undefined>(undefined);
  const [input, setInput] = useState("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS);
  const [model, setModel] = useState(DEFAULT_MODEL_ID);
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<SkillOption[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSubmittingTask, setIsSubmittingTask] = useState(false);
  const [isSwitchingConversation, setIsSwitchingConversation] = useState(false);
  const [isMutatingConversation, setIsMutatingConversation] = useState(false);
  const [isStoppingTask, setIsStoppingTask] = useState(false);
  const [error, setError] = useState<string>("");
  const [errorLevel, setErrorLevel] = useState<"warning" | "error">("error");
  const [copiedCopyKey, setCopiedCopyKey] = useState("");
  const copyFeedbackTimerRef = useRef<number | null>(null);
  const logsRef = useRef<ExecutionLog[]>([]);
  logsRef.current = logs;

  const canSend = input.trim().length > 0 || selectedFiles.length > 0;
  const activeTask = isTaskActive(status);
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
  const selectedModelOption = useMemo(
    () => modelOptions.find((option) => option.id === model) ?? null,
    [model, modelOptions],
  );
  const selectedSkillNames = useMemo(
    () => selectedSkills.map((skill) => skill.name),
    [selectedSkills],
  );
  const selectedModelRunnable = isModelRunnable(selectedModelOption);
  const isComposerBusy = isSubmittingTask || isSwitchingConversation || isStoppingTask;
  const isHistoryBusy =
    isSubmittingTask || isSwitchingConversation || isMutatingConversation || isStoppingTask;
  const runActivityGroups = useMemo(
    () => buildRunActivityGroups(runs, logs, artifacts),
    [artifacts, logs, runs],
  );
  const conversationStreamItems = useMemo(
    () => buildConversationStreamItems(messages, runActivityGroups),
    [messages, runActivityGroups],
  );

  const applyTaskState = useCallback((state: TaskState, mergeLogs = false) => {
    setTaskId(state.id);
    setStatus(state.status);
    setMessages((current) => (mergeLogs && state.messages.length === 0 ? current : state.messages));
    setLogs((current) => (mergeLogs ? mergeExecutionLogs(current, state.logs) : state.logs));
    latestEventIdRef.current = state.latestEventId ?? state.logs.at(-1)?.id;
    setArtifacts(state.artifacts);
    setRuns(state.runs);
    setUploadCount(state.uploadCount);
    setBackendError(state.error ?? "");
    setNeedsInput(state.needsInput ?? null);
  }, []);

  const refreshTaskSummaries = useCallback(async () => {
    setTaskSummaries(await fetchTaskSummaries());
  }, []);

  useEffect(() => {
    let cancelled = false;

    void fetchModelOptions(DEFAULT_MODEL_OPTIONS)
      .then((options) => {
        if (cancelled) {
          return;
        }
        const deepSeekOnlyOptions = options.filter((option) => ALLOWED_MODEL_IDS.has(option.id));
        const nextOptions = deepSeekOnlyOptions.length > 0 ? deepSeekOnlyOptions : DEFAULT_MODEL_OPTIONS;
        setModelOptions(nextOptions);
        setModel((current) =>
          nextOptions.some((option) => option.id === current) ? current : DEFAULT_MODEL_ID,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setModelOptions(DEFAULT_MODEL_OPTIONS);
          setModel(DEFAULT_MODEL_ID);
        }
      });

    void refreshTaskSummaries().catch((caught) => {
      if (!cancelled) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      }
    });

    void fetchSkillOptions()
      .then((options) => {
        if (!cancelled) {
          setSkillOptions(options);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setSkillOptions([]);
          setErrorLevel("warning");
          setError(`Skill 列表加载失败：${formatTaskApiFailure(caught)}`);
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

    const created = await createTask(model);
    applyTaskState(created.state);
    return created.id;
  }, [applyTaskState, model, taskId]);

  const refreshTask = useCallback(
    async (id = taskId) => {
      if (!id) {
        return;
      }

      applyTaskState(await fetchTask(id));
    },
    [applyTaskState, taskId],
  );

  const refreshTaskSummary = useCallback(
    async (id = taskId) => {
      if (!id) {
        return;
      }
      applyTaskState(await fetchTask(id, { includeEvents: false }), true);
    },
    [applyTaskState, taskId],
  );

  const refreshTaskEvents = useCallback(
    async (id = taskId, afterId = latestEventIdRef.current ?? logsRef.current.at(-1)?.id) => {
      if (!id) {
        return;
      }
      const incoming = await fetchTaskEvents(id, afterId);
      if (incoming.length > 0) {
        latestEventIdRef.current = incoming.at(-1)?.id ?? latestEventIdRef.current;
        setLogs((current) => mergeExecutionLogs(current, incoming));
      }
    },
    [taskId],
  );

  useEffect(() => {
    if (!taskId || !activeTask) {
      return;
    }

    let disposed = false;
    let es: EventSource | null = null;
    let retryTimeoutId: number | null = null;
    let retryCount = 0;

    function startSSE() {
      if (disposed) return;

      es = createTaskEventSource(
        taskId,
        (event) => {
          if (disposed) return;
          try {
            const payload = JSON.parse(event.data);
            retryCount = 0;
            const sseErrorDetail = getSseErrorDetail(payload);
            if (sseErrorDetail) {
              setErrorLevel("error");
              setError(sseErrorDetail);
              void refreshTaskSummary();
              return;
            }
            if (
              payload &&
              ((typeof payload.type === "string" &&
                TASK_WORKSPACE_STREAM_EVENT_TYPES.has(payload.type)) ||
                Array.isArray(payload))
            ) {
              const incoming = normalizeEventRecords(
                Array.isArray(payload) ? payload : [payload],
              );
              if (incoming.length > 0) {
                latestEventIdRef.current = incoming.at(-1)?.id ?? latestEventIdRef.current;
                setLogs((current) => mergeExecutionLogs(current, incoming));
              }
            }
            if (!payload || payload.type === "state" || payload.type === "done" || payload.type === "final_answer") {
              void refreshTaskSummary();
            }
          } catch {
            void refreshTaskSummary();
          }
        },
        () => {
          if (disposed) return;
          es?.close();
          es = null;
          void Promise.all([refreshTaskSummary(), refreshTaskEvents()]).catch(() => {});
          if (!disposed) {
            if (retryCount >= MAX_SSE_RETRIES) {
              setErrorLevel("error");
              setError("流连接多次重试失败，请刷新页面或稍后重试。");
              return;
            }
            const backoffMs = calculateSseRetryDelay(retryCount);
            retryCount++;
            retryTimeoutId = window.setTimeout(() => {
              retryTimeoutId = null;
              if (!disposed) startSSE();
            }, backoffMs);
          }
        },
        latestEventIdRef.current,
      );
    }

    startSSE();

    return () => {
      disposed = true;
      es?.close();
      if (retryTimeoutId !== null) {
        window.clearTimeout(retryTimeoutId);
      }
    };
  }, [activeTask, refreshTaskEvents, refreshTaskSummary, taskId]);

  useEffect(() => {
    return () => {
      if (copyFeedbackTimerRef.current !== null) {
        window.clearTimeout(copyFeedbackTimerRef.current);
      }
    };
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!canSend || activeTask || isSubmittingTask || isSwitchingConversation) {
      return;
    }

    setError("");
    if (!selectedModelRunnable) {
      setErrorLevel("error");
      setError("当前模型服务未配置，请先在后端配置对应 API Key 后再发送。");
      return;
    }
    setIsSubmittingTask(true);
    const content = input.trim();
    const taskContent = content || DEFAULT_FILE_PROMPT;
    const files = selectedFiles;
    let requestTaskId = taskId;

    try {
      const id = await ensureTask();
      requestTaskId = id;
      await uploadTaskFiles(id, files);
      await postTaskMessage(id, taskContent, model, selectedSkillNames);

      setInput("");
      setSelectedSkills([]);
      setSelectedFiles([]);
      await refreshTask(id);
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatTaskApiFailure(caught));
      if (requestTaskId) {
        try {
          await refreshTask(requestTaskId);
        } catch {
          setStatus((current) => (current === "idle" ? "idle" : "failed"));
        }
      }
    } finally {
      setIsSubmittingTask(false);
    }
  }, [
    activeTask,
    canSend,
    ensureTask,
    input,
    isSubmittingTask,
    isSwitchingConversation,
    model,
    refreshTask,
    refreshTaskSummaries,
    selectedFiles,
    selectedSkillNames,
    selectedModelRunnable,
    taskId,
  ]);

  const handleSelectSkill = useCallback(
    (skill: SkillOption) => {
      if (activeTask || isSubmittingTask || isSwitchingConversation) {
        return;
      }

      setSelectedSkills((current) =>
        current.some((selected) => selected.name === skill.name) ? current : [...current, skill],
      );
    },
    [activeTask, isSubmittingTask, isSwitchingConversation],
  );

  const handleRemoveSkill = useCallback((skillName: string) => {
    setSelectedSkills((current) => current.filter((skill) => skill.name !== skillName));
  }, []);

  const handleStop = useCallback(async () => {
    if (!taskId || isStoppingTask || isSwitchingConversation) {
      return;
    }

    setError("");
    setIsStoppingTask(true);

    try {
      await cancelTask(taskId);
      await refreshTask(taskId);
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatTaskApiFailure(caught));
    } finally {
      setIsStoppingTask(false);
    }
  }, [isStoppingTask, isSwitchingConversation, refreshTask, refreshTaskSummaries, taskId]);

  const handleFileSelection = useCallback((chosenFiles: File[]) => {
    const { supportedFiles, rejectedFiles } = partitionSupportedUploadFiles(chosenFiles);
    setSelectedFiles(supportedFiles);
    setErrorLevel("warning");
    setError(
      rejectedFiles.length > 0
        ? `当前仅支持上传 ${SUPPORTED_UPLOAD_LABEL}，已忽略 ${rejectedFiles.length} 个其他类型文件。`
        : "",
    );
  }, []);

  const handleRemoveFile = useCallback((removedIndex: number) => {
    setSelectedFiles((current) => current.filter((_, index) => index !== removedIndex));
  }, []);

  const handleNewConversation = useCallback(() => {
    setTaskId("");
    setStatus("idle");
    setMessages([]);
    setLogs([]);
    latestEventIdRef.current = undefined;
    setArtifacts([]);
    setRuns([]);
    setUploadCount(0);
    setBackendError("");
    setNeedsInput(null);
    setInput("");
    setSelectedSkills([]);
    setSelectedFiles([]);
    setError("");
  }, []);

  const handleSelectConversation = useCallback(
    async (id: string) => {
      if (
        !id ||
        id === taskId ||
        isSubmittingTask ||
        isSwitchingConversation ||
        isMutatingConversation ||
        isStoppingTask
      ) {
        return;
      }

      const targetSummary = taskSummaries.find((summary) => summary.id === id);

      setError("");
      setTaskId(id);
      setStatus(targetSummary?.status ?? "idle");
      setMessages([]);
      setLogs([]);
      latestEventIdRef.current = undefined;
      setArtifacts([]);
      setRuns([]);
      setUploadCount(0);
      setBackendError("");
      setNeedsInput(null);
      setInput("");
      setSelectedSkills([]);
      setSelectedFiles([]);
      setIsSwitchingConversation(true);

      try {
        await refreshTaskSummary(id);
        const shouldHydrateFullHistory = targetSummary?.status !== "running";
        void refreshTaskEvents(id, shouldHydrateFullHistory ? undefined : latestEventIdRef.current).catch((caught) => {
          setErrorLevel("error");
          setError(formatTaskApiFailure(caught));
        });
      } catch (caught) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      } finally {
        setIsSwitchingConversation(false);
      }
    },
    [
      isMutatingConversation,
      isStoppingTask,
      isSubmittingTask,
      isSwitchingConversation,
      refreshTaskEvents,
      refreshTaskSummary,
      taskSummaries,
      taskId,
    ],
  );

  const handleRenameConversation = useCallback(
    async (id: string, title: string) => {
      const normalizedTitle = title.trim();
      if (
        !id ||
        !normalizedTitle ||
        isSubmittingTask ||
        isSwitchingConversation ||
        isMutatingConversation ||
        isStoppingTask
      ) {
        return;
      }

      setError("");
      setIsMutatingConversation(true);
      try {
        await renameTask(id, normalizedTitle);
        await refreshTaskSummaries();
        if (id === taskId) {
          await refreshTaskSummary(id);
        }
      } catch (caught) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      } finally {
        setIsMutatingConversation(false);
      }
    },
    [
      isMutatingConversation,
      isStoppingTask,
      isSubmittingTask,
      isSwitchingConversation,
      refreshTaskSummaries,
      refreshTaskSummary,
      taskId,
    ],
  );

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      if (
        !id ||
        isSubmittingTask ||
        isSwitchingConversation ||
        isMutatingConversation ||
        isStoppingTask
      ) {
        return;
      }
      const summary = taskSummaries.find((item) => item.id === id);
      if (summary?.status === "running") {
        setErrorLevel("warning");
        setError("任务运行中，暂时不能删除。");
        return;
      }

      setError("");
      setIsMutatingConversation(true);
      try {
        await deleteTask(id);
        if (id === taskId) {
          handleNewConversation();
        }
        await refreshTaskSummaries();
      } catch (caught) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      } finally {
        setIsMutatingConversation(false);
      }
    },
    [
      handleNewConversation,
      isMutatingConversation,
      isStoppingTask,
      isSubmittingTask,
      isSwitchingConversation,
      refreshTaskSummaries,
      taskId,
      taskSummaries,
    ],
  );

  const handleClearConversations = useCallback(async () => {
    if (
      isSubmittingTask ||
      isSwitchingConversation ||
      isMutatingConversation ||
      isStoppingTask ||
      taskSummaries.length === 0
    ) {
      return;
    }
    if (activeTask || taskSummaries.some((summary) => isTaskActive(summary.status))) {
      setErrorLevel("warning");
      setError("有任务正在运行，完成或停止后再清空历史会话。");
      return;
    }
    if (!window.confirm("清空所有历史会话后无法恢复，确定清空吗？")) {
      return;
    }

    const deletedIds = taskSummaries.map((summary) => summary.id);

    setError("");
    setIsMutatingConversation(true);
    try {
      for (const id of deletedIds) {
        await deleteTask(id);
      }
      if (deletedIds.includes(taskId)) {
        handleNewConversation();
      }
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatTaskApiFailure(caught));
    } finally {
      setIsMutatingConversation(false);
    }
  }, [
    activeTask,
    handleNewConversation,
    isMutatingConversation,
    isStoppingTask,
    isSubmittingTask,
    isSwitchingConversation,
    refreshTaskSummaries,
    taskId,
    taskSummaries,
  ]);

  const showCopyFeedback = useCallback((copyKey?: string) => {
    if (!copyKey) {
      return;
    }
    setCopiedCopyKey(copyKey);
    if (copyFeedbackTimerRef.current !== null) {
      window.clearTimeout(copyFeedbackTimerRef.current);
    }
    copyFeedbackTimerRef.current = window.setTimeout(() => {
      setCopiedCopyKey("");
      copyFeedbackTimerRef.current = null;
    }, 1400);
  }, []);

  const handleCopyText = useCallback(
    async (
      text: string,
      failureMessage = "复制内容失败，请检查浏览器权限。",
      copyKey?: string,
    ) => {
      try {
        await navigator.clipboard.writeText(text);
        showCopyFeedback(copyKey);
      } catch {
        setErrorLevel("error");
        setError(failureMessage);
      }
    },
    [showCopyFeedback],
  );

  const handleCopyLogs = useCallback(
    async (copiedLogs = logs, copyKey?: string) => {
      await handleCopyText(
        buildLogClipboardText(copiedLogs),
        "复制日志失败，请检查浏览器权限。",
        copyKey,
      );
    },
    [handleCopyText, logs],
  );

  const handleDownloadLogs = useCallback(
    async (downloadedLogs: ExecutionLog[], runId: string, groupTitle: string) => {
      if (downloadedLogs.length === 0) {
        setErrorLevel("warning");
        setError(`${groupTitle}暂无完整日志可下载。`);
        return;
      }

      setError("");
      try {
        const payload = buildLogClipboardText(downloadedLogs);
        const blob = new Blob([payload], { type: "application/x-ndjson;charset=utf-8" });
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = buildRunLogDownloadName(runId);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), ARTIFACT_OBJECT_URL_REVOKE_DELAY_MS);
      } catch (caught) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      }
    },
    [],
  );

  const handleDownloadArtifact = useCallback(
    async (artifact: Artifact) => {
      setError("");
      try {
        const blob = await fetchArtifactBlob(artifact, taskId);
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
        setError(formatTaskApiFailure(caught));
      }
    },
    [taskId],
  );

  const handleOpenArtifact = useCallback(
    async (artifact: Artifact) => {
      setError("");
      const artifactWindow = window.open("about:blank", "_blank");
      if (!artifactWindow) {
        setErrorLevel("error");
        setError("报告窗口被浏览器拦截，请允许弹窗后重试。");
        return;
      }
      artifactWindow.opener = null;
      try {
        const blob = await fetchArtifactBlob(artifact, taskId);
        const objectUrl = URL.createObjectURL(blob);
        artifactWindow.document.open();
        artifactWindow.document.write(
          buildSandboxedArtifactPreviewDocument(artifact.name, objectUrl),
        );
        artifactWindow.document.close();
        window.setTimeout(
          () => URL.revokeObjectURL(objectUrl),
          ARTIFACT_OBJECT_URL_REVOKE_DELAY_MS,
        );
      } catch (caught) {
        artifactWindow.close();
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      }
    },
    [taskId],
  );

  return {
    activeTask,
    canSend,
    copiedCopyKey,
    conversationStreamItems,
    currentTaskActive: activeTask,
    handleCopyLogs,
    handleCopyText,
    handleClearConversations,
    handleDownloadArtifact,
    handleDownloadLogs,
    handleFileSelection,
    handleNewConversation,
    handleOpenArtifact,
    handleDeleteConversation,
    handleRenameConversation,
    handleRemoveFile,
    handleSelectConversation,
    handleStop,
    handleSubmit,
    hasConversation,
    historyItems,
    input,
    isComposerBusy,
    isHistoryBusy,
    isMutatingConversation,
    isStoppingTask,
    isSubmittingTask,
    isSwitchingConversation,
    model,
    modelDisplayOptions,
    noticeMessages,
    selectedModelRunnable,
    selectedFiles,
    selectedSkills,
    skillOptions,
    selectedModelDisplay,
    setInput,
    setModel,
    handleSelectSkill,
    handleRemoveSkill,
    status,
    uploadCount,
  };
}
