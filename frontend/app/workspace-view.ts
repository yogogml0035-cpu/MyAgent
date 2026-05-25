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

export type LiveLogDiagnostics = {
  records: unknown[];
  displayRecords: unknown[];
  customDisplay: boolean;
  replaceDisplayOnMerge: boolean;
  rawJson: string;
  displayJson: string;
};

export type LiveToolLogItem = {
  id: string;
  kind: "tool";
  eventType: "tool_call" | "tool_result";
  createdAt?: string;
  completedAt?: string;
  level?: ExecutionLog["level"];
  stage?: NonNullable<ExecutionLog["live"]>["stage"];
  title: string;
  toolName?: string;
  parameterText?: string;
  resultText: string;
  resultStatus?: NonNullable<ExecutionLog["live"]>["resultStatus"];
  details: LiveLogDiagnostics;
  mergedEventCount?: number;
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
      level: "error",
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

export function formatLiveLogItemTime(item: LiveLogItem) {
  if (item.kind === "tool" && item.completedAt && item.completedAt !== item.createdAt) {
    const start = formatTime(item.createdAt);
    const end = formatTime(item.completedAt);
    if (start && end && start !== "--:--:--" && end !== "--:--:--") {
      return `${start}-${end}`;
    }
  }
  return formatTime(item.createdAt);
}

export function buildLogClipboardText(logs: ExecutionLog[]) {
  return logs.map(formatRawLogRecordJson).join("\n") || "暂无日志";
}

export function buildRunDiagnosticsJson(logs: ExecutionLog[]) {
  return formatDiagnosticJson(logs.map(buildRunDiagnosticRecord));
}

export function buildLiveLogItems(
  logs: ExecutionLog[],
  status: TaskStatus = "unknown",
): LiveLogItem[] {
  const items: LiveLogItem[] = [];
  const toolCallItemsByStageKey = new Map<string, LiveToolLogItem>();
  let hiddenDiagnosticLogs: ExecutionLog[] = [];
  let activeText = "";
  let activeCreatedAt: string | undefined;
  let activeDetails: LiveLogDiagnostics | undefined;
  let hasCancelEvent = false;
  let hasAnswerStream = false;
  let lastAnswerCreatedAt: string | undefined;
  let lastAnswerDetails: LiveLogDiagnostics | undefined;
  let answerStreamItem: LiveStatusLogItem | undefined;
  let answerStreamBaseDetails: LiveLogDiagnostics | undefined;
  let answerStreamChunkCount = 0;
  let answerStreamCharacterCount = 0;
  let answerStreamLastLog: ExecutionLog | undefined;
  let answerStreamLogs: ExecutionLog[] = [];
  let thinkingStreamItem: LiveStatusLogItem | undefined;
  let thinkingStreamBaseDetails: LiveLogDiagnostics | undefined;
  let thinkingStreamChunkCount = 0;
  let thinkingStreamCharacterCount = 0;
  let thinkingStreamLastLog: ExecutionLog | undefined;
  let thinkingStreamLogs: ExecutionLog[] = [];

  function consumeHiddenDiagnostics() {
    if (hiddenDiagnosticLogs.length === 0) {
      return undefined;
    }
    const details = buildLiveLogDiagnosticsFromRecords(
      hiddenDiagnosticLogs.map(rawLogRecordForDiagnostics),
      buildCompactHiddenLogDisplayRecords(hiddenDiagnosticLogs),
    );
    hiddenDiagnosticLogs = [];
    return details;
  }

  function mergeHiddenDiagnostics(details: LiveLogDiagnostics) {
    const hiddenDetails = consumeHiddenDiagnostics();
    return hiddenDetails ? mergeLiveLogDiagnostics(hiddenDetails, details) : details;
  }

  function clearThinkingStreamSegment() {
    thinkingStreamItem = undefined;
    thinkingStreamBaseDetails = undefined;
    thinkingStreamChunkCount = 0;
    thinkingStreamCharacterCount = 0;
    thinkingStreamLastLog = undefined;
    thinkingStreamLogs = [];
  }

  function clearAnswerStreamSegment() {
    answerStreamItem = undefined;
    answerStreamBaseDetails = undefined;
    answerStreamChunkCount = 0;
    answerStreamCharacterCount = 0;
    answerStreamLastLog = undefined;
    answerStreamLogs = [];
  }

  function finalizeThinkingStreamSegment() {
    if (thinkingStreamItem) {
      const rawRecords = buildClosedStreamRawRecords(thinkingStreamLogs);
      if (rawRecords.length > 0) {
        thinkingStreamItem.details = withLiveLogRawRecords(thinkingStreamItem.details, rawRecords);
      }
    }
    clearThinkingStreamSegment();
  }

  function finalizeAnswerStreamSegment() {
    if (answerStreamItem) {
      const rawRecords = buildClosedStreamRawRecords(answerStreamLogs);
      if (rawRecords.length > 0) {
        answerStreamItem.details = withLiveLogRawRecords(answerStreamItem.details, rawRecords);
      }
    }
    clearAnswerStreamSegment();
  }

  function pushStatusItem(log: ExecutionLog, text: string) {
    const previous = items.at(-1);
    const details = mergeHiddenDiagnostics(buildLogDiagnostics(log));
    if (previous?.kind === "status" && previous.text === text && !previous.active) {
      previous.details = mergeLiveLogDiagnostics(previous.details, details);
      previous.createdAt = previous.createdAt || log.createdAt;
      previous.level = log.level || previous.level;
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

  function upsertThinkingStreamItem(log: ExecutionLog) {
    const thinkingContent = log.thinkingStream?.content;
    if (!thinkingContent) {
      return;
    }
    thinkingStreamChunkCount += 1;
    thinkingStreamCharacterCount += thinkingContent.length;
    thinkingStreamLastLog = log;
    thinkingStreamLogs.push(log);
    const streamDetails = buildThinkingStreamDiagnostics({
      characterCount: thinkingStreamCharacterCount,
      chunkCount: thinkingStreamChunkCount,
      lastLog: thinkingStreamLastLog,
    });
    if (!thinkingStreamItem) {
      const previous = items.at(-1);
      if (previous?.kind === "status" && previous.text === "AI正在思考" && !previous.active) {
        thinkingStreamItem = previous;
        thinkingStreamBaseDetails = previous.details;
      } else {
        thinkingStreamBaseDetails = consumeHiddenDiagnostics();
        thinkingStreamItem = {
          id: `thinking:${log.id}`,
          kind: "status",
          createdAt: log.createdAt,
          level: log.level,
          text: "AI正在思考",
          details: streamDetails,
        };
        items.push(thinkingStreamItem);
      }
    }
    thinkingStreamItem.createdAt = thinkingStreamItem.createdAt || log.createdAt;
    thinkingStreamItem.level = log.level || thinkingStreamItem.level;
    thinkingStreamItem.details = thinkingStreamBaseDetails
      ? mergeLiveLogDiagnostics(thinkingStreamBaseDetails, streamDetails)
      : streamDetails;
    activeText = "AI正在思考";
    activeCreatedAt = log.createdAt || activeCreatedAt;
    activeDetails = thinkingStreamItem.details;
  }

  function upsertAnswerStreamItem(log: ExecutionLog) {
    const answerContent = log.answerStream?.content;
    if (!answerContent) {
      return;
    }
    hasAnswerStream = true;
    answerStreamChunkCount += 1;
    answerStreamCharacterCount += answerContent.length;
    answerStreamLastLog = log;
    answerStreamLogs.push(log);
    lastAnswerCreatedAt = log.createdAt;
    lastAnswerDetails = buildAnswerStreamDiagnostics({
      characterCount: answerStreamCharacterCount,
      chunkCount: answerStreamChunkCount,
      lastLog: answerStreamLastLog,
    });
    if (!answerStreamItem) {
      const previous = items.at(-1);
      if (previous?.kind === "status" && previous.text === "AI正在生成结果" && !previous.active) {
        answerStreamItem = previous;
        answerStreamBaseDetails = previous.details;
      } else {
        answerStreamBaseDetails = consumeHiddenDiagnostics();
        answerStreamItem = {
          id: `answer:${log.id}`,
          kind: "status",
          createdAt: log.createdAt,
          level: log.level,
          text: "AI正在生成结果",
          details: lastAnswerDetails,
        };
        items.push(answerStreamItem);
      }
    }
    answerStreamItem.createdAt = answerStreamItem.createdAt || log.createdAt;
    answerStreamItem.level = log.level || answerStreamItem.level;
    answerStreamItem.details = answerStreamBaseDetails
      ? mergeLiveLogDiagnostics(answerStreamBaseDetails, lastAnswerDetails)
      : lastAnswerDetails;
  }

  function upsertToolCallItem(log: ExecutionLog, live: NonNullable<ExecutionLog["live"]>) {
    const existing = findToolCallStageItem(toolCallItemsByStageKey, live);
    const isDelta = isToolCallDeltaLog(log, live);
    if (existing) {
      existing.createdAt = existing.createdAt || log.createdAt;
      existing.level = log.level || existing.level;
      existing.stage = live.stage;
      existing.title = formatLiveToolCallTitle(live);
      existing.toolName = live.toolName || existing.toolName;
      existing.parameterText = formatLiveToolParameterSummary(live.parameterItems) || existing.parameterText;
      if (isDelta) {
        existing.mergedEventCount = (existing.mergedEventCount ?? 1) + 1;
        existing.details = buildToolCallDeltaDiagnostics(log, existing.mergedEventCount);
      } else {
        existing.details = mergeLiveLogDiagnostics(existing.details, buildLogDiagnostics(log));
      }
      refreshToolEventDisplayJson(existing);
      return;
    }

    const toolItem: LiveToolLogItem = {
      id: `tool-call:${live.toolCallId ?? log.id}:${live.stage ?? "using_tool"}`,
      kind: "tool",
      eventType: "tool_call",
      createdAt: log.createdAt,
      level: log.level,
      stage: live.stage,
      title: formatLiveToolCallTitle(live),
      toolName: live.toolName,
      parameterText: formatLiveToolParameterSummary(live.parameterItems),
      resultText: formatLiveToolPendingText(live.toolName),
      details: isDelta ? buildToolCallDeltaDiagnostics(log, 1) : buildLogDiagnostics(log),
      mergedEventCount: isDelta ? 1 : undefined,
    };
    refreshToolEventDisplayJson(toolItem);
    items.push(toolItem);
    rememberToolCallStageItem(toolCallItemsByStageKey, toolItem, live);
  }

  const orderedLogs = [...logs].sort(byLogOrder);
  orderedLogs.forEach((log, index) => {
    if (log.type === "values_snapshot" || log.type === "final_answer") {
      hiddenDiagnosticLogs.push(log);
      return;
    }

    if (log.type === "assistant_answer_delta") {
      finalizeThinkingStreamSegment();
      upsertAnswerStreamItem(log);
      return;
    }

    if (log.type === "assistant_thinking_delta") {
      finalizeAnswerStreamSegment();
      upsertThinkingStreamItem(log);
      return;
    }

    finalizeThinkingStreamSegment();
    finalizeAnswerStreamSegment();

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
      upsertToolCallItem(log, live);
      return;
    }

    if (live.kind === "tool_result") {
      const toolItem: LiveToolLogItem = {
        id: `tool-result:${live.toolCallId ?? log.id ?? index}`,
        kind: "tool",
        eventType: "tool_result",
        createdAt: log.createdAt,
        level: log.level,
        stage: live.stage,
        title: formatLiveToolResultTitle(live),
        toolName: live.toolName,
        parameterText: formatLiveToolParameterSummary(live.parameterItems),
        resultStatus: live.resultStatus,
        resultText: formatLiveToolResultText(live),
        details: buildLogDiagnostics(log),
      };
      refreshToolEventDisplayJson(toolItem);
      items.push(toolItem);
      return;
    }

    if (log.type === "status_update") {
      const statusItem = pushStatusItem(log, "状态已更新");
      if (isTaskActive(status)) {
        activeText = "状态已更新";
        activeCreatedAt = log.createdAt || activeCreatedAt;
        activeDetails = statusItem.details;
      }
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
    const statusItem = pushStatusItem(log, text);
    activeText = text;
    activeCreatedAt = log.createdAt;
    activeDetails = statusItem.details;
  });

  if (!isTaskActive(status)) {
    finalizeThinkingStreamSegment();
    finalizeAnswerStreamSegment();
  }

  if (!isTaskActive(status) && hiddenDiagnosticLogs.length > 0) {
    const target = [...items].reverse().find((item) => item.kind === "status");
    const hiddenDetails = consumeHiddenDiagnostics();
    if (target && hiddenDetails) {
      target.details = mergeLiveLogDiagnostics(target.details, hiddenDetails);
    }
  }

  if (isTaskActive(status)) {
    // If there's a cancel event, show cancelled status instead of active thinking
    if (hasCancelEvent) {
      const trailingHiddenDetails = consumeHiddenDiagnostics();
      const mergedCancelDetails = trailingHiddenDetails
        ? activeDetails
          ? mergeLiveLogDiagnostics(activeDetails, trailingHiddenDetails)
          : trailingHiddenDetails
        : activeDetails;
      const lastItem = items.at(-1);
      if (
        lastItem?.kind === "status" &&
        lastItem.text === "任务已取消" &&
        lastItem.id.startsWith("status:")
      ) {
        lastItem.active = false;
        if (trailingHiddenDetails) {
          lastItem.details = mergeLiveLogDiagnostics(lastItem.details, trailingHiddenDetails);
        }
      } else {
        items.push({
          id: "status:cancelled",
          kind: "status",
          createdAt: activeCreatedAt,
          level: "warning",
          text: "任务已取消",
          active: false,
          details: mergedCancelDetails ?? buildSyntheticLogDiagnostics("task_cancelled", "任务已取消"),
        });
      }
    } else {
      const displayText = hasAnswerStream ? "AI正在生成结果" : activeText || "AI正在思考";
      const trailingHiddenDetails = consumeHiddenDiagnostics();
      const mergedActiveDetails = trailingHiddenDetails
        ? activeDetails
          ? mergeLiveLogDiagnostics(activeDetails, trailingHiddenDetails)
          : trailingHiddenDetails
        : activeDetails;
      const mergedAnswerDetails = trailingHiddenDetails && lastAnswerDetails
        ? mergeLiveLogDiagnostics(lastAnswerDetails, trailingHiddenDetails)
        : lastAnswerDetails;
      const lastItem = items.at(-1);
      if (lastItem?.kind === "status" && lastItem.text === displayText) {
        lastItem.active = true;
        lastItem.createdAt = lastAnswerCreatedAt || activeCreatedAt || lastItem.createdAt;
        lastItem.level = "info";
        if (mergedAnswerDetails && lastItem !== answerStreamItem) {
          lastItem.details = mergeLiveLogDiagnostics(lastItem.details, mergedAnswerDetails);
        } else if (trailingHiddenDetails) {
          lastItem.details = mergeLiveLogDiagnostics(lastItem.details, trailingHiddenDetails);
        }
      } else {
        items.push({
          id: "status:active",
          kind: "status",
          createdAt: lastAnswerCreatedAt || activeCreatedAt,
          level: "info",
          text: displayText,
          active: true,
          details: mergedAnswerDetails
            ?? mergedActiveDetails
            ?? buildSyntheticLogDiagnostics("active_status", displayText),
        });
      }
    }
  }

  return items;
}

export function formatLiveLogItemClipboardText(item: LiveLogItem) {
  const time = formatLiveLogItemTime(item);
  if (item.kind === "tool") {
    return `${time} ${item.title} -> ${item.resultText}`;
  }
  return `${time} ${item.text}`;
}

function formatRawLogRecordJson(log: ExecutionLog) {
  return JSON.stringify(buildRunDiagnosticRecord(log));
}

function buildRunDiagnosticRecord(log: ExecutionLog) {
  const fallback = fallbackRawLogRecord(log);
  if (log.memoryContext || !isPlainRecord(log.rawRecord)) {
    return compactDiagnosticRecord(fallback);
  }

  const mergedRecord: Record<string, unknown> = {
    ...fallback,
    ...log.rawRecord,
  };
  const fallbackPayload = isPlainRecord(fallback.payload) ? fallback.payload : undefined;
  const rawPayload = isPlainRecord(log.rawRecord.payload) ? log.rawRecord.payload : undefined;
  if (fallbackPayload || rawPayload) {
    mergedRecord.payload = stripUndefinedValues({
      ...(fallbackPayload ?? {}),
      ...(rawPayload ?? {}),
    });
  }

  return stripUndefinedValues(compactDiagnosticRecord(mergedRecord));
}

function fallbackRawLogRecord(log: ExecutionLog) {
  return stripUndefinedValues({
    id: log.id,
    seq: log.seq,
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
      thinking_stream: log.thinkingStream,
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
  return buildLiveLogDiagnosticsFromRecord(rawLogRecordForDiagnostics(log));
}

const TOOL_CALL_PARTIAL_ARG_PREVIEW_CHARS = 800;
const CLOSED_STREAM_RAW_RECORD_LIMIT = 20;

function compactDiagnosticRecord(record: Record<string, unknown>): Record<string, unknown> {
  const payload = isPlainRecord(record.payload) ? record.payload : undefined;
  if (!payload) {
    return record;
  }

  const compactPayload = compactDiagnosticPayload(payload);
  return compactPayload === payload ? record : { ...record, payload: compactPayload };
}

function compactDiagnosticPayload(payload: Record<string, unknown>): Record<string, unknown> {
  let changed = false;
  const next: Record<string, unknown> = { ...payload };

  if (isPartialToolCallPayload(payload)) {
    for (const key of ["args", "raw_args", "rawArgs"]) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        continue;
      }
      const compacted = compactToolCallArgumentValue(payload[key]);
      if (compacted.truncated) {
        next[key] = compacted.value;
        next[`${key}_truncated`] = true;
        next[`${key}_original_chars`] = compacted.originalChars;
        changed = true;
      }
    }
  }

  const toolCalls = payload.tool_calls;
  if (Array.isArray(toolCalls)) {
    const compactedToolCalls = toolCalls.map((entry) =>
      isPlainRecord(entry) ? compactDiagnosticPayload(entry) : entry,
    );
    if (compactedToolCalls.some((entry, index) => entry !== toolCalls[index])) {
      next.tool_calls = compactedToolCalls;
      changed = true;
    }
  }

  return changed ? next : payload;
}

function isPartialToolCallPayload(payload: Record<string, unknown>) {
  if (payload.partial === true || payload.is_partial === true || payload.isPartial === true) {
    return true;
  }
  const live = isPlainRecord(payload.live) ? payload.live : undefined;
  return live?.diagnostic_label === "tool_call_delta" || live?.diagnosticLabel === "tool_call_delta";
}

function compactToolCallArgumentValue(value: unknown) {
  const text = typeof value === "string" ? value : formatDiagnosticJson(value);
  if (text.length <= TOOL_CALL_PARTIAL_ARG_PREVIEW_CHARS) {
    return { value, truncated: false, originalChars: text.length };
  }
  return {
    value: `${text.slice(0, TOOL_CALL_PARTIAL_ARG_PREVIEW_CHARS).trimEnd()}...`,
    truncated: true,
    originalChars: text.length,
  };
}

function isToolCallDeltaLog(
  log: ExecutionLog,
  live: NonNullable<ExecutionLog["live"]>,
) {
  if (log.type !== "tool_call" || live.kind !== "tool_call") {
    return false;
  }
  if (live.diagnosticLabel === "tool_call_delta" || live.stage === "selecting_tool") {
    return true;
  }
  const payload = isPlainRecord(log.rawRecord?.payload) ? log.rawRecord.payload : undefined;
  return Boolean(payload && isPartialToolCallPayload(payload));
}

function buildToolCallDeltaDiagnostics(
  log: ExecutionLog,
  deltaCount: number,
): LiveLogDiagnostics {
  const record = buildRunDiagnosticRecord(log);
  const payload = isPlainRecord(record.payload) ? record.payload : {};
  const summaryRecord = stripUndefinedValues({
    ...record,
    payload: {
      ...payload,
      tool_call_delta_count: deltaCount,
      earlier_tool_call_deltas_hidden: deltaCount > 1,
    },
  });
  return buildLiveLogDiagnosticsFromRecords([summaryRecord], summaryRecord, {
    replaceDisplayOnMerge: true,
  });
}

function buildAnswerStreamDiagnostics({
  characterCount,
  chunkCount,
  lastLog,
}: {
  characterCount: number;
  chunkCount: number;
  lastLog: ExecutionLog | undefined;
}): LiveLogDiagnostics {
  const payload = stripUndefinedValues({
    answer_stream: stripUndefinedValues({
      schema_version: lastLog?.answerStream?.schemaVersion ?? 1,
      chunk_count: chunkCount,
      character_count: characterCount,
      content_hidden: true,
    }),
  });
  const summaryRecord = stripUndefinedValues({
    type: "assistant_answer_delta",
    message: "AI正在生成结果",
    created_at: lastLog?.createdAt,
    run_id: lastLog?.runId ?? undefined,
    payload,
  });
  return buildStreamStatusDiagnostics({
    summaryRecord,
  });
}

function buildThinkingStreamDiagnostics({
  characterCount,
  chunkCount,
  lastLog,
}: {
  characterCount: number;
  chunkCount: number;
  lastLog: ExecutionLog | undefined;
}): LiveLogDiagnostics {
  const payload = stripUndefinedValues({
    thinking_stream: stripUndefinedValues({
      schema_version: lastLog?.thinkingStream?.schemaVersion ?? 1,
      chunk_count: chunkCount,
      character_count: characterCount,
      content_hidden: true,
    }),
  });
  const summaryRecord = stripUndefinedValues({
    type: "assistant_thinking_delta",
    message: "AI正在思考",
    created_at: lastLog?.createdAt,
    run_id: lastLog?.runId ?? undefined,
    payload,
  });
  return buildStreamStatusDiagnostics({
    summaryRecord,
  });
}

function buildStreamStatusDiagnostics({
  summaryRecord,
}: {
  summaryRecord: Record<string, unknown>;
}): LiveLogDiagnostics {
  return buildLiveLogDiagnosticsFromRecords([summaryRecord], summaryRecord, {
    replaceDisplayOnMerge: true,
  });
}

function buildSyntheticLogDiagnostics(type: string, message: string): LiveLogDiagnostics {
  return buildLiveLogDiagnosticsFromRecord({ type, message });
}

function mergeLiveLogDiagnostics(
  first: LiveLogDiagnostics | undefined,
  second: LiveLogDiagnostics,
): LiveLogDiagnostics {
  if (!first) {
    return second;
  }
  const mergedDisplayRecords = second.replaceDisplayOnMerge
    ? second.displayRecords
    : first.replaceDisplayOnMerge
      ? first.displayRecords
      : [...first.displayRecords, ...second.displayRecords];
  return buildLiveLogDiagnosticsFromRecords(
    [...first.records, ...second.records],
    mergedDisplayRecords,
    {
      replaceDisplayOnMerge: second.replaceDisplayOnMerge || first.replaceDisplayOnMerge,
    },
  );
}

function rawLogRecordForDiagnostics(log: ExecutionLog) {
  return buildRunDiagnosticRecord(log);
}

function buildLiveLogDiagnosticsFromRecord(
  record: unknown,
  displayRecord?: unknown,
): LiveLogDiagnostics {
  return buildLiveLogDiagnosticsFromRecords([record], displayRecord);
}

function buildLiveLogDiagnosticsFromRecords(
  records: unknown[],
  displayRecord?: unknown | unknown[],
  options: { replaceDisplayOnMerge?: boolean } = {},
): LiveLogDiagnostics {
  const normalizedRecords = records.map(normalizeDiagnosticRecord);
  const normalizedDisplayRecords =
    displayRecord === undefined
      ? normalizedRecords
      : Array.isArray(displayRecord)
        ? displayRecord.map(normalizeDiagnosticRecord)
        : [normalizeDiagnosticRecord(displayRecord)];
  return {
    records: normalizedRecords,
    displayRecords: normalizedDisplayRecords,
    customDisplay: displayRecord !== undefined,
    replaceDisplayOnMerge: options.replaceDisplayOnMerge ?? false,
    rawJson: formatDiagnosticRecords(normalizedRecords),
    displayJson: formatDiagnosticRecords(normalizedDisplayRecords),
  };
}

function normalizeDiagnosticRecord(record: unknown): unknown {
  return isPlainRecord(record) ? stripUndefinedValues(record) : record;
}

function formatDiagnosticJson(record: unknown) {
  return JSON.stringify(record, null, 2) ?? "null";
}

function formatDiagnosticRecords(records: unknown[]) {
  return formatDiagnosticJson(records.length === 1 ? records[0] : { records });
}

function withLiveLogDisplayRecord(
  details: LiveLogDiagnostics,
  displayRecord: unknown,
): LiveLogDiagnostics {
  return buildLiveLogDiagnosticsFromRecords(details.records, [displayRecord], {
    replaceDisplayOnMerge: true,
  });
}

function withLiveLogRawRecords(
  details: LiveLogDiagnostics,
  rawRecords: unknown[],
): LiveLogDiagnostics {
  return buildLiveLogDiagnosticsFromRecords(
    [...details.records, ...rawRecords],
    details.displayRecords,
    {
      replaceDisplayOnMerge: details.replaceDisplayOnMerge,
    },
  );
}

function buildClosedStreamRawRecords(logs: ExecutionLog[]) {
  const rawRecords = logs.flatMap((log) =>
    isPlainRecord(log.rawRecord) ? [buildRunDiagnosticRecord(log)] : [],
  );
  if (rawRecords.length <= CLOSED_STREAM_RAW_RECORD_LIMIT) {
    return rawRecords;
  }

  const firstLog = logs[0];
  const lastLog = logs.at(-1);
  const streamType = lastLog?.type ?? firstLog?.type ?? "stream_delta";
  return [
    stripUndefinedValues({
      type: streamType,
      message:
        streamType === "assistant_answer_delta"
          ? "AI生成流式片段已压缩"
          : "AI思考流式片段已压缩",
      created_at: lastLog?.createdAt ?? firstLog?.createdAt,
      run_id: lastLog?.runId ?? firstLog?.runId,
      payload: {
        schema_version: 1,
        chunk_count: rawRecords.length,
        content_hidden: true,
        omitted_raw_record_count: Math.max(0, rawRecords.length - 1),
      },
    }),
  ];
}

function buildCompactHiddenLogDisplayRecords(logs: ExecutionLog[]) {
  return logs.map((log) => {
    if (log.type === "values_snapshot") {
      return stripUndefinedValues({
        type: "values_snapshot",
        message: "状态快照已省略",
        created_at: log.createdAt,
        run_id: log.runId,
        payload: {
          content_hidden: true,
        },
      });
    }
    if (log.type === "final_answer") {
      return stripUndefinedValues({
        type: "final_answer",
        message: "最终回复正文已省略",
        created_at: log.createdAt,
        run_id: log.runId,
        payload: {
          content_hidden: true,
        },
      });
    }
    return rawLogRecordForDiagnostics(log);
  });
}

const TOOL_RESULT_DISPLAY_JSON_MAX_BYTES = 100 * 1024;
const TOOL_RESULT_DISPLAY_PREVIEW_CHARS = 4096;

function refreshToolEventDisplayJson(item: LiveToolLogItem) {
  item.details = withLiveLogDisplayRecord(item.details, buildToolEventDisplayRecord(item));
}

function buildToolEventDisplayRecord(item: LiveToolLogItem) {
  if (item.eventType === "tool_call") {
    return buildToolCallDisplayRecord(item);
  }
  return buildToolResultDisplayRecord(item);
}

function buildToolCallDisplayRecord(item: LiveToolLogItem) {
  const toolCalls = item.details.records
    .map(readToolCallDiagnostic)
    .filter((call): call is NonNullable<ReturnType<typeof readToolCallDiagnostic>> => Boolean(call));
  const finalToolCall =
    [...toolCalls].reverse().find((call) => call.partial !== true) ?? toolCalls.at(-1);
  const toolName = finalToolCall?.toolName ?? item.toolName;

  return stripUndefinedValues({
    type: "tool_call",
    stage: item.stage,
    created_at: item.createdAt ?? finalToolCall?.createdAt,
    tool_name: toolName,
    tool_label:
      finalToolCall?.toolLabel ??
      (toolName ? formatLiveToolLabel({ toolName } as NonNullable<ExecutionLog["live"]>) : undefined),
    tool_call_id: finalToolCall?.toolCallId,
    args: finalToolCall?.args,
    args_truncated: finalToolCall?.argsTruncated,
    args_original_chars: finalToolCall?.argsOriginalChars,
    delta_count: item.mergedEventCount && item.mergedEventCount > 1 ? item.mergedEventCount : undefined,
  });
}

function buildToolResultDisplayRecord(item: LiveToolLogItem) {
  const toolResults = item.details.records
    .map(readToolResultDiagnostic)
    .filter((result): result is NonNullable<ReturnType<typeof readToolResultDiagnostic>> => Boolean(result));
  const finalToolResult = toolResults.at(-1);
  const toolName = finalToolResult?.toolName ?? item.toolName;

  return capToolResultDisplayRecord(
    stripUndefinedValues({
      type: "tool_result",
      created_at: item.createdAt ?? finalToolResult?.createdAt,
      tool_name: toolName,
      tool_label:
        finalToolResult?.toolLabel ??
        (toolName ? formatLiveToolLabel({ toolName } as NonNullable<ExecutionLog["live"]>) : undefined),
      tool_call_id: finalToolResult?.toolCallId,
      status: finalToolResult?.status ?? item.resultStatus,
      content: finalToolResult?.content,
    }),
  );
}

function readToolCallDiagnostic(record: unknown) {
  if (!isPlainRecord(record)) {
    return undefined;
  }
  const payload = readDiagnosticPayload(record);
  const live = readDiagnosticLive(record, payload);
  const type = readDiagnosticString(record.type, payload.type);
  const liveKind = readDiagnosticString(live?.kind);
  if (type !== "tool_call" && liveKind !== "tool_call") {
    return undefined;
  }

  const argsValue =
    payload.args ??
    payload.arguments ??
    payload.raw_args ??
    payload.rawArgs ??
    payload.input ??
    readDiagnosticParameterItems(live);

  return {
    createdAt: readDiagnosticString(record.created_at, record.createdAt),
    toolName: readDiagnosticString(
      payload.name,
      payload.tool_name,
      payload.toolName,
      live?.tool_name,
      live?.toolName,
    ),
    toolLabel: readDiagnosticString(payload.tool_label, payload.toolLabel, live?.tool_label, live?.toolLabel),
    toolCallId: readDiagnosticString(
      payload.id,
      payload.tool_call_id,
      payload.toolCallId,
      live?.tool_call_id,
      live?.toolCallId,
    ),
    partial: readDiagnosticBoolean(payload.partial, payload.is_partial, payload.isPartial),
    args: normalizeToolArguments(argsValue),
    argsTruncated: readDiagnosticBoolean(
      payload.args_truncated,
      payload.argsTruncated,
      payload.raw_args_truncated,
      payload.rawArgs_truncated,
      payload.rawArgsTruncated,
    ),
    argsOriginalChars: readDiagnosticNumber(
      payload.args_original_chars,
      payload.argsOriginalChars,
      payload.raw_args_original_chars,
      payload.rawArgs_original_chars,
      payload.rawArgsOriginalChars,
    ),
  };
}

function readToolResultDiagnostic(record: unknown) {
  if (!isPlainRecord(record)) {
    return undefined;
  }
  const payload = readDiagnosticPayload(record);
  const live = readDiagnosticLive(record, payload);
  const type = readDiagnosticString(record.type, payload.type);
  const liveKind = readDiagnosticString(live?.kind);
  if (type !== "tool_result" && liveKind !== "tool_result") {
    return undefined;
  }

  const content = readDiagnosticPayloadValue(payload, ["content", "result", "output"]);

  return {
    createdAt: readDiagnosticString(record.created_at, record.createdAt),
    toolName: readDiagnosticString(
      payload.name,
      payload.tool_name,
      payload.toolName,
      live?.tool_name,
      live?.toolName,
    ),
    toolLabel: readDiagnosticString(payload.tool_label, payload.toolLabel, live?.tool_label, live?.toolLabel),
    toolCallId: readDiagnosticString(
      payload.id,
      payload.tool_call_id,
      payload.toolCallId,
      live?.tool_call_id,
      live?.toolCallId,
    ),
    status: readDiagnosticString(
      payload.status,
      payload.result_status,
      payload.resultStatus,
      live?.result_status,
      live?.resultStatus,
    ),
    content: normalizeToolResultContent(content),
  };
}

function readDiagnosticPayload(record: Record<string, unknown>) {
  return isPlainRecord(record.payload) ? record.payload : {};
}

function readDiagnosticLive(
  record: Record<string, unknown>,
  payload: Record<string, unknown>,
) {
  if (isPlainRecord(payload.live)) {
    return payload.live;
  }
  return isPlainRecord(record.live) ? record.live : undefined;
}

function readDiagnosticString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return undefined;
}

function readDiagnosticBoolean(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "boolean") {
      return value;
    }
  }
  return undefined;
}

function readDiagnosticNumber(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return undefined;
}

function readDiagnosticPayloadValue(
  payload: Record<string, unknown>,
  keys: string[],
) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      return payload[key];
    }
  }
  return undefined;
}

function readDiagnosticParameterItems(live: Record<string, unknown> | undefined) {
  const parameterItems = live?.parameter_items ?? live?.parameterItems;
  if (!Array.isArray(parameterItems)) {
    return undefined;
  }
  const entries = parameterItems.flatMap((item) => {
    if (!isPlainRecord(item) || typeof item.key !== "string") {
      return [];
    }
    return [[item.key, item.value]] as const;
  });
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}

function normalizeToolArguments(value: unknown) {
  if (typeof value === "string") {
    return parseJsonStringIfPossible(value);
  }
  return value;
}

function normalizeToolResultContent(value: unknown) {
  if (typeof value === "string") {
    const parsed = parseJsonStringIfPossible(value);
    return isPlainRecord(parsed) || Array.isArray(parsed) ? parsed : value;
  }
  return value;
}

function parseJsonStringIfPossible(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return value;
  }
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return value;
  }
}

function capToolResultDisplayRecord(displayRecord: Record<string, unknown>) {
  const serialized = formatDiagnosticJson(displayRecord);
  if (getSerializedSizeBytes(serialized) <= TOOL_RESULT_DISPLAY_JSON_MAX_BYTES) {
    return displayRecord;
  }

  if (!Object.prototype.hasOwnProperty.call(displayRecord, "content")) {
    return {
      ...displayRecord,
      display_truncated: true,
      display_truncation: {
        original_serialized_size_bytes: getSerializedSizeBytes(serialized),
        max_serialized_size_bytes: TOOL_RESULT_DISPLAY_JSON_MAX_BYTES,
      },
    };
  }

  const content = displayRecord.content;
  const contentSerialized =
    typeof content === "string" ? content : formatDiagnosticJson(content);
  return stripUndefinedValues({
    ...displayRecord,
    content: {
      truncated: true,
      preview: contentSerialized.slice(0, TOOL_RESULT_DISPLAY_PREVIEW_CHARS),
    },
    content_truncated: true,
    content_truncation: {
      original_serialized_size_bytes: getSerializedSizeBytes(contentSerialized),
      max_serialized_size_bytes: TOOL_RESULT_DISPLAY_JSON_MAX_BYTES,
    },
  });
}

function getSerializedSizeBytes(value: string) {
  return new TextEncoder().encode(value).length;
}

function rememberToolCallStageItem(
  toolCallItemsByStageKey: Map<string, LiveToolLogItem>,
  toolItem: LiveToolLogItem,
  live: NonNullable<ExecutionLog["live"]>,
) {
  const key = getToolCallStageKey(live);
  if (key) {
    toolCallItemsByStageKey.set(key, toolItem);
  }
}

function findToolCallStageItem(
  toolCallItemsByStageKey: Map<string, LiveToolLogItem>,
  live: NonNullable<ExecutionLog["live"]>,
) {
  const key = getToolCallStageKey(live);
  if (key) {
    const matched = toolCallItemsByStageKey.get(key);
    if (matched) {
      return matched;
    }
  }
  return undefined;
}

function getToolCallStageKey(live: NonNullable<ExecutionLog["live"]>) {
  if (!live.toolCallId || !live.stage) {
    return undefined;
  }
  return `${live.toolCallId}:${live.stage}`;
}

function formatLiveToolCallTitle(live: NonNullable<ExecutionLog["live"]>) {
  const label = formatLiveToolLabel(live);
  return `${live.stage === "selecting_tool" ? "准备调用" : "调用"}${label === "调用工具" ? "工具" : label}`;
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

function formatLiveToolParameterSummary(
  parameterItems: NonNullable<ExecutionLog["live"]>["parameterItems"] = [],
) {
  return parameterItems
    .map((item) => {
      const suffix = item.truncated ? "..." : "";
      return `${item.key}=${formatLiveParameterValue(item.value)}${suffix}`;
    })
    .join("; ");
}

function formatLiveParameterValue(value: string | number | boolean) {
  if (typeof value === "string") {
    return value.replace(/\s+/g, " ").trim();
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
  if (log.agentActivity) {
    return formatAgentActivityPhase(log.agentActivity.phase);
  }
  if (log.reasoning) {
    return "AI正在思考...";
  }
  if (log.type === "assistant_thinking_delta") {
    return "AI正在思考...";
  }
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
  if (log.type === "assistant_answer_delta") {
    return "";
  }
  if (log.type === "status_update") {
    return "AI正在更新状态";
  }
  if (log.type === "tool_call" || log.type === "tool_result") {
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

function isDeliverableFailureMessage(message: ChatMessage) {
  const content = message.content.trim();
  return (
    message.role === "assistant" &&
    (content.includes("文件未成功生成或未能登记为下载文件") ||
      content.includes("文件未生成或未登记为产物"))
  );
}

export function getMessagePanelTone(message: ChatMessage): MessagePanelTone {
  if (message.level === "error") {
    return "error";
  }
  if (isDeliverableFailureMessage(message)) {
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

function byLogOrder(left: ExecutionLog, right: ExecutionLog) {
  if (typeof left.seq === "number" && typeof right.seq === "number" && left.seq !== right.seq) {
    return left.seq - right.seq;
  }
  if (typeof left.seq === "number" && typeof right.seq !== "number") {
    return -1;
  }
  if (typeof left.seq !== "number" && typeof right.seq === "number") {
    return 1;
  }
  return byCreatedAt(left, right);
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
      return byLogOrder(left, right);
    });
  return streamLogs.map((log) => log.answerStream!.content).join("");
}

const PUNCTUATION_PATTERN = /[。，！？、；：""''（）【】《》.,!?;:"'()\[\]{}]/g;
const ARTIFACT_SUMMARY_MAX_CHARS = 220;
const DELIVERY_ARTIFACT_NOTE_PREFIX = "已生成";
const DELIVERY_ARTIFACT_EXTENSIONS = /\.(docx|pptx|xlsx|xlsm|pdf|html|md)\b/i;
const ARTIFACT_SUMMARY_SPLIT_PATTERN = /[。！？!?；;，,]/;

function hasMeaningfulContent(content: string): boolean {
  const stripped = content.replace(PUNCTUATION_PATTERN, "");
  return stripped.trim().length > 0;
}

function truncateArtifactSummary(value: string, maxChars: number) {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

function normalizeArtifactSummaryLine(line: string) {
  return line
    .trim()
    .replace(/^#{1,6}\s+/, "")
    .replace(/^[-*+]\s+/, "")
    .replace(/^\d+[.)]\s+/, "")
    .trim();
}

function buildArtifactSummaryExcerpt(line: string) {
  const clause = normalizeArtifactSummaryLine(line)
    .split(ARTIFACT_SUMMARY_SPLIT_PATTERN)
    .map((part) => part.trim())
    .find(Boolean);
  return clause ?? "";
}

function isArtifactDeliveryLine(line: string) {
  const normalized = normalizeArtifactSummaryLine(line);
  if (!normalized) {
    return true;
  }
  if (
    /^(保存路径|输出路径|文件路径|文件位置|下载路径|已保存到|已生成到|保存于|存放于|附件路径)[:：]/i.test(
      normalized,
    )
  ) {
    return true;
  }
  if (
    /^(已保存|已生成|已写入|文件已生成|报告已生成|文档已生成).*(\.docx|\.pptx|\.xlsx|\.xlsm|\.pdf|\.html|\.md)\b/i.test(
      normalized,
    )
  ) {
    return true;
  }
  if (DELIVERY_ARTIFACT_EXTENSIONS.test(normalized) && /[\\/]/.test(normalized)) {
    return true;
  }
  return DELIVERY_ARTIFACT_EXTENSIONS.test(normalized) && normalized.length <= 120;
}

function buildArtifactDeliveryNote(artifacts: Artifact[]) {
  if (artifacts.length <= 1) {
    return `${DELIVERY_ARTIFACT_NOTE_PREFIX} 1 个交付文件，请使用下方下载卡片获取。`;
  }
  return `${DELIVERY_ARTIFACT_NOTE_PREFIX} ${artifacts.length} 个交付文件，请使用下方下载卡片获取。`;
}

function buildAssistantArtifactSummary(message: ChatMessage, artifacts: Artifact[]) {
  const deliveryNote = buildArtifactDeliveryNote(artifacts);
  const normalizedContent = message.content.replace(/\r\n/g, "\n").trim();
  if (!normalizedContent) {
    return deliveryNote;
  }

  const summarySource =
    normalizedContent
      .split(/\n+/)
      .map(buildArtifactSummaryExcerpt)
      .find((line) => line && !isArtifactDeliveryLine(line)) ??
    normalizedContent.replace(/\s+/g, " ").trim();

  const summaryText = truncateArtifactSummary(summarySource, ARTIFACT_SUMMARY_MAX_CHARS);
  if (!summaryText || summaryText === deliveryNote) {
    return deliveryNote;
  }

  const normalizedSummary = /[。！？.!?]$/.test(summaryText) ? summaryText : `${summaryText}。`;
  return `${normalizedSummary}\n\n${deliveryNote}`;
}

function projectAssistantMessage(message: ChatMessage, artifacts: Artifact[]) {
  if (message.role !== "assistant" || artifacts.length === 0) {
    return message;
  }
  return {
    ...message,
    content: buildAssistantArtifactSummary(message, artifacts),
  };
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
      .sort(byLogOrder);
    const accumulatedAnswer = accumulateStreamedAnswer(runLogs);
    const lastStreamLog = runLogs
      .filter((log) => Boolean(log.answerStream?.content))
      .sort((left, right) => {
        const leftIndex = left.answerStream?.streamIndex ?? 0;
        const rightIndex = right.answerStream?.streamIndex ?? 0;
        if (leftIndex !== rightIndex) return leftIndex - rightIndex;
        return byLogOrder(left, right);
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
      logs: visibleFallbackLogs.sort(byLogOrder),
      artifacts: fallbackArtifacts.map((artifact) => artifactForRenderedRun("legacy", artifact)),
    });
  }

  return groups.filter(
    (group) =>
      group.logs.length > 0 ||
      group.artifacts.length > 0 ||
      group.status === "running" ||
      group.status === "needs_input",
  );
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
  const groupsByRunId = new Map(groups.map((group) => [group.runId, group]));
  const remainingGroups = new Map(groups.map((group) => [group.runId, group]));
  const firstReplyIndexByRunId = new Map<string, number>();
  const lastMessageIndexByRunId = new Map<string, number>();
  const lastVisibleAssistantIndexByRunId = new Map<string, number>();
  const renderedArtifactRuns = new Set<string>();

  messages.forEach((message, index) => {
    if (message.runId) {
      lastMessageIndexByRunId.set(message.runId, index);
      if (message.role !== "user" && !firstReplyIndexByRunId.has(message.runId)) {
        firstReplyIndexByRunId.set(message.runId, index);
      }
      if (message.role === "assistant" && !isPlaceholderAssistantMessage(message)) {
        lastVisibleAssistantIndexByRunId.set(message.runId, index);
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
    if (renderedArtifactRuns.has(group.runId)) {
      return;
    }
    group.artifacts.forEach((artifact) => {
      items.push({
        id: `artifact:${group.runId}:${artifact.name}`,
        kind: "artifact",
        group,
        artifact,
      });
    });
    renderedArtifactRuns.add(group.runId);
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
    const assistantArtifacts =
      message.runId &&
      message.role === "assistant" &&
      lastVisibleAssistantIndexByRunId.get(message.runId) === index
        ? (groupsByRunId.get(message.runId)?.artifacts ?? [])
        : [];
    if (!isPlaceholder) {
      items.push({
        id: `message:${message.id}`,
        kind: "message",
        message: projectAssistantMessage(message, assistantArtifacts),
        assistantArtifacts: assistantArtifacts.length > 0 ? assistantArtifacts : undefined,
        groupTitle: assistantArtifacts.length > 0 ? groupsByRunId.get(message.runId ?? "")?.title : undefined,
      });
      if (assistantArtifacts.length > 0 && message.runId) {
        renderedArtifactRuns.add(message.runId);
      }
    }

    if (
      message.runId &&
      lastMessageIndexByRunId.get(message.runId) === index &&
      !lastVisibleAssistantIndexByRunId.has(message.runId)
    ) {
      const group = groupBeforeReply ?? pushGroup(message.runId);
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
