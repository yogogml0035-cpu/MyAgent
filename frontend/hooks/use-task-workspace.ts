"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type Artifact,
  type ChatMessage,
  type ExecutionLog,
  type ModelOption,
  type TaskState,
  type TaskStatus,
  type TaskSummary,
  formatNeedsInput,
  isTaskActive,
  mergeExecutionLogs,
} from "../app/task-state";
import {
  buildModelDisplayOptions,
  selectedModelDisplayOption,
} from "../app/model-ui";
import { partitionSupportedUploadFiles } from "../app/file-upload";
import {
  buildConversationHistoryItems,
  buildConversationStreamItems,
  buildLogClipboardText,
  buildRunActivityGroups,
  buildStateNoticeMessages,
  buildWorkspaceNoticeMessages,
} from "../app/workspace-view";
import {
  TASK_API_BASE_URL,
  cancelTask,
  createTask,
  fetchArtifactBlob,
  fetchModelOptions,
  fetchTask,
  fetchTaskEvents,
  fetchTaskSummaries,
  formatTaskApiFailure,
  postTaskMessage,
  uploadTaskFiles,
} from "../lib/task-api";

const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    id: "deepseek-reasoner",
    label: "Deepseek",
  },
];

const DEFAULT_FILE_PROMPT = "请分析已上传的 Markdown 或 JSON 文件是否存在串标围标嫌疑。";

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
  const [input, setInput] = useState("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS);
  const [model, setModel] = useState(DEFAULT_MODEL_OPTIONS[0].id);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [errorLevel, setErrorLevel] = useState<"warning" | "error">("error");
  const [copiedCopyKey, setCopiedCopyKey] = useState("");
  const copyFeedbackTimerRef = useRef<number | null>(null);
  const logsRef = useRef<ExecutionLog[]>([]);
  logsRef.current = logs;

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
    setTaskSummaries(await fetchTaskSummaries());
  }, []);

  useEffect(() => {
    let cancelled = false;

    void fetchModelOptions(DEFAULT_MODEL_OPTIONS)
      .then((options) => {
        if (cancelled) {
          return;
        }
        setModelOptions(options);
        setModel((current) => (options.some((option) => option.id === current) ? current : options[0].id));
      })
      .catch(() => {
        if (!cancelled) {
          setModelOptions(DEFAULT_MODEL_OPTIONS);
        }
      });

    void refreshTaskSummaries().catch((caught) => {
      if (!cancelled) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
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
    async (id = taskId) => {
      if (!id) {
        return;
      }
      const incoming = await fetchTaskEvents(id, logsRef.current.at(-1)?.id);
      if (incoming.length > 0) {
        setLogs((current) => mergeExecutionLogs(current, incoming));
      }
    },
    [taskId],
  );

  useEffect(() => {
    if (!taskId || !activeTask) {
      return;
    }

    const timer = window.setInterval(() => {
      void refreshTaskSummary();
      void refreshTaskEvents();
    }, 700);

    return () => window.clearInterval(timer);
  }, [activeTask, refreshTaskEvents, refreshTaskSummary, taskId]);

  useEffect(() => {
    return () => {
      if (copyFeedbackTimerRef.current !== null) {
        window.clearTimeout(copyFeedbackTimerRef.current);
      }
    };
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!canSend || isBusy || activeTask) {
      return;
    }

    setError("");
    setIsBusy(true);
    const content = input.trim();
    const taskContent = content || DEFAULT_FILE_PROMPT;
    const files = selectedFiles;
    let requestTaskId = taskId;

    try {
      const id = await ensureTask();
      requestTaskId = id;
      await uploadTaskFiles(id, files);
      await postTaskMessage(id, taskContent, model);

      setInput("");
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
      setIsBusy(false);
    }
  }, [
    activeTask,
    canSend,
    ensureTask,
    input,
    isBusy,
    model,
    refreshTask,
    refreshTaskSummaries,
    selectedFiles,
    taskId,
  ]);

  const handleStop = useCallback(async () => {
    if (!taskId || isBusy) {
      return;
    }

    setError("");
    setIsBusy(true);

    try {
      await cancelTask(taskId);
      await refreshTask(taskId);
      await refreshTaskSummaries();
    } catch (caught) {
      setErrorLevel("error");
      setError(formatTaskApiFailure(caught));
    } finally {
      setIsBusy(false);
    }
  }, [isBusy, refreshTask, refreshTaskSummaries, taskId]);

  const handleFileSelection = useCallback((chosenFiles: File[]) => {
    const { supportedFiles, rejectedFiles } = partitionSupportedUploadFiles(chosenFiles);
    setSelectedFiles(supportedFiles);
    setErrorLevel("warning");
    setError(
      rejectedFiles.length > 0
        ? `当前仅支持上传 Markdown 或 JSON 文件，已忽略 ${rejectedFiles.length} 个其他类型文件。`
        : "",
    );
  }, []);

  const handleClearFiles = useCallback(() => {
    setSelectedFiles([]);
  }, []);

  const handleNewConversation = useCallback(() => {
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
  }, []);

  const handleSelectConversation = useCallback(
    async (id: string) => {
      if (!id || id === taskId || isBusy) {
        return;
      }

      setError("");
      setInput("");
      setSelectedFiles([]);
      setIsBusy(true);

      try {
        await refreshTask(id);
      } catch (caught) {
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      } finally {
        setIsBusy(false);
      }
    },
    [isBusy, refreshTask, taskId],
  );

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
        artifactWindow.location.replace(objectUrl);
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
      } catch (caught) {
        artifactWindow.close();
        setErrorLevel("error");
        setError(formatTaskApiFailure(caught));
      }
    },
    [taskId],
  );

  return {
    apiBaseUrl: TASK_API_BASE_URL,
    activeTask,
    canSend,
    copiedCopyKey,
    conversationStreamItems,
    handleClearFiles,
    handleCopyLogs,
    handleCopyText,
    handleDownloadArtifact,
    handleFileSelection,
    handleNewConversation,
    handleOpenArtifact,
    handleSelectConversation,
    handleStop,
    handleSubmit,
    hasConversation,
    historyItems,
    input,
    isBusy,
    model,
    modelDisplayOptions,
    noticeMessages,
    selectedFileNames,
    selectedFileSize,
    selectedFiles,
    selectedModelDisplay,
    setInput,
    setModel,
    status,
    uploadCount,
  };
}
