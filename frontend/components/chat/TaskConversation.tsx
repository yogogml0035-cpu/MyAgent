"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Artifact, ChatMessage, ExecutionLog } from "../../app/task-state";
import { isTaskActive } from "../../app/task-state";
import {
  type ConversationStreamItem,
  type LiveLogItem,
  buildLiveLogItems,
  formatMessagePanelStatus,
  formatMessagePanelTitle,
  formatRunLogStatus,
  formatTime,
  getMessagePanelTone,
} from "../../app/workspace-view";
import { RobotAvatar } from "./RobotAvatar";

type TaskConversationProps = {
  conversationStreamItems: ConversationStreamItem[];
  copiedCopyKey: string;
  hasConversation: boolean;
  noticeMessages: ChatMessage[];
  onCopyLogs: (logs: ExecutionLog[], copyKey?: string) => Promise<void>;
  onCopyText: (text: string, failureMessage?: string, copyKey?: string) => Promise<void>;
  onDownloadArtifact: (artifact: Artifact) => Promise<void>;
  onOpenArtifact: (artifact: Artifact) => Promise<void>;
};

export function TaskConversation({
  conversationStreamItems,
  copiedCopyKey,
  hasConversation,
  noticeMessages,
  onCopyLogs,
  onCopyText,
  onDownloadArtifact,
  onOpenArtifact,
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
            <div className="messageCardBody markdownBody">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
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
                          className="downloadSecondaryButton"
                          onClick={() => void onOpenArtifact(artifact)}
                          type="button"
                        >
                          打开
                        </button>
                      ) : null}
                      <button
                        className="downloadPrimaryButton"
                        onClick={() => void onDownloadArtifact(artifact)}
                        type="button"
                      >
                        <span className="downloadButtonIcon" aria-hidden="true" />
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
    const groupLogStatusText = formatRunLogStatus(group.status);
    const liveItems = buildLiveLogItems(group.logs, group.status);
    const logCopyKey = `logs:${group.runId}`;
    const isLogCopied = copiedCopyKey === logCopyKey;
    const logCopyButtonClassName = [
      "copyButton",
      isLogCopied ? "copyButton-copied" : "",
    ]
      .filter(Boolean)
      .join(" ");
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

          <div className="logList">
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
    if (item.kind === "tool") {
      const toolClassName = [
        "liveToolCard",
        item.resultStatus ? `liveToolCard-${item.resultStatus}` : "",
      ]
        .filter(Boolean)
        .join(" ");
      return (
        <details className={toolClassName} key={item.id}>
          <summary>
            <span className="liveToolIcon" aria-hidden="true" />
            <strong>{item.title}</strong>
            <time>{formatTime(item.createdAt)}</time>
          </summary>
          <p>{item.resultText}</p>
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
    return (
      <article className={statusClassName} key={item.id}>
        <time>{formatTime(item.createdAt)}</time>
        <span>{item.text}</span>
        {item.active ? (
          <span className="thinkingDots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        ) : null}
      </article>
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
