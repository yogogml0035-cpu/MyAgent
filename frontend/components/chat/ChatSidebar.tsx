import type { ConversationHistoryItem } from "../../app/workspace-view";

type ChatSidebarProps = {
  historyItems: ConversationHistoryItem[];
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
};

export function ChatSidebar({
  historyItems,
  onNewConversation,
  onSelectConversation,
}: ChatSidebarProps) {
  return (
    <aside className="chatSidebar" aria-label="历史会话">
      <button className="newChatButton" onClick={onNewConversation} type="button">
        <span aria-hidden="true" />
        新建会话
      </button>

      <nav className="historyPanel" aria-label="聊天历史">
        <p>聊天历史</p>
        <div className="historyList">
          {historyItems.map((item) => (
            <button
              aria-current={item.active ? "page" : undefined}
              className={item.active ? "historyItem historyItem-active" : "historyItem"}
              key={item.id}
              onClick={() => void onSelectConversation(item.id)}
              type="button"
            >
              <strong>{item.title}</strong>
            </button>
          ))}
        </div>
      </nav>
    </aside>
  );
}
