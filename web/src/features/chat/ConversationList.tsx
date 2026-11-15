import type { ConversationListItem } from "../../api-client/types";
import { mascotOf } from "../../components/chat/ChatThread";
import { Icon } from "../../components/Icon";
import { Mascot } from "../../components/Mascot";

interface Props {
  items: ConversationListItem[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (item: ConversationListItem) => void;
  onNewDirect: () => void;
  onNewGroup: () => void;
  canCreateGroup: boolean;
}

function when(at: string | undefined): string {
  if (!at) return "";
  const date = new Date(at);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

/** The left column: newest first, unread counts, a search box and the two ways to start a chat. */
export function ConversationList({ items, loading, error, selectedId, search, onSearch, onSelect, onNewDirect, onNewGroup, canCreateGroup }: Props) {
  return (
    <aside className="messenger__list" aria-label="Danh sách cuộc trò chuyện">
      <div className="messenger__list-head">
        <strong>Tin nhắn</strong>
        <div>
          <button className="icon-button" type="button" onClick={onNewDirect} aria-label="Chat với agent" title="Chat với agent"><Icon name="sparkles" /></button>
          <button className="icon-button" type="button" onClick={onNewGroup} disabled={!canCreateGroup} aria-label="Tạo nhóm" title={canCreateGroup ? "Tạo nhóm" : "Cần tham gia một lớp để tạo nhóm"}><Icon name="team" /></button>
        </div>
      </div>
      <label className="visually-hidden" htmlFor="messenger-search">Tìm cuộc trò chuyện</label>
      <input id="messenger-search" className="messenger__search" type="search" placeholder="Tìm theo tên agent hoặc nhóm" value={search} onChange={(event) => onSearch(event.target.value)} />
      {error && <p className="form-error" role="alert">{error}</p>}
      {loading && items.length === 0 && <p className="ea-muted">Đang tải…</p>}
      {!loading && items.length === 0 && <p className="ea-muted">Chưa có cuộc trò chuyện nào.</p>}
      <ul>
        {items.map((item) => {
          // Auto-routed chats (from before feature 003) keep their own title; a chat with one agent shows the agent.
          const name = item.kind === "direct" && item.agent?.slug ? item.agent.name : item.title || item.agent?.name || "Trợ lý";
          return (
            <li key={item.id}>
              <button type="button" className={`messenger__item${item.id === selectedId ? " is-active" : ""}${item.unread ? " has-unread" : ""}`} onClick={() => onSelect(item)}
                aria-current={item.id === selectedId ? "true" : undefined}>
                {item.kind === "direct"
                  ? <Mascot character={mascotOf(item.agent?.avatar ?? undefined)} mood="still" size={36} />
                  : <span className="messenger__group-avatar" aria-hidden="true"><Icon name="team" /></span>}
                <span className="messenger__item-body">
                  <span className="messenger__item-top">
                    <strong>{name}</strong>
                    <small>{when(item.last_message?.at ?? item.updated_at)}</small>
                  </span>
                  <span className="messenger__item-preview">
                    {item.waiting_for.length > 0 ? <em>Đang chờ {item.waiting_for.join(", ")}</em>
                      : item.last_message ? `${item.last_message.sender ? `${item.last_message.sender}: ` : ""}${item.last_message.text}` : "Chưa có tin nhắn"}
                  </span>
                </span>
                {item.unread > 0 && <span className="messenger__badge" aria-label={`${item.unread} tin chưa đọc`}>{item.unread}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
