import { useEffect, useRef, useState } from "react";

import { Icon } from "../Icon";
import { sessionGroup, sessionTime, type StoredSession } from "./chatHistory";

interface ChatHistoryDrawerProps<M> {
  sessions: Array<StoredSession<M> & { transient?: boolean }>;
  activeId: string;
  /** Sessions whose turn is still running; they cannot be deleted until it ends. */
  busyIds: Set<string>;
  onOpen: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
  error?: string;
}

/**
 * The reader's earlier chats in this browser, newest first and grouped by day. Opening one shows its transcript;
 * deleting asks once, then removes it here and closes the conversation on the server. Plans, reviews and
 * submissions are never touched by either.
 */
export function ChatHistoryDrawer<M>({ sessions, activeId, busyIds, onOpen, onNew, onDelete, onClose, error }: ChatHistoryDrawerProps<M>) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const drawerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    drawerRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { window.setTimeout(() => { if (previous?.isConnected) previous.focus(); }, 0); };
  }, []);
  const groups: { label: string; items: Array<StoredSession<M> & { transient?: boolean }> }[] = [];
  for (const session of sessions) {
    const label = sessionGroup(session.updatedAt);
    const group = groups.find((item) => item.label === label);
    if (group) group.items.push(session);
    else groups.push({ label, items: [session] });
  }
  return (
    <section ref={drawerRef} className="chat-history" role="dialog" aria-modal="true" aria-label="Lịch sử trò chuyện" onKeyDown={(event) => {
      if (event.key !== "Tab") return;
      const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
      const first = buttons[0], last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      event.stopPropagation();
    }}>
      <header className="chat-history__head">
        <strong>Lịch sử trò chuyện</strong>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng lịch sử">
          <Icon name="x" />
        </button>
      </header>
      <p className="chat-history__scope">Lưu trên trình duyệt này, theo tài khoản đang đăng nhập.</p>
      <button className="chat-history__new" type="button" onClick={onNew}>
        <Icon name="plus" /> Cuộc trò chuyện mới
      </button>
      {error && <p className="chat-history__error" role="alert">{error}</p>}
      {sessions.length === 0 ? (
        <p className="chat-history__empty">Chưa có cuộc trò chuyện nào được lưu trên trình duyệt này.</p>
      ) : (
        <div className="chat-history__list">
          {groups.map((group) => (
            <div key={group.label}>
              <h4>{group.label}</h4>
              <ul>
                {group.items.map((session) => (
                  <li key={session.id} className={session.id === activeId ? "is-active" : ""}>
                    {confirming === session.id ? (
                      <div className="chat-history__confirm" role="alertdialog" aria-label="Xóa cuộc trò chuyện">
                        <span>Xóa cuộc trò chuyện này? Kế hoạch và đánh giá vẫn giữ nguyên.</span>
                        <button type="button" className="is-danger" onClick={() => { setConfirming(null); onDelete(session.id); }}>Xóa</button>
                        <button type="button" onClick={() => setConfirming(null)} autoFocus>Hủy</button>
                      </div>
                    ) : (
                      <>
                        <button type="button" className="chat-history__open" onClick={() => onOpen(session.id)} aria-current={session.id === activeId ? "true" : undefined}>
                          <Icon name="message" />
                          <span>
                            <strong>{session.title}</strong>
                            <small>{session.transient ? session.messages.length ? "Trong tab này" : "Chưa gửi · Giữ trong tab này" : `${sessionTime(session.updatedAt)} · ${session.messages.length} tin nhắn`}</small>
                            {busyIds.has(session.id) && <small>Đang trả lời</small>}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="chat-history__delete"
                          onClick={() => setConfirming(session.id)}
                          disabled={busyIds.has(session.id)}
                          aria-label={`Xóa “${session.title}”`}
                          title={busyIds.has(session.id) ? "Đang trả lời, chờ xong rồi xóa" : "Xóa cuộc trò chuyện"}
                        >
                          <Icon name="trash" />
                        </button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
