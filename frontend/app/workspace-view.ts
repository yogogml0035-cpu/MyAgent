import type { ChatMessage, ExecutionLog, TaskStatus } from "./task-state";

export type TimeVariant = "default" | "short";

export type ConversationHistoryItem = {
  id: string;
  title: string;
  subtitle: string;
  active: boolean;
};

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
        return `${time} ${(log.level ?? "info").toUpperCase()} ${log.title}${detail}`;
      })
      .join("\n") || "暂无日志"
  );
}

function compactTitle(value: string) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "新对话";
  }
  return normalized.length > 24 ? `${normalized.slice(0, 24)}...` : normalized;
}

export function buildConversationHistoryItems(
  messages: ChatMessage[],
  taskId: string,
  status: TaskStatus,
): ConversationHistoryItem[] {
  const userMessages = messages.filter((message) => message.role === "user" && message.content.trim());

  if (userMessages.length === 0) {
    return [
      {
        id: taskId || "draft",
        title: taskId ? `任务 ${taskId}` : "新对话",
        subtitle: taskId ? status : "等待开始",
        active: true,
      },
    ];
  }

  return userMessages
    .slice(-6)
    .reverse()
    .map((message, index) => ({
      id: message.id,
      title: compactTitle(message.content),
      subtitle: index === 0 ? status : formatTime(message.createdAt, "short") || "历史消息",
      active: index === 0,
    }));
}
