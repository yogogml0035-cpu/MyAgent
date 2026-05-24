"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Artifact, ChatMessage, ExecutionLog } from "../../app/task-state";
import { isTaskActive } from "../../app/task-state";
import {
  type ConversationStreamItem,
  type LiveLogItem,
  buildLiveLogItems,
  formatLiveLogItemTime,
  formatMessagePanelStatus,
  formatMessagePanelTitle,
  formatRunLogStatus,
  formatTime,
  getMessagePanelTone,
} from "../../app/workspace-view";
import { RobotAvatar } from "./RobotAvatar";
import { TypewriterText } from "./TypewriterText";

export const LOG_LIST_AUTO_SCROLL_THRESHOLD = 60;

type LogScrollElement = {
  clientHeight: number;
  scrollHeight: number;
  scrollTo: (options: ScrollToOptions) => void;
  scrollTop: number;
};

export function isLogListNearBottom(
  element: LogScrollElement,
  threshold = LOG_LIST_AUTO_SCROLL_THRESHOLD,
) {
  return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

export function scrollLogListToBottomIfPinned(
  element: LogScrollElement,
  pinnedToBottom: boolean | undefined,
) {
  if (pinnedToBottom === false && !isLogListNearBottom(element)) {
    return false;
  }
  element.scrollTo({ top: element.scrollHeight, behavior: "auto" });
  return true;
}

export function countOpenLogDetails(logLists: Iterable<HTMLElement>) {
  let count = 0;
  for (const logList of logLists) {
    count += logList.querySelectorAll("details[open]").length;
  }
  return count;
}

export function collapseOpenLogDetails(logLists: Iterable<HTMLElement>) {
  let collapsedCount = 0;
  for (const logList of logLists) {
    logList.querySelectorAll<HTMLDetailsElement>("details[open]").forEach((detail) => {
      detail.open = false;
      collapsedCount += 1;
    });
  }
  return collapsedCount;
}

export function setLogDetailsOpen(logList: HTMLElement, open: boolean) {
  const selector = open ? "details:not([open])" : "details[open]";
  let changedCount = 0;
  logList.querySelectorAll<HTMLDetailsElement>(selector).forEach((detail) => {
    detail.open = open;
    changedCount += 1;
  });
  return changedCount;
}

type TaskConversationProps = {
  activeTask: boolean;
  conversationStreamItems: ConversationStreamItem[];
  copiedCopyKey: string;
  hasConversation: boolean;
  noticeMessages: ChatMessage[];
  onCopyText: (text: string, failureMessage?: string, copyKey?: string) => Promise<void>;
  onDownloadLogs: (logs: ExecutionLog[], runId: string, groupTitle: string) => Promise<void>;
  onDownloadArtifact: (artifact: Artifact) => Promise<void>;
  onOpenArtifact: (artifact: Artifact) => Promise<void>;
};

export function TaskConversation({
  activeTask,
  conversationStreamItems,
  copiedCopyKey,
  hasConversation,
  noticeMessages,
  onCopyText,
  onDownloadLogs,
  onDownloadArtifact,
  onOpenArtifact,
}: TaskConversationProps) {
  const conversationCanvasRef = useRef<HTMLElement | null>(null);
  const logListRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const logListPinnedRefs = useRef<Map<string, boolean>>(new Map());
  const [openLogDetailCounts, setOpenLogDetailCounts] = useState<Record<string, number>>({});

  const syncOpenLogDetailCounts = useCallback(() => {
    const counts: Record<string, number> = {};
    logListRefs.current.forEach((logList, runId) => {
      counts[runId] = countOpenLogDetails([logList]);
    });
    setOpenLogDetailCounts(counts);
  }, []);

  const toggleRunLogDetails = useCallback((runId: string, open: boolean) => {
    const logList = logListRefs.current.get(runId);
    if (!logList) {
      return;
    }
    setLogDetailsOpen(logList, open);
    if (open) {
      logListPinnedRefs.current.set(runId, false);
    }
    syncOpenLogDetailCounts();
  }, [syncOpenLogDetailCounts]);

  useEffect(() => {
    if (!hasConversation) {
      return;
    }
    const canvas = conversationCanvasRef.current;
    if (!canvas) {
      return;
    }
    const threshold = 120;
    const distanceFromBottom = canvas.scrollHeight - canvas.scrollTop - canvas.clientHeight;
    if (distanceFromBottom < threshold) {
      canvas.scrollTo({ top: canvas.scrollHeight, behavior: "smooth" });
    }
  }, [conversationStreamItems, hasConversation, noticeMessages]);

  useLayoutEffect(() => {
    const scrollPinnedLists = () => {
      logListRefs.current.forEach((el, runId) => {
        if (!el) return;
        scrollLogListToBottomIfPinned(el, logListPinnedRefs.current.get(runId));
      });
    };

    scrollPinnedLists();
    const animationFrameId = window.requestAnimationFrame(scrollPinnedLists);
    syncOpenLogDetailCounts();
    return () => {
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [conversationStreamItems, syncOpenLogDetailCounts]);

  useEffect(() => {
    logListRefs.current.forEach((el, runId) => {
      if (!el) return;
      scrollLogListToBottomIfPinned(el, logListPinnedRefs.current.get(runId));
    });
  }, [noticeMessages]);

  function artifactCanOpen(artifact: Artifact) {
    const artifactKind = artifact.kind ?? (artifact.name.toLowerCase().endsWith(".html") ? "html" : "file");
    return artifactKind === "html" || artifact.name.toLowerCase().endsWith(".html");
  }

  function renderChatMessage(
    message: ChatMessage,
    key: string,
    assistantArtifacts: Artifact[] = [],
    groupTitle?: string,
  ) {
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
            <div className="messageCardBody markdownBody">
              {message.streaming && activeTask ? (
                <TypewriterText text={message.content} />
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              )}
              {message.streaming && activeTask ? (
                <span className="answerStreamCursor" aria-hidden="true" />
              ) : null}
            </div>
          ) : null}

          {tone === "default" && assistantArtifacts.length > 0 ? (
            <footer className="messageArtifactFooter" aria-label="AI回复产物">
              <div className="messageArtifactFooterTitle">
                <span className="downloadStatusIcon" aria-hidden="true" />
                <strong>产物</strong>
                {groupTitle ? <span className="runRoundLabel">{groupTitle}</span> : null}
              </div>
              <div className="messageArtifactList">
                {assistantArtifacts.map((artifact) => (
                  <div className="messageArtifactItem" key={`${artifact.runId ?? "run"}:${artifact.name}`}>
                    <span className="downloadFileIcon" aria-hidden="true" />
                    <span className="downloadFileName">{artifact.name}</span>
                    <div className="messageArtifactActions">
                      {artifactCanOpen(artifact) ? (
                        <button
                          aria-label={`打开 ${artifact.name}`}
                          className="downloadSecondaryButton"
                          onClick={() => void onOpenArtifact(artifact)}
                          type="button"
                        >
                          打开
                        </button>
                      ) : null}
                      <button
                        aria-label={`下载 ${artifact.name}`}
                        className="downloadPrimaryButton"
                        onClick={() => void onDownloadArtifact(artifact)}
                        type="button"
                      >
                        下载
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </footer>
          ) : null}

          {message.createdAt ? (
            <time className="messageCardTime">{formatTime(message.createdAt, "short")}</time>
          ) : null}
        </article>
      </section>
    );
  }

  function renderArtifactMessage(groupTitle: string, artifact: Artifact, key: string) {
    const canOpen = artifactCanOpen(artifact);

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
                  aria-label={`打开 ${artifact.name}`}
                  className="downloadSecondaryButton"
                  onClick={() => void onOpenArtifact(artifact)}
                  type="button"
                >
                  打开报告
                </button>
              ) : null}
              <button
                aria-label={`下载 ${artifact.name}`}
                className="downloadPrimaryButton"
                onClick={() => void onDownloadArtifact(artifact)}
                type="button"
              >
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
    const groupLogStatusText = formatRunLogStatus(group.status);
    const liveItems = buildLiveLogItems(group.logs, group.status);
    const openLogDetailCount = openLogDetailCounts[group.runId] ?? 0;
    const totalLogDetailCount = liveItems.length;
    const hasOpenLogDetails = openLogDetailCount > 0;
    const toggleLogDetailsLabel = hasOpenLogDetails ? "全部折叠" : "全部展开";
    const toggleLogDetailsTitle = hasOpenLogDetails
      ? `折叠${group.title}全部日志`
      : `展开${group.title}全部日志`;
    const logToggleButtonClassName = [
      "traceLogToggleButton",
      hasOpenLogDetails ? "traceLogToggleButton-open" : "",
    ]
      .filter(Boolean)
      .join(" ");

    const logListId = `logList:${group.runId}`;

    return (
      <section className="traceRow" aria-label={`${group.title}进度日志`} key={item.id}>
        <RobotAvatar />
        <article className={`traceCard traceCard-${group.status}`}>
          <header className="traceHeader">
            <div className="traceTitle">
              <strong>进度日志</strong>
              <span className="runRoundLabel">{group.title}</span>
              <span
                className={groupActive ? "spinner" : `statusGlyph statusGlyph-${group.status}`}
                aria-hidden="true"
              />
              <span>{groupLogStatusText}</span>
            </div>
            <div className="traceActions" aria-label={`${group.title}日志操作`}>
              <button
                aria-label={`下载${group.title}完整日志`}
                className="downloadSecondaryButton"
                disabled={group.logs.length === 0}
                onClick={() => void onDownloadLogs(group.logs, group.runId, group.title)}
                title={group.logs.length > 0 ? `下载${group.title}完整日志（JSONL）` : "暂无日志可下载"}
                type="button"
              >
                下载完整日志
              </button>
              <button
                aria-expanded={hasOpenLogDetails}
                aria-label={toggleLogDetailsTitle}
                className={logToggleButtonClassName}
                disabled={totalLogDetailCount === 0}
                onClick={() => toggleRunLogDetails(group.runId, !hasOpenLogDetails)}
                title={toggleLogDetailsTitle}
                type="button"
              >
                <span>{toggleLogDetailsLabel}</span>
              </button>
            </div>
          </header>

          <div
            className="logList"
            id={logListId}
            ref={(el) => {
              if (el) {
                logListRefs.current.set(group.runId, el);
                if (!logListPinnedRefs.current.has(group.runId)) {
                  logListPinnedRefs.current.set(group.runId, true);
                }
              } else {
                logListRefs.current.delete(group.runId);
                logListPinnedRefs.current.delete(group.runId);
              }
            }}
            onScroll={(event) => {
              logListPinnedRefs.current.set(
                group.runId,
                isLogListNearBottom(event.currentTarget),
              );
            }}
          >
            {liveItems.length === 0 ? (
              <p className="emptyLog">任务直播会显示在这里。</p>
            ) : (
              liveItems.map((liveItem) => renderLiveLogItem(liveItem))
            )}
          </div>
        </article>
      </section>
    );
  }

  function renderLiveLogItem(item: LiveLogItem) {
    const copyKey = `log-detail:${item.id}`;
    if (item.kind === "tool") {
      const toolSummaryLine = formatToolSummaryLine(item);
      const toolClassName = [
        "liveToolCard",
        item.resultStatus ? `liveToolCard-${item.resultStatus}` : "",
      ]
        .filter(Boolean)
        .join(" ");
      return (
        <details className={toolClassName} key={item.id} onToggle={syncOpenLogDetailCounts}>
          <summary>
            <time>{formatLiveLogItemTime(item)}</time>
            <strong className="liveToolSummaryText" title={toolSummaryLine}>
              {toolSummaryLine}
            </strong>
            {renderLiveLogCopyButton(item.details, copyKey)}
          </summary>
          {renderLiveLogDiagnostics(item.details)}
        </details>
      );
    }

    const statusClassName = [
      "liveStatusRow",
      item.active ? "liveStatusRow-active" : "",
      item.level ? `liveStatusRow-${item.level}` : "",
    ]
      .filter(Boolean)
      .join(" ");
    const statusSummary = (
      <>
        <time>{formatTime(item.createdAt)}</time>
        <span>{item.text}</span>
        {item.active ? (
          <span className="thinkingDots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        ) : null}
        {renderLiveLogCopyButton(item.details, copyKey)}
      </>
    );
    return (
      <details
        className={`${statusClassName} liveStatusRow-details`}
        key={item.id}
        onToggle={syncOpenLogDetailCounts}
      >
        <summary>{statusSummary}</summary>
        {renderLiveLogDiagnostics(item.details)}
      </details>
    );
  }

  function renderLiveLogCopyButton(
    details: NonNullable<LiveLogItem["details"]>,
    copyKey: string,
  ) {
    const isCopied = copiedCopyKey === copyKey;
    const copyButtonClassName = [
      "copyButton",
      "liveLogCopyButton",
      isCopied ? "copyButton-copied" : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <button
        aria-label={isCopied ? "已复制此行日志JSON" : "复制此行日志JSON"}
        className={copyButtonClassName}
        disabled={!details.displayJson}
        onClick={(event: MouseEvent<HTMLButtonElement>) => {
          event.preventDefault();
          event.stopPropagation();
          void onCopyText(details.displayJson, "复制此行日志失败，请检查浏览器权限。", copyKey);
        }}
        title={isCopied ? "已复制" : "复制此行日志JSON"}
        type="button"
      >
        <span aria-hidden="true" />
      </button>
    );
  }

  function renderLiveLogDiagnostics(details: NonNullable<LiveLogItem["details"]>) {
    return (
      <div className="liveLogDiagnostics">
        <pre>{details.displayJson}</pre>
      </div>
    );
  }

  function formatToolSummaryLine(item: Extract<LiveLogItem, { kind: "tool" }>) {
    return item.title;
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
                return renderChatMessage(
                  item.message,
                  item.id,
                  item.assistantArtifacts,
                  item.groupTitle,
                );
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
