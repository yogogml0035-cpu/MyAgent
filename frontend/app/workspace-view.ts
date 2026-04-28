import type { Artifact, ChatMessage, ExecutionLog, TaskRunRecord, TaskStatus, TaskSummary } from "./task-state";

export type TimeVariant = "default" | "short";

export type ConversationHistoryItem = {
  id: string;
  title: string;
  active: boolean;
};

export type ComposerKeyIntent = {
  key: string;
  shiftKey?: boolean;
  isComposing?: boolean;
  nativeIsComposing?: boolean;
};

export type RunActivityGroup = {
  runId: string;
  title: string;
  status: TaskStatus;
  startedAt?: string;
  completedAt?: string;
  logs: ExecutionLog[];
  reportArtifacts: Artifact[];
};

export type ConversationStreamItem =
  | {
      id: string;
      kind: "message";
      message: ChatMessage;
    }
  | {
      id: string;
      kind: "run";
      group: RunActivityGroup;
    }
  | {
      id: string;
      kind: "artifact";
      group: RunActivityGroup;
      artifact: Artifact;
    };

export type MessagePanelTone = "default" | "system" | "warning" | "error";

export function buildStateNoticeMessages(
  backendError: string,
  needsInputMessage = "",
): ChatMessage[] {
  const notices: ChatMessage[] = [];
  const errorContent = backendError.trim();
  const needsInputContent = needsInputMessage.trim();

  if (errorContent) {
    notices.push({
      id: "state:backend-error",
      role: "assistant",
      content: errorContent,
      level: "error",
    });
  }

  if (needsInputContent) {
    notices.push({
      id: "state:needs-input",
      role: "assistant",
      content: needsInputContent,
      level: "warning",
    });
  }

  return notices;
}

export function buildWorkspaceNoticeMessages(
  content: string,
  level: "warning" | "error" = "error",
): ChatMessage[] {
  const noticeContent = content.trim();
  if (!noticeContent) {
    return [];
  }
  return [
    {
      id: "state:workspace-notice",
      role: "assistant",
      content: noticeContent,
      level,
    },
  ];
}

export function calculateLogProgress(logCount: number) {
  const total = Math.max(logCount, 5);
  const count = Math.min(logCount, total);
  const percent = Math.round((count / total) * 100);
  return { count, total, percent };
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTime(value?: string, variant: TimeVariant = "default") {
  if (!value) {
    return variant === "short" ? "" : "--:--:--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return variant === "short" ? "" : "--:--:--";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: variant === "short" ? undefined : "2-digit",
    hour12: false,
  }).format(date);
}

export function buildLogClipboardText(logs: ExecutionLog[]) {
  return (
    logs
      .map((log) => {
        const time = formatTime(log.createdAt);
        const detail = log.detail ? ` ${log.detail}` : "";
        return `${time} ${formatLogLevelLabel(log.level)} ${log.title}${detail}`;
      })
      .join("\n") || "暂无日志"
  );
}

export function formatLogLevelLabel(level: ExecutionLog["level"] = "info") {
  switch (level) {
    case "success":
      return "成功";
    case "warning":
      return "警告";
    case "error":
      return "错误";
    case "info":
    default:
      return "信息";
  }
}

export function buildConversationHistoryItems(
  summaries: TaskSummary[],
  activeTaskId: string,
): ConversationHistoryItem[] {
  return summaries.map((summary) => ({
    id: summary.id,
    title: summary.title,
    active: summary.id === activeTaskId,
  }));
}

export function shouldSubmitComposerKey(intent: ComposerKeyIntent) {
  return (
    intent.key === "Enter" &&
    !intent.shiftKey &&
    !intent.isComposing &&
    !intent.nativeIsComposing
  );
}

export function formatTaskStatus(status: TaskStatus) {
  switch (status) {
    case "running":
      return "运行中";
    case "complete":
      return "已完成";
    case "cancelled":
      return "已取消";
    case "failed":
      return "失败";
    case "needs_input":
      return "需补充";
    case "interrupted":
      return "已中断";
    case "idle":
      return "待开始";
    case "unknown":
      return "历史";
  }
}

const DEEPSEEK_MISSING_KEY_PREFIX =
  "DeepSeek is selected, but DEEPSEEK_API_KEY is not configured";
const DEEPSEEK_MISSING_KEY_PREFIX_ZH = "已选择 DeepSeek，但后端 .env 未配置 DEEPSEEK_API_KEY";

export function isWarningChatMessage(message: ChatMessage) {
  const content = message.content.trim();
  return (
    message.level === "warning" ||
    content.startsWith(DEEPSEEK_MISSING_KEY_PREFIX) ||
    content.startsWith(DEEPSEEK_MISSING_KEY_PREFIX_ZH)
  );
}

export function getMessagePanelTone(message: ChatMessage): MessagePanelTone {
  if (message.level === "error") {
    return "error";
  }
  if (isWarningChatMessage(message)) {
    return "warning";
  }
  if (message.role === "system") {
    return "system";
  }
  return "default";
}

export function formatMessagePanelStatus(message: ChatMessage) {
  const tone = getMessagePanelTone(message);
  if (tone === "error") {
    return "生成失败";
  }
  if (tone === "warning") {
    return "配置提醒";
  }
  if (tone === "system") {
    return "系统消息";
  }
  return "已完成";
}

export function formatRunLogStatus(status: TaskStatus) {
  switch (status) {
    case "running":
      return "日志收集中...";
    case "complete":
      return "日志完成";
    case "failed":
      return "日志结束（失败）";
    case "cancelled":
      return "日志结束（已取消）";
    case "interrupted":
      return "日志结束（已中断）";
    case "needs_input":
      return "等待补充输入";
    case "idle":
      return "等待日志";
    case "unknown":
      return "日志";
  }
}

export function isReportArtifact(artifact: Artifact) {
  const marker = `${artifact.name} ${artifact.kind ?? ""} ${artifact.path ?? ""} ${artifact.url ?? ""}`.toLowerCase();
  return marker.includes("report") || marker.includes(".html");
}

function runTimeValue(run: TaskRunRecord) {
  return run.startedAt ?? run.completedAt ?? "";
}

function byCreatedAt<T extends { createdAt?: string }>(left: T, right: T) {
  const leftTime = left.createdAt ? Date.parse(left.createdAt) : Number.NaN;
  const rightTime = right.createdAt ? Date.parse(right.createdAt) : Number.NaN;
  if (Number.isNaN(leftTime) && Number.isNaN(rightTime)) {
    return 0;
  }
  if (Number.isNaN(leftTime)) {
    return 1;
  }
  if (Number.isNaN(rightTime)) {
    return -1;
  }
  return leftTime - rightTime;
}

function artifactKeyForRun(runId: string, artifact: Artifact) {
  return `${runId}:${artifact.name}`;
}

function artifactFromRunName(runId: string, name: string): Artifact {
  return {
    id: `${runId}:${name}`,
    name,
    runId,
  };
}

function artifactForRenderedRun(runId: string, artifact: Artifact): Artifact {
  return { ...artifact, runId, id: `${runId}:${artifact.name}` };
}

function isUploadLog(log: ExecutionLog) {
  return log.type === "file_uploaded";
}

export function buildRunActivityGroups(
  runs: TaskRunRecord[],
  logs: ExecutionLog[],
  artifacts: Artifact[],
): RunActivityGroup[] {
  const indexedRuns = runs
    .map((run, index) => ({ run, index }))
    .sort((left, right) => {
      const leftTime = Date.parse(runTimeValue(left.run));
      const rightTime = Date.parse(runTimeValue(right.run));
      if (Number.isNaN(leftTime) && Number.isNaN(rightTime)) {
        return left.index - right.index;
      }
      if (Number.isNaN(leftTime)) {
        return 1;
      }
      if (Number.isNaN(rightTime)) {
        return -1;
      }
      return leftTime - rightTime;
    });

  const groups = indexedRuns.map(({ run }, index): RunActivityGroup => {
    const runArtifacts = artifacts.filter(
      (artifact) => artifact.runId === run.id || (runs.length === 1 && !artifact.runId),
    );
    const artifactMap = new Map<string, Artifact>();
    [...run.artifactNames.map((name) => artifactFromRunName(run.id, name)), ...runArtifacts]
      .filter(isReportArtifact)
      .forEach((artifact) => {
        const key = artifactKeyForRun(run.id, artifact);
        if (!artifactMap.has(key)) {
          artifactMap.set(key, artifactForRenderedRun(run.id, artifact));
        }
      });

    return {
      runId: run.id,
      title: `第 ${index + 1} 轮`,
      status: run.status,
      startedAt: run.startedAt,
      completedAt: run.completedAt,
      logs: logs
        .filter((log) => log.runId === run.id || (runs.length === 1 && !log.runId))
        .sort(byCreatedAt),
      reportArtifacts: Array.from(artifactMap.values()),
    };
  });

  const knownRunIds = new Set(runs.map((run) => run.id));
  const fallbackLogs = logs.filter(
    (log) => (!log.runId && runs.length !== 1) || (log.runId && !knownRunIds.has(log.runId)),
  );
  const fallbackArtifacts = artifacts.filter(
    (artifact) =>
      (!artifact.runId && runs.length !== 1) || (artifact.runId && !knownRunIds.has(artifact.runId)),
  );
  const fallbackReportArtifacts = fallbackArtifacts.filter(isReportArtifact);
  const hideUploadOnlyFallback =
    runs.length > 0 &&
    fallbackLogs.length > 0 &&
    fallbackLogs.every(isUploadLog) &&
    fallbackReportArtifacts.length === 0;

  if (!hideUploadOnlyFallback && (fallbackLogs.length > 0 || fallbackReportArtifacts.length > 0)) {
    groups.push({
      runId: "legacy",
      title: runs.length > 0 ? "历史日志" : "第 1 轮",
      status: "unknown",
      logs: fallbackLogs.sort(byCreatedAt),
      reportArtifacts: fallbackReportArtifacts.map((artifact) =>
        artifactForRenderedRun("legacy", artifact),
      ),
    });
  }

  return groups.filter((group) => group.logs.length > 0 || group.reportArtifacts.length > 0);
}

function groupTimeValue(group: RunActivityGroup) {
  return group.startedAt ?? group.completedAt ?? "";
}

export function buildConversationStreamItems(
  messages: ChatMessage[],
  groups: RunActivityGroup[],
): ConversationStreamItem[] {
  const remainingGroups = new Map(groups.map((group) => [group.runId, group]));
  const firstReplyIndexByRunId = new Map<string, number>();
  const lastMessageIndexByRunId = new Map<string, number>();

  messages.forEach((message, index) => {
    if (message.runId) {
      lastMessageIndexByRunId.set(message.runId, index);
      if (message.role !== "user" && !firstReplyIndexByRunId.has(message.runId)) {
        firstReplyIndexByRunId.set(message.runId, index);
      }
    }
  });

  const items: ConversationStreamItem[] = [];
  function pushGroup(runId: string) {
    const group = remainingGroups.get(runId);
    if (!group) {
      return undefined;
    }
    items.push({ id: `run:${group.runId}`, kind: "run", group });
    remainingGroups.delete(runId);
    return group;
  }

  function pushArtifactItems(group: RunActivityGroup) {
    group.reportArtifacts.forEach((artifact) => {
      items.push({
        id: `artifact:${group.runId}:${artifact.name}`,
        kind: "artifact",
        group,
        artifact,
      });
    });
  }

  messages.forEach((message, index) => {
    let groupBeforeReply: RunActivityGroup | undefined;
    if (message.runId && firstReplyIndexByRunId.get(message.runId) === index) {
      groupBeforeReply = pushGroup(message.runId);
    }

    items.push({
      id: `message:${message.id}`,
      kind: "message",
      message,
    });

    if (groupBeforeReply) {
      pushArtifactItems(groupBeforeReply);
    }

    if (
      message.runId &&
      !firstReplyIndexByRunId.has(message.runId) &&
      lastMessageIndexByRunId.get(message.runId) === index
    ) {
      const group = pushGroup(message.runId);
      if (group) {
        pushArtifactItems(group);
      }
    }
  });

  if (messages.length > 0 && remainingGroups.size === 1) {
    const [[runId, group]] = Array.from(remainingGroups.entries());
    if (runId === "legacy") {
      items.push({ id: `run:${group.runId}`, kind: "run", group });
      pushArtifactItems(group);
      remainingGroups.delete(runId);
    }
  }

  Array.from(remainingGroups.values())
    .sort((left, right) => {
      const leftTime = Date.parse(groupTimeValue(left));
      const rightTime = Date.parse(groupTimeValue(right));
      if (Number.isNaN(leftTime) && Number.isNaN(rightTime)) {
        return 0;
      }
      if (Number.isNaN(leftTime)) {
        return 1;
      }
      if (Number.isNaN(rightTime)) {
        return -1;
      }
      return leftTime - rightTime;
    })
    .forEach((group) => {
      items.push({ id: `run:${group.runId}`, kind: "run", group });
      pushArtifactItems(group);
    });

  return items;
}
