import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import type { ConversationHistoryItem } from "../../app/workspace-view";

type ChatSidebarProps = {
  historyItems: ConversationHistoryItem[];
  isHistoryBusy: boolean;
  onClearConversations: () => Promise<void> | void;
  onDeleteConversation: (id: string) => Promise<void> | void;
  onNewConversation: () => void;
  onRenameConversation: (id: string, title: string) => Promise<void> | void;
  onSelectConversation: (id: string) => void;
};

export function ChatSidebar({
  historyItems,
  isHistoryBusy,
  onClearConversations,
  onDeleteConversation,
  onNewConversation,
  onRenameConversation,
  onSelectConversation,
}: ChatSidebarProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [openMenuId, setOpenMenuId] = useState("");
  const [renamingId, setRenamingId] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [actionBusyId, setActionBusyId] = useState("");

  useEffect(() => {
    if (!openMenuId) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (menuRef.current?.contains(event.target as Node)) {
        return;
      }
      setOpenMenuId("");
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenMenuId("");
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openMenuId]);

  async function handleRenameSubmit(event: FormEvent<HTMLFormElement>, id: string) {
    event.preventDefault();
    const nextTitle = renameValue.trim();
    if (!nextTitle) {
      return;
    }
    setActionBusyId(id);
    try {
      await onRenameConversation(id, nextTitle);
      setRenamingId("");
      setRenameValue("");
    } finally {
      setActionBusyId("");
    }
  }

  function handleRenameKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setRenamingId("");
      setRenameValue("");
    }
  }

  async function handleDelete(id: string) {
    setOpenMenuId("");
    if (!window.confirm("删除会话后无法恢复，确定删除吗？")) {
      return;
    }
    setActionBusyId(id);
    try {
      await onDeleteConversation(id);
    } finally {
      setActionBusyId("");
    }
  }

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
            <div
              className={item.active ? "historyItemShell historyItemShell-active" : "historyItemShell"}
              key={item.id}
              ref={openMenuId === item.id ? menuRef : undefined}
            >
              {renamingId === item.id ? (
                <form
                  className="historyRenameForm"
                  onSubmit={(event) => void handleRenameSubmit(event, item.id)}
                >
                  <input
                    aria-label="重命名会话"
                    autoFocus
                    maxLength={80}
                    onChange={(event) => setRenameValue(event.target.value)}
                    onKeyDown={handleRenameKeyDown}
                    value={renameValue}
                  />
                  <button disabled={isHistoryBusy || actionBusyId === item.id} type="submit">
                    保存
                  </button>
                  <button
                    onClick={() => {
                      setRenamingId("");
                      setRenameValue("");
                    }}
                    type="button"
                  >
                    取消
                  </button>
                </form>
              ) : (
                <>
                  <button
                    aria-current={item.active ? "page" : undefined}
                    className="historyItem"
                    disabled={isHistoryBusy && actionBusyId !== item.id}
                    onClick={() => void onSelectConversation(item.id)}
                    type="button"
                  >
                    <strong>{item.title}</strong>
                  </button>
                  <button
                    aria-expanded={openMenuId === item.id}
                    aria-haspopup="menu"
                    aria-label={`打开 ${item.title} 的会话菜单`}
                    className="historyMenuButton"
                    disabled={isHistoryBusy && actionBusyId !== item.id}
                    onClick={() => setOpenMenuId((current) => (current === item.id ? "" : item.id))}
                    type="button"
                  >
                    <span aria-hidden="true">•••</span>
                  </button>
                  {openMenuId === item.id ? (
                    <div className="historyActionMenu" role="menu">
                      <button
                        className="historyMenuItem"
                        onClick={() => {
                          setOpenMenuId("");
                          setRenamingId(item.id);
                          setRenameValue(item.title);
                        }}
                        role="menuitem"
                        type="button"
                      >
                        <span aria-hidden="true" className="historyActionIcon historyActionIcon-rename" />
                        重命名
                      </button>
                      <button
                        className="historyMenuItem historyMenuItem-danger"
                        onClick={() => void handleDelete(item.id)}
                        role="menuitem"
                        type="button"
                      >
                        <span aria-hidden="true" className="historyActionIcon historyActionIcon-delete" />
                        删除
                      </button>
                    </div>
                  ) : null}
                </>
              )}
            </div>
          ))}
        </div>
        <div className="historyFooter">
          <button
            className="clearHistoryButton"
            disabled={isHistoryBusy || historyItems.length === 0}
            onClick={() => void onClearConversations()}
            type="button"
          >
            清空所有会话
          </button>
        </div>
      </nav>
    </aside>
  );
}
