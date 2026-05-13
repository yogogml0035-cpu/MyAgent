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

export type LiveLogDetailRow = {
  label: string;
  value: string;
};

export type LiveLogDiagnostics = {
  rows: LiveLogDetailRow[];
  rawJson: string;
};

export type LiveToolLogItem = {
  id: string;
  kind: "tool";
  createdAt?: string;
  level?: ExecutionLog["level"];
  title: string;
  resultText: string;
  resultStatus?: NonNullable<ExecutionLog["live"]>["resultStatus"];
  details: LiveLogDiagnostics;
};

export type LiveStatusLogItem = {
  id: string;
  kind: "status";
  createdAt?: string;
  level?: ExecutionLog["level"];
  text: string;
  active?: boolean;
  details: LiveLogDiagnostics;
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
  return logs.map(formatRawLogRecordJson).join("\n") || "暂无日志";
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
  let activeDetails: LiveLogDiagnostics | undefined;
  let hasCancelEvent = false;
  let hasAnswerStream = false;
  let lastAnswerCreatedAt: string | undefined;
  let lastAnswerDetails: LiveLogDiagnostics | undefined;

  function pushStatusItem(log: ExecutionLog, text: string) {
    const previous = items.at(-1);
    const details = buildLogDiagnostics(log);
    if (previous?.kind === "status" && previous.text === text && !previous.active) {
      previous.details = details;
      return previous;
    }
    const item: LiveStatusLogItem = {
      id: `status:${log.id}`,
      kind: "status",
      createdAt: log.createdAt,
      level: log.level,
      text,
      details,
    };
    items.push(item);
    return item;
  }

  logs.forEach((log, index) => {
    if (log.type === "assistant_answer_delta") {
      if (log.answerStream?.content) {
        hasAnswerStream = true;
        lastAnswerCreatedAt = log.createdAt;
        lastAnswerDetails = buildAnswerStreamDiagnostics(log);
      }
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
          details: buildLogDiagnostics(log),
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
        details: buildLogDiagnostics(log),
      };
      items.push(toolItem);
      rememberPendingToolItem(toolItemsById, pendingToolItemsByName, toolItem, live);
      return;
    }

    if (live.kind === "tool_result") {
      const toolItem = takePendingToolItem(toolItemsById, pendingToolItemsByName, live);
      if (toolItem) {
        toolItem.createdAt = log.createdAt || toolItem.createdAt;
        toolItem.level = log.level;
        toolItem.title = formatLiveToolResultTitle(live);
        toolItem.resultStatus = live.resultStatus;
        toolItem.resultText = formatLiveToolResultText(live);
        toolItem.details = mergeLiveLogDiagnostics(toolItem.details, buildLogDiagnostics(log));
        return;
      }
      items.push({
        id: `tool-result:${live.toolCallId ?? log.id ?? index}`,
        kind: "tool",
        createdAt: log.createdAt,
        level: log.level,
        title: formatLiveToolResultTitle(live),
        resultStatus: live.resultStatus,
        resultText: formatLiveToolResultText(live),
        details: buildLogDiagnostics(log),
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
      pushStatusItem(log, text);
      return;
    }
    pushStatusItem(log, text);
    activeText = text;
    activeCreatedAt = log.createdAt;
    activeDetails = buildLogDiagnostics(log);
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
        details: activeDetails ?? buildSyntheticLogDiagnostics("task_cancelled", "任务已取消"),
      });
    } else {
      const displayText = hasAnswerStream ? "AI正在生成结果" : activeText || "AI正在思考...";
      const lastItem = items.at(-1);
      if (lastItem?.kind === "status" && lastItem.text === displayText) {
        lastItem.active = true;
        lastItem.createdAt = lastAnswerCreatedAt || activeCreatedAt || lastItem.createdAt;
        lastItem.level = "info";
        lastItem.details = lastAnswerDetails
          ? mergeLiveLogDiagnostics(lastItem.details, lastAnswerDetails)
          : lastItem.details;
      } else {
        items.push({
          id: "status:active",
          kind: "status",
          createdAt: lastAnswerCreatedAt || activeCreatedAt,
          level: "info",
          text: displayText,
          active: true,
          details: lastAnswerDetails ?? activeDetails ?? buildSyntheticLogDiagnostics("active_status", displayText),
        });
      }
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

function formatRawLogRecordJson(log: ExecutionLog) {
  if (log.memoryContext) {
    return JSON.stringify(fallbackRawLogRecord(log));
  }
  return JSON.stringify(log.rawRecord ?? fallbackRawLogRecord(log));
}

function formatPrettyRawLogRecord(log: ExecutionLog) {
  if (log.memoryContext) {
    return JSON.stringify(fallbackRawLogRecord(log), null, 2);
  }
  return JSON.stringify(log.rawRecord ?? fallbackRawLogRecord(log), null, 2);
}

function fallbackRawLogRecord(log: ExecutionLog) {
  return stripUndefinedValues({
    id: log.id,
    type: log.type,
    message: log.title,
    detail: log.detail,
    level: log.level,
    created_at: log.createdAt,
    run_id: log.runId,
    payload: {
      live: log.live,
      agent_activity: log.agentActivity,
      file_audit: log.fileAudit,
      reasoning: log.reasoning,
      search_trace: log.searchTrace,
      orchestration: log.orchestration,
      memory_context: log.memoryContext,
      answer_stream: log.answerStream,
    },
  });
}

function stripUndefinedValues(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, entry]) => entry !== undefined)
      .map(([key, entry]) => [
        key,
        isPlainRecord(entry) ? stripUndefinedValues(entry) : entry,
      ]),
  );
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function buildLogDiagnostics(log: ExecutionLog): LiveLogDiagnostics {
  const live = log.live;
  const rows: LiveLogDetailRow[] = [
    { label: "事件类型", value: log.type || "unknown" },
  ];

  const originalMessage = readRawString(log.rawRecord?.message);
  if (originalMessage) {
    rows.push({ label: "原始消息", value: originalMessage });
  }
  if (live?.diagnosticLabel || live?.agentName) {
    rows.push({ label: "节点", value: live.diagnosticLabel || live.agentName || "" });
  }
  if (live?.toolName) {
    rows.push({ label: "工具", value: live.toolName });
  }
  const parameters = live?.parameterItems?.length
    ? formatLiveToolParameters(live.parameterItems)
    : "";
  if (parameters) {
    rows.push({ label: "参数", value: parameters });
  }
  if (live?.resultStatus) {
    rows.push({ label: "结果状态", value: live.resultStatus });
  }
  if (log.memoryContext) {
    rows.push(...formatMemoryContextRows(log.memoryContext));
  }

  return {
    rows,
    rawJson: formatPrettyRawLogRecord(log),
  };
}

function formatMemoryContextRows(memoryContext: NonNullable<ExecutionLog["memoryContext"]>) {
  const rows: LiveLogDetailRow[] = [];
  if (memoryContext.kind === "conversation") {
    rows.push({ label: "上下文类型", value: "同一会话上下文" });
    if (typeof memoryContext.recentMessageCount === "number") {
      rows.push({ label: "最近消息", value: String(memoryContext.recentMessageCount) });
    }
    if (memoryContext.summaryPreview) {
      rows.push({ label: "会话摘要", value: memoryContext.summaryPreview });
    }
    if (typeof memoryContext.cachedToolResultCount === "number") {
      rows.push({ label: "工具缓存", value: String(memoryContext.cachedToolResultCount) });
    }
    if (memoryContext.memoryPreviews.length > 0) {
      rows.push({ label: "缓存预览", value: memoryContext.memoryPreviews.join("；") });
    }
    return rows;
  }

  rows.push({ label: "上下文类型", value: "长期记忆" });
  if (memoryContext.userId) {
    rows.push({ label: "用户", value: memoryContext.userId });
  }
  if (typeof memoryContext.memoryCount === "number") {
    rows.push({ label: "记忆数", value: String(memoryContext.memoryCount) });
  }
  if (memoryContext.memoryPreviews.length > 0) {
    rows.push({ label: "记忆预览", value: memoryContext.memoryPreviews.join("；") });
  }
  return rows;
}

function buildAnswerStreamDiagnostics(log: ExecutionLog): LiveLogDiagnostics {
  const payload = stripUndefinedValues({
    answer_stream: stripUndefinedValues({
      schema_version: log.answerStream?.schemaVersion,
      stream_index: log.answerStream?.streamIndex,
      content_hidden: true,
    }),
  });
  return {
    rows: [
      { label: "事件类型", value: "assistant_answer_delta" },
      { label: "显示方式", value: "流式片段已折叠为生成状态" },
    ],
    rawJson: JSON.stringify(
      stripUndefinedValues({
        type: "assistant_answer_delta",
        message: "AI正在生成结果",
        created_at: log.createdAt,
        run_id: log.runId,
        payload,
      }),
      null,
      2,
    ),
  };
}

function buildSyntheticLogDiagnostics(type: string, message: string): LiveLogDiagnostics {
  return {
    rows: [
      { label: "事件类型", value: type },
      { label: "显示消息", value: message },
    ],
    rawJson: JSON.stringify({ type, message }, null, 2),
  };
}

function mergeLiveLogDiagnostics(
  first: LiveLogDiagnostics | undefined,
  second: LiveLogDiagnostics,
): LiveLogDiagnostics {
  if (!first) {
    return second;
  }
  return {
    rows: [...first.rows, ...second.rows],
    rawJson: `${first.rawJson}\n\n${second.rawJson}`,
  };
}

function readRawString(value: unknown) {
  return typeof value === "string" ? value : "";
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
  return `正在${formatLiveToolLabel(live)}`;
}

function formatLiveToolResultTitle(live: NonNullable<ExecutionLog["live"]>) {
  const label = formatLiveToolLabel(live);
  switch (live.resultStatus) {
    case "failed":
      return `${label}遇到问题`;
    case "empty":
      return `${label}暂无可用结果`;
    case "cancelled":
      return `${label}已取消`;
    case "skipped":
      return `${label}已跳过`;
    case "success":
    default:
      return `${label}已返回结果`;
  }
}

function formatLiveToolLabel(live: NonNullable<ExecutionLog["live"]>) {
  if (live.toolLabel) {
    return live.toolLabel;
  }
  const toolName = live.toolName?.toLowerCase() ?? "";
  if (toolName.includes("tavily") || toolName.includes("search")) {
    return "联网搜索";
  }
  if (toolName.includes("read_file")) {
    return "读取文件";
  }
  if (toolName.includes("write_file")) {
    return "写入文件";
  }
  if (toolName.includes("list")) {
    return "查看文件列表";
  }
  return "调用工具";
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
  const label = formatToolNameLabel(toolName);
  return `正在等待${label}返回结果`;
}

function formatLiveToolResultText(live: NonNullable<ExecutionLog["live"]>) {
  switch (live.resultStatus) {
    case "failed":
      return "工具调用失败，正在调整处理方式";
    case "empty":
      return "未找到可用结果，正在尝试其他方式";
    case "cancelled":
      return "工具调用已取消";
    case "skipped":
      return "工具调用已跳过";
    case "success":
    default:
      if (typeof live.resultCount === "number") {
        return `返回了 ${live.resultCount} 条结果`;
      }
      return "工具已返回结果";
  }
}

function formatToolNameLabel(toolName?: string) {
  const normalized = toolName?.toLowerCase() ?? "";
  if (normalized.includes("tavily") || normalized.includes("search")) {
    return "联网搜索";
  }
  if (normalized.includes("read_file")) {
    return "文件读取";
  }
  if (normalized.includes("write_file")) {
    return "文件写入";
  }
  if (normalized.includes("list")) {
    return "文件列表";
  }
  return "工具";
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
      return "AI正在生成结果";
    default:
      return "";
  }
}

function formatLiveStatusText(live: NonNullable<ExecutionLog["live"]>) {
  if (live.displayText) {
    return live.displayText;
  }
  if (live.resultStatus === "cancelled") {
    return "任务已取消";
  }
  if (live.kind === "answer_status") {
    if (live.stage === "completed") {
      return "回答已完成";
    }
    if (live.stage === "generating_answer") {
      return "AI正在生成结果";
    }
  }
  switch (live.stage) {
    case "preparing":
      return "正在准备任务...";
    case "thinking":
      return "AI正在思考...";
    case "analyzing_intent":
      return "正在分析任务意图...";
    case "selecting_tool":
      return "正在选择合适工具...";
    case "using_tool":
      return "正在调用工具...";
    case "reading_input":
      return "正在读取输入...";
    case "organizing_state":
      return "正在整理任务状态...";
    case "generating_answer":
      return "AI正在生成结果";
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
    return "AI正在生成结果";
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
    .filter((log) => Boolean(log.answerStream?.content) && !log.answerStream?.isSubgraph)
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
    // DISABLED: We no longer show intermediate streaming text as an AI
    // reply card. The authoritative final answer comes from final_state
    // and is stored as a ChatMessage by the backend after the stream ends.
    // Intermediate tokens are shown in the progress log instead.
    return;
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
