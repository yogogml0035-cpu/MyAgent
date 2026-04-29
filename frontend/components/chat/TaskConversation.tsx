"use client";

import { useEffect, useRef } from "react";
import type { Artifact, ChatMessage, ExecutionLog } from "../../app/task-state";
import { isTaskActive } from "../../app/task-state";
import {
  type ConversationStreamItem,
  calculateLogProgress,
  countReasoningLogs,
  formatAgentActivityKindLabel,
  formatAgentActivityPhaseLabel,
  formatAgentActivityStatusLabel,
  formatFileAuditOperationLabel,
  formatFileAuditStatusLabel,
  formatLogLevelLabel,
  formatMessagePanelStatus,
  formatMessagePanelTitle,
  formatReasoningPhaseLabel,
  formatRunLogStatus,
  formatSearchTraceKindLabel,
  formatTime,
  getMessagePanelTone,
  partitionVisibleLogs,
} from "../../app/workspace-view";
import { RobotAvatar } from "./RobotAvatar";

type TaskConversationProps = {
  conversationStreamItems: ConversationStreamItem[];
  copiedCopyKey: string;
  expandedReasoningRuns: Record<string, boolean>;
  hasConversation: boolean;
  noticeMessages: ChatMessage[];
  onCopyLogs: (logs: ExecutionLog[], copyKey?: string) => Promise<void>;
  onCopyText: (text: string, failureMessage?: string, copyKey?: string) => Promise<void>;
  onDownloadArtifact: (artifact: Artifact) => Promise<void>;
  onOpenArtifact: (artifact: Artifact) => Promise<void>;
  onToggleReasoningRun: (runId: string) => void;
};

export function TaskConversation({
  conversationStreamItems,
  copiedCopyKey,
  expandedReasoningRuns,
  hasConversation,
  noticeMessages,
  onCopyLogs,
  onCopyText,
  onDownloadArtifact,
  onOpenArtifact,
  onToggleReasoningRun,
}: TaskConversationProps) {
  const conversationCanvasRef = useRef<HTMLElement | null>(null);

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
      const userCopyKey = `message:${message.id}:user`;
      const isUserMessageCopied = copiedCopyKey === userCopyKey;
      const userCopyButtonClassName = [
        "copyButton",
        "userCopyButton",
        isUserMessageCopied ? "copyButton-copied" : "",
      ]
        .filter(Boolean)
        .join(" ");

      return (
        <div className="userMessageRow" key={key}>
          <div className="userMessageFrame">
            <article className={messageClassName}>
              <p>{message.content}</p>
            </article>
            <div className="userMessageMeta">
              <time className="userMessageTime">{formatTime(message.createdAt, "short")}</time>
              <button
                aria-label={isUserMessageCopied ? "已复制用户消息" : "复制用户消息"}
                className={userCopyButtonClassName}
                disabled={!message.content}
                onClick={() => void onCopyText(message.content, undefined, userCopyKey)}
                title={isUserMessageCopied ? "已复制" : "复制用户消息"}
                type="button"
              >
                <span aria-hidden="true" />
              </button>
            </div>
          </div>
          <div className="userMarker" aria-hidden="true" />
        </div>
      );
    }

    const assistantCopyKey = `message:${message.id}:${message.role}`;
    const isAssistantMessageCopied = copiedCopyKey === assistantCopyKey;
    const assistantCopyButtonClassName = [
      "copyButton",
      isAssistantMessageCopied ? "copyButton-copied" : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <section className="assistantMessageRow" key={key}>
        <RobotAvatar />
        <article className={messageClassName}>
          <header className="messageCardHeader">
            <div className="messageCardTitle">
              <RobotAvatar variant="title" />
              <strong>{formatMessagePanelTitle(message)}</strong>
              <span className={`statusGlyph statusGlyph-${tone}`} aria-hidden="true" />
              <span>{formatMessagePanelStatus(message)}</span>
            </div>
            <button
              aria-label={isAssistantMessageCopied ? "已复制AI内容" : "复制AI内容"}
              className={assistantCopyButtonClassName}
              disabled={!message.content}
              onClick={() => void onCopyText(message.content, undefined, assistantCopyKey)}
              title={isAssistantMessageCopied ? "已复制" : "复制AI内容"}
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
        <RobotAvatar />
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
                  onClick={() => void onOpenArtifact(artifact)}
                  type="button"
                >
                  打开报告
                </button>
              ) : null}
              <button
                className="downloadPrimaryButton"
                onClick={() => void onDownloadArtifact(artifact)}
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

  function renderRunItem(item: Extract<ConversationStreamItem, { kind: "run" }>) {
    const group = item.group;
    const groupActive = isTaskActive(group.status);
    const groupProgress = calculateLogProgress(group.logs.length);
    const groupLogStatusText = formatRunLogStatus(group.status);
    const logCopyKey = `logs:${group.runId}`;
    const isLogCopied = copiedCopyKey === logCopyKey;
    const logCopyButtonClassName = [
      "copyButton",
      isLogCopied ? "copyButton-copied" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const reasoningCount = countReasoningLogs(group.logs);
    const reasoningExpanded = Boolean(expandedReasoningRuns[group.runId]);
    const { visibleLogs, hiddenReasoningCount } = partitionVisibleLogs(group.logs, {
      expanded: reasoningExpanded,
    });
    const showReasoningToggle =
      hiddenReasoningCount > 0 || (reasoningExpanded && reasoningCount > 3);

    return (
      <section className="traceRow" aria-label={`${group.title}进度日志`} key={item.id}>
        <RobotAvatar />
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
              {reasoningCount > 0 ? (
                <span className="reasoningCount">含 {reasoningCount} 条思考摘要</span>
              ) : null}
            </div>
            <button
              aria-label={isLogCopied ? `已复制${group.title}日志` : `复制${group.title}日志`}
              className={logCopyButtonClassName}
              disabled={group.logs.length === 0}
              onClick={() => void onCopyLogs(group.logs, logCopyKey)}
              title={isLogCopied ? "已复制" : `复制${group.title}日志`}
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
              visibleLogs.map((log) => renderLogItem(log))
            )}
            {showReasoningToggle ? (
              <button
                className="logToggleButton"
                onClick={() => onToggleReasoningRun(group.runId)}
                type="button"
              >
                {reasoningExpanded
                  ? "收起思考摘要"
                  : `展开 ${hiddenReasoningCount} 条思考摘要`}
              </button>
            ) : null}
          </div>
        </article>
      </section>
    );
  }

  function renderLogItem(log: ExecutionLog) {
    const logClassName = [
      "logItem",
      `log-${log.level ?? "info"}`,
      log.agentActivity ? "logItem-activity" : "",
      log.reasoning ? "logItem-reasoning" : "",
      log.fileAudit ? "logItem-fileAudit" : "",
      log.searchTrace ? "logItem-search" : "",
      log.orchestration ? "logItem-orchestration" : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <article className={logClassName} key={log.id}>
        <time>{formatTime(log.createdAt)}</time>
        <span className="logLevel">
          {log.agentActivity
            ? "执行进展"
            : log.reasoning
              ? "思考摘要"
              : log.fileAudit
                ? "文件审计"
                : log.searchTrace
                  ? "搜索日志"
                  : log.orchestration
                    ? "编排策略"
                    : formatLogLevelLabel(log.level)}
        </span>
        <div>{renderLogBody(log)}</div>
      </article>
    );
  }

  function renderLogBody(log: ExecutionLog) {
    if (log.agentActivity) {
      return (
        <>
          <strong>
            {formatAgentActivityPhaseLabel(log.agentActivity.phase)}
            ·{formatAgentActivityStatusLabel(log.agentActivity.status)}
            ：{log.agentActivity.title}
          </strong>
          <p>{log.agentActivity.summary}</p>
          <div className="logMetaGrid">
            <span>{formatAgentActivityKindLabel(log.agentActivity.activityKind)}</span>
            {typeof log.agentActivity.iterationIndex === "number" ? (
              <span>轮次：{log.agentActivity.iterationIndex}</span>
            ) : null}
            {log.agentActivity.agentId ? <span>代理：{log.agentActivity.agentId}</span> : null}
            {log.agentActivity.parentAgentId ? (
              <span>父代理：{log.agentActivity.parentAgentId}</span>
            ) : null}
            {log.agentActivity.taskLabel ? <span>任务：{log.agentActivity.taskLabel}</span> : null}
            {log.agentActivity.toolName ? <span>工具：{log.agentActivity.toolName}</span> : null}
            {log.agentActivity.parameterSummary ? (
              <span>参数：{log.agentActivity.parameterSummary}</span>
            ) : null}
            {log.agentActivity.resultSummary ? (
              <span>结果：{log.agentActivity.resultSummary}</span>
            ) : null}
            {log.agentActivity.subgraphPath.length > 0 ? (
              <span>路径：{log.agentActivity.subgraphPath.join(" / ")}</span>
            ) : null}
            {log.agentActivity.relatedEventId ? (
              <span>关联：{log.agentActivity.relatedEventId}</span>
            ) : null}
            {log.agentActivity.truncated ? <span>已截断</span> : null}
          </div>
        </>
      );
    }

    if (log.reasoning) {
      return (
        <>
          <strong>
            {formatReasoningPhaseLabel(log.reasoning.phase)}：{log.reasoning.agentId}
          </strong>
          <p>{log.reasoning.summary}</p>
          {log.reasoning.evidenceRefs.length > 0 ? (
            <p className="reasoningRefs">关联：{log.reasoning.evidenceRefs.join("、")}</p>
          ) : null}
        </>
      );
    }

    if (log.fileAudit) {
      return (
        <>
          <strong>
            {formatFileAuditOperationLabel(log.fileAudit.operation)}
            ·{formatFileAuditStatusLabel(log.fileAudit.status)}
            ：{log.fileAudit.virtualPath}
          </strong>
          <div className="logMetaGrid">
            {log.fileAudit.toolName ? <span>工具：{log.fileAudit.toolName}</span> : null}
            {log.fileAudit.source ? <span>来源：{log.fileAudit.source}</span> : null}
            {typeof log.fileAudit.bytes === "number" ? (
              <span>字节：{log.fileAudit.bytes}</span>
            ) : null}
            {log.fileAudit.sha256 ? <span>SHA256：{log.fileAudit.sha256}</span> : null}
            {log.fileAudit.reason ? <span>原因：{log.fileAudit.reason}</span> : null}
            {log.fileAudit.promotedArtifactId ? (
              <span>产物：{log.fileAudit.promotedArtifactId}</span>
            ) : null}
            {log.fileAudit.partial ? <span>部分写入</span> : null}
          </div>
        </>
      );
    }

    if (log.searchTrace) {
      return (
        <>
          <strong>
            {formatSearchTraceKindLabel(log.searchTrace.kind)}：{log.title}
          </strong>
          {log.detail ? <p>{log.detail}</p> : null}
          <div className="logMetaGrid">
            {log.searchTrace.toolName ? <span>工具：{log.searchTrace.toolName}</span> : null}
            {log.searchTrace.parameterSummary ? (
              <span>参数：{log.searchTrace.parameterSummary}</span>
            ) : null}
            {log.searchTrace.resultSummary ? (
              <span>结果：{log.searchTrace.resultSummary}</span>
            ) : null}
            {typeof log.searchTrace.sourceCount === "number" ? (
              <span>来源数：{log.searchTrace.sourceCount}</span>
            ) : null}
            {typeof log.searchTrace.usedModel === "boolean" ? (
              <span>模型：{log.searchTrace.usedModel ? "已使用" : "未使用"}</span>
            ) : null}
            {log.searchTrace.warningCode ? <span>提醒：{log.searchTrace.warningCode}</span> : null}
          </div>
          {log.searchTrace.sources.length > 0 ? (
            <p className="reasoningRefs">
              来源：{log.searchTrace.sources.map((source) => source.title).join("、")}
            </p>
          ) : null}
        </>
      );
    }

    if (log.orchestration) {
      return (
        <>
          <strong>
            {log.orchestration.strategy === "multi_agent" ? "多 Agent" : "单 Agent"}：
            {log.orchestration.chosenProfileLabel ?? "默认编排"}
          </strong>
          {log.orchestration.decisionSummary ? <p>{log.orchestration.decisionSummary}</p> : null}
          <div className="logMetaGrid">
            {log.orchestration.chosenProfileId ? (
              <span>Profile：{log.orchestration.chosenProfileId}</span>
            ) : null}
            {log.orchestration.reasonCode ? <span>原因：{log.orchestration.reasonCode}</span> : null}
            {log.orchestration.messageClass ? (
              <span>消息类型：{log.orchestration.messageClass}</span>
            ) : null}
            {typeof log.orchestration.bidderCount === "number" ? (
              <span>投标人数：{log.orchestration.bidderCount}</span>
            ) : null}
            {log.orchestration.plannedSubagents.map((subagent) => (
              <span key={subagent}>子 Agent：{subagent}</span>
            ))}
          </div>
        </>
      );
    }

    return (
      <>
        <strong>{log.title}</strong>
        {log.detail ? <p>{log.detail}</p> : null}
      </>
    );
  }

  return (
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

              return renderRunItem(item);
            })}
            {noticeMessages.map((message) => renderChatMessage(message, `notice:${message.id}`))}
          </>
        )}
      </div>
    </section>
  );
}
