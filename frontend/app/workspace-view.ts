import {
  isTaskActive,
  translateKnownDisplayText,
  type AgentActivityPhase,
  type Artifact,
  type ChatMessage,
  type ExecutionLog,
  type TaskRunRecord,
  type TaskStatus,
  type TaskSummary,
} from "./task-state";

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
  artifacts: Artifact[];
  streamedAnswer?: string;
  streamedAnswerCreatedAt?: string;
};

export type VisibleLogPartition = {
  visibleLogs: ExecutionLog[];
  hiddenReasoningCount: number;
};

export type LiveToolLogItem = {
  id: string;
  kind: "tool";
  createdAt?: string;
  level?: ExecutionLog["level"];
  title: string;
  resultText: string;
  resultStatus?: NonNullable<ExecutionLog["live"]>["resultStatus"];
};

export type LiveStatusLogItem = {
  id: string;
  kind: "status";
  createdAt?: string;
  level?: ExecutionLog["level"];
  text: string;
  active?: boolean;
};

export type LiveLogItem = LiveToolLogItem | LiveStatusLogItem;

export type ConversationStreamItem =
  | {
      id: string;
      kind: "message";
      message: ChatMessage;
      assistantArtifacts?: Artifact[];
      groupTitle?: string;
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
  const liveItems = buildLiveLogItems(logs);
  return liveItems.map(formatLiveLogItemClipboardText).join("\n") || "暂无日志";
}

export function buildLiveLogItems(
  logs: ExecutionLog[],
  status: TaskStatus = "unknown",
): LiveLogItem[] {
  const items: LiveLogItem[] = [];
  const toolItemsById = new Map<string, LiveToolLogItem>();
  const pendingToolItemsByName = new Map<string, LiveToolLogItem[]>();
  let activeText = "";
  let activeCreatedAt: string | undefined;
  let hasCancelEvent = false;

  logs.forEach((log, index) => {
    if (log.type === "assistant_answer_delta") {
      return;
    }

    // Detect cancel events to handle them specially
    if (log.type === "task_cancelled" || log.live?.resultStatus === "cancelled") {
      hasCancelEvent = true;
    }

    const live = log.live;
    if (!live) {
      const text = formatLegacyLiveSummary(log);
      if (text) {
        items.push({
          id: `legacy:${log.id}`,
          kind: "status",
          createdAt: log.createdAt,
          level: log.level,
          text,
        });
      }
      return;
    }

    if (live.kind === "tool_call") {
      const toolItem: LiveToolLogItem = {
        id: `tool:${live.toolCallId ?? log.id}`,
        kind: "tool",
        createdAt: log.createdAt,
        level: log.level,
        title: formatLiveToolCallTitle(live),
        resultText: formatLiveToolPendingText(live.toolName),
      };
      items.push(toolItem);
      rememberPendingToolItem(toolItemsById, pendingToolItemsByName, toolItem, live);
      return;
    }

    if (live.kind === "tool_result") {
      const toolItem = takePendingToolItem(toolItemsById, pendingToolItemsByName, live);
      if (toolItem) {
        toolItem.level = log.level;
        toolItem.resultStatus = live.resultStatus;
        toolItem.resultText = formatLiveToolResultText(live);
        return;
      }
      items.push({
        id: `tool-result:${live.toolCallId ?? log.id ?? index}`,
        kind: "tool",
        createdAt: log.createdAt,
        level: log.level,
        title: formatLiveToolCallTitle(live),
        resultStatus: live.resultStatus,
        resultText: formatLiveToolResultText(live),
      });
      return;
    }

    // Check agentActivity first (higher precedence), then fall back to live stage
    const agentActivityText = log.agentActivity
      ? formatAgentActivityPhase(log.agentActivity.phase)
      : "";
    const liveText = formatLiveStatusText(live);
    const text = agentActivityText || liveText;
    if (!text) {
      return;
    }
    // Determine if this is a terminal stage
    const isAgentTerminal = log.agentActivity?.status === "completed" || log.agentActivity?.status === "failed" || log.agentActivity?.status === "skipped";
    const isTerminal = isTerminalLiveStage(live.stage) || isAgentTerminal;
    if (isTerminal || !isTaskActive(status)) {
      items.push({
        id: `status:${log.id}`,
        kind: "status",
        createdAt: log.createdAt,
        level: log.level,
        text,
      });
      return;
    }
    activeText = text;
    activeCreatedAt = log.createdAt;
  });

  if (isTaskActive(status)) {
    // If there's a cancel event, show cancelled status instead of active thinking
    if (hasCancelEvent) {
      items.push({
        id: "status:cancelled",
        kind: "status",
        createdAt: activeCreatedAt,
        level: "warning",
        text: "任务已取消",
        active: false,
      });
    } else {
      items.push({
        id: "status:active",
        kind: "status",
        createdAt: activeCreatedAt,
        level: "info",
        text: activeText || "AI正在思考...",
        active: true,
      });
    }
  }

  return items;
}

export function formatLiveLogItemClipboardText(item: LiveLogItem) {
  const time = formatTime(item.createdAt);
  if (item.kind === "tool") {
    return `${time} ${item.title} -> ${item.resultText}`;
  }
  return `${time} ${item.text}`;
}

function rememberPendingToolItem(
  toolItemsById: Map<string, LiveToolLogItem>,
  pendingToolItemsByName: Map<string, LiveToolLogItem[]>,
  toolItem: LiveToolLogItem,
  live: NonNullable<ExecutionLog["live"]>,
) {
  if (live.toolCallId) {
    toolItemsById.set(live.toolCallId, toolItem);
  }
  const toolName = liveToolQueueKey(live.toolName);
  const queue = pendingToolItemsByName.get(toolName) ?? [];
  queue.push(toolItem);
  pendingToolItemsByName.set(toolName, queue);
}

function takePendingToolItem(
  toolItemsById: Map<string, LiveToolLogItem>,
  pendingToolItemsByName: Map<string, LiveToolLogItem[]>,
  live: NonNullable<ExecutionLog["live"]>,
) {
  if (live.toolCallId) {
    const matchedById = toolItemsById.get(live.toolCallId);
    if (matchedById) {
      toolItemsById.delete(live.toolCallId);
      removePendingToolItemByReference(pendingToolItemsByName, matchedById);
      return matchedById;
    }
  }
  const toolName = liveToolQueueKey(live.toolName);
  const queue = pendingToolItemsByName.get(toolName);
  const matched = queue?.shift();
  if (queue && queue.length === 0) {
    pendingToolItemsByName.delete(toolName);
  }
  return matched;
}

function removePendingToolItemByReference(
  pendingToolItemsByName: Map<string, LiveToolLogItem[]>,
  toolItem: LiveToolLogItem,
) {
  for (const [toolName, queue] of pendingToolItemsByName) {
    const index = queue.indexOf(toolItem);
    if (index < 0) {
      continue;
    }
    queue.splice(index, 1);
    if (queue.length === 0) {
      pendingToolItemsByName.delete(toolName);
    }
    return;
  }
}

function liveToolQueueKey(toolName?: string) {
  return toolName || "tool";
}

function formatLiveToolCallTitle(live: NonNullable<ExecutionLog["live"]>) {
  const agentName = live.agentName || "main_agent";
  const toolName = live.toolName || "tool";
  return `${agentName} 调用 ${toolName}(${formatLiveToolParameters(live.parameterItems)})`;
}

function formatLiveToolParameters(
  parameterItems: NonNullable<ExecutionLog["live"]>["parameterItems"] = [],
) {
  return parameterItems
    .map((item) => `"${item.key}":${formatLiveParameterValue(item.value)}`)
    .join(",");
}

function formatLiveParameterValue(value: string | number | boolean) {
  if (typeof value === "string") {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return String(value);
}

function formatLiveToolPendingText(toolName?: string) {
  return `${toolName || "工具"} 正在执行`;
}

function formatLiveToolResultText(live: NonNullable<ExecutionLog["live"]>) {
  const toolLabel = live.toolName ? `${live.toolName} 工具` : "工具";
  switch (live.resultStatus) {
    case "failed":
      return `${toolLabel}调用失败，正在调整处理方式`;
    case "empty":
      return `${live.toolName || "工具"} 未找到可用结果，正在尝试其他方式`;
    case "cancelled":
      return `${toolLabel}调用已取消`;
    case "skipped":
      return `${toolLabel}已跳过`;
    case "success":
    default:
      if (typeof live.resultCount === "number") {
        return `${toolLabel}返回了 ${live.resultCount} 条结果`;
      }
      return `${toolLabel}已返回结果`;
  }
}

export function formatAgentActivityPhase(phase: AgentActivityPhase | undefined): string {
  switch (phase) {
    case "planning":
      return "正在规划任务...";
    case "reasoning":
      return "AI正在思考...";
    case "tool_use":
      return "正在调用工具...";
    case "file_operation":
      return "正在处理文件...";
    case "finalizing":
      return "AI正在生成结果...";
    default:
      return "";
  }
}

function formatLiveStatusText(live: NonNullable<ExecutionLog["live"]>) {
  if (live.resultStatus === "cancelled") {
    return "任务已取消";
  }
  if (live.kind === "answer_status") {
    if (live.stage === "completed") {
      return "回答已完成";
    }
    if (live.stage === "generating_answer") {
      return "正在生成回答...";
    }
  }
  switch (live.stage) {
    case "analyzing_intent":
      return "正在分析任务意图...";
    case "selecting_tool":
      return "正在选择合适工具...";
    case "using_tool":
      return "正在调用工具...";
    case "reading_input":
      return "正在读取输入...";
    case "generating_answer":
      return "正在整理回答...";
    case "completed":
      return live.kind === "answer_status" ? "回答已完成" : "任务处理已完成";
    case "needs_input":
      return "需要补充信息后继续";
    case "failed":
      return "处理遇到问题，正在调整处理方式";
    default:
      return "";
  }
}

function isTerminalLiveStage(stage: NonNullable<ExecutionLog["live"]>["stage"]) {
  return stage === "completed" || stage === "failed" || stage === "needs_input";
}

function formatLegacyLiveSummary(log: ExecutionLog) {
  if (log.type === "answer_generation_started") {
    return "正在生成回答...";
  }
  if (log.type === "task_cancelled") {
    return "任务已取消";
  }
  if (log.type === "needs_input") {
    return "需要补充信息后继续";
  }
  if (log.type === "task_failed") {
    return "处理遇到问题，正在调整处理方式";
  }
  if (log.type === "reasoning_trace") {
    return "";
  }
  if (log.type === "assistant_answer_delta") {
    return "";
  }
  if (log.type === "tool_call" || log.type === "tool_result" || log.type === "status_update") {
    const translated = translateKnownDisplayText(log.title);
    return translated || log.title;
  }
  if (log.level === "error") {
    return "处理遇到问题，正在调整处理方式";
  }
  if (log.level === "warning") {
    return "任务需要注意，正在调整处理方式";
  }
  return "";
}

export function formatReasoningPhaseLabel(phase: NonNullable<ExecutionLog["reasoning"]>["phase"]) {
  switch (phase) {
    case "plan":
      return "计划";
    case "observe":
      return "观察";
    case "decide":
      return "决策";
    case "next_step":
      return "下一步";
    case "final_summary":
      return "总结";
    case "risk":
      return "风险";
  }
}

export function partitionVisibleLogs(
  logs: ExecutionLog[],
  options: { reasoningLimit?: number; expanded?: boolean } = {},
): VisibleLogPartition {
  const reasoningLimit = options.reasoningLimit ?? 3;
  if (options.expanded) {
    return { visibleLogs: logs, hiddenReasoningCount: 0 };
  }
  let visibleInfoReasoning = 0;
  const visibleLogs: ExecutionLog[] = [];
  let hiddenReasoningCount = 0;

  logs.forEach((log) => {
    const isReasoning = Boolean(log.reasoning);
    const isWarningOrError = log.level === "warning" || log.level === "error";
    if (!isReasoning || isWarningOrError) {
      visibleLogs.push(log);
      return;
    }
    visibleInfoReasoning += 1;
    if (visibleInfoReasoning <= reasoningLimit) {
      visibleLogs.push(log);
      return;
    }
    hiddenReasoningCount += 1;
  });

  return { visibleLogs, hiddenReasoningCount };
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
  if (message.streaming) {
    return "生成中";
  }
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

export function formatMessagePanelTitle(message: ChatMessage) {
  if (message.role === "system") {
    return "系统消息";
  }
  const tone = getMessagePanelTone(message);
  if (tone === "default") {
    return "AI回复";
  }
  return "AI 生成内容";
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

function isSetupFallbackLog(log: ExecutionLog) {
  if (log.level === "warning" || log.level === "error") {
    return false;
  }
  return log.type === "task_created" || log.type === "file_uploaded";
}

function accumulateStreamedAnswer(logs: ExecutionLog[]): string {
  const streamLogs = logs
    .filter((log) => Boolean(log.answerStream?.content))
    .sort((left, right) => {
      const leftIndex = left.answerStream?.streamIndex ?? 0;
      const rightIndex = right.answerStream?.streamIndex ?? 0;
      if (leftIndex !== rightIndex) return leftIndex - rightIndex;
      return byCreatedAt(left, right);
    });
  return streamLogs.map((log) => log.answerStream!.content).join("");
}

const PUNCTUATION_PATTERN = /[。，！？、；：""''（）【】《》.,!?;:"'()\[\]{}]/g;

function hasMeaningfulContent(content: string): boolean {
  const stripped = content.replace(PUNCTUATION_PATTERN, "");
  return stripped.trim().length > 0;
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
      .forEach((artifact) => {
        const key = artifactKeyForRun(run.id, artifact);
        if (!artifactMap.has(key)) {
          artifactMap.set(key, artifactForRenderedRun(run.id, artifact));
        }
      });

    const runLogs = logs
      .filter(
        (log) =>
          log.runId === run.id ||
          (runs.length === 1 && !log.runId && !isSetupFallbackLog(log)),
      )
      .sort(byCreatedAt);
    const accumulatedAnswer = accumulateStreamedAnswer(runLogs);
    const lastStreamLog = runLogs
      .filter((log) => Boolean(log.answerStream?.content))
      .sort((left, right) => {
        const leftIndex = left.answerStream?.streamIndex ?? 0;
        const rightIndex = right.answerStream?.streamIndex ?? 0;
        if (leftIndex !== rightIndex) return leftIndex - rightIndex;
        return byCreatedAt(left, right);
      })
      .at(-1);

    return {
      runId: run.id,
      title: `第 ${index + 1} 轮`,
      status: run.status,
      startedAt: run.startedAt,
      completedAt: run.completedAt,
      logs: runLogs,
      artifacts: Array.from(artifactMap.values()),
      streamedAnswer: accumulatedAnswer || undefined,
      streamedAnswerCreatedAt: lastStreamLog?.createdAt,
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
  const visibleFallbackLogs =
    runs.length > 0 ? fallbackLogs.filter((log) => !isSetupFallbackLog(log)) : fallbackLogs;

  if (visibleFallbackLogs.length > 0 || fallbackArtifacts.length > 0) {
    groups.push({
      runId: "legacy",
      title: runs.length > 0 ? "历史日志" : "第 1 轮",
      status: "unknown",
      logs: visibleFallbackLogs.sort(byCreatedAt),
      artifacts: fallbackArtifacts.map((artifact) => artifactForRenderedRun("legacy", artifact)),
    });
  }

  return groups.filter((group) => group.logs.length > 0 || group.artifacts.length > 0);
}

function groupTimeValue(group: RunActivityGroup) {
  return group.startedAt ?? group.completedAt ?? "";
}

function isPlaceholderAssistantMessage(message: ChatMessage): boolean {
  if (message.role !== "assistant") {
    return false;
  }
  const content = message.content.trim();
  if (!content || !hasMeaningfulContent(content)) {
    return true;
  }
  const placeholderTitles = ["AI回复", "AI 生成内容", "系统消息"];
  const strippedContent = content.replace(PUNCTUATION_PATTERN, "").trim();
  return placeholderTitles.some((title) => strippedContent === title || strippedContent.startsWith(title));
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
    group.artifacts.forEach((artifact) => {
      items.push({
        id: `artifact:${group.runId}:${artifact.name}`,
        kind: "artifact",
        group,
        artifact,
      });
    });
  }

  function pushStreamedAnswerItem(group: RunActivityGroup) {
    const content = group.streamedAnswer?.trim();
    if (!content || !hasMeaningfulContent(content)) {
      return;
    }
    items.push({
      id: `message:stream:${group.runId}`,
      kind: "message",
      message: {
        id: `stream:${group.runId}`,
        role: "assistant",
        content: group.streamedAnswer ?? "",
        createdAt: group.streamedAnswerCreatedAt,
        runId: group.runId,
        streaming: true,
      },
      groupTitle: group.title,
    });
  }

  messages.forEach((message, index) => {
    let groupBeforeReply: RunActivityGroup | undefined;
    if (message.runId && firstReplyIndexByRunId.get(message.runId) === index) {
      groupBeforeReply = pushGroup(message.runId);
    }

    const isPlaceholder = isPlaceholderAssistantMessage(message);
    if (!isPlaceholder) {
      items.push({
        id: `message:${message.id}`,
        kind: "message",
        message,
        assistantArtifacts:
          message.role !== "user" && groupBeforeReply ? groupBeforeReply.artifacts : undefined,
        groupTitle: groupBeforeReply?.title,
      });
    }

    if (groupBeforeReply && message.role === "user") {
      pushArtifactItems(groupBeforeReply);
    }

    if (
      message.runId &&
      !firstReplyIndexByRunId.has(message.runId) &&
      lastMessageIndexByRunId.get(message.runId) === index
    ) {
      const group = pushGroup(message.runId);
      if (group) {
        pushStreamedAnswerItem(group);
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
      pushStreamedAnswerItem(group);
      pushArtifactItems(group);
    });

  return items;
}
