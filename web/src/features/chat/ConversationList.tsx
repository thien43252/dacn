import type { ConversationListItem } from "../../api-client/types";
import { mascotOf } from "../../components/chat/ChatThread";
import { Icon } from "../../components/Icon";
import { Mascot } from "../../components/Mascot";

interface Props {
  items: ConversationListItem[];
  loading: boolean;
  error: string | null;
  selectedKey: string | null;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (item: ConversationListItem) => void;
  onNewDirect: () => void;
  onNewGroup: () => void;
  canCreateGroup: boolean;
  /** Class names by id, to tell apart the same agent in different classes. */
  classNames: Record<string, string>;
}

function when(at: string | undefined): string {
  if (!at) return "";
  const date = new Date(at);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

/** One bubble per group and per agent (in each class or the personal space); its sessions live in the history. */
export function bubbleKey(item: ConversationListItem): string {
  return item.kind === "group" ? `group:${item.id}` : `direct:${item.class_id ?? ""}:${item.agent?.slug ?? ""}`;
}

interface Bubble {
  key: string;
  item: ConversationListItem;
  unread: number;
}

function bubblesOf(items: ConversationListItem[]): Bubble[] {
  const bubbles = new Map<string, Bubble>();
  for (const item of items) {
    const key = bubbleKey(item);
    const found = bubbles.get(key);
    const at = item.last_message?.at ?? item.updated_at;
    if (!found) bubbles.set(key, { key, item, unread: item.unread });
    else {
      found.unread += item.unread;
      if (at > (found.item.last_message?.at ?? found.item.updated_at)) found.item = item;
    }
  }
  return [...bubbles.values()];
}

/** The left column: newest first, unread counts, a search box and the two ways to start a chat. */
export function ConversationList({ items, loading, error, selectedKey, search, onSearch, onSelect, onNewDirect, onNewGroup, canCreateGroup, classNames }: Props) {
  const bubbles = bubblesOf(items);
  const nameOf = (item: ConversationListItem) => (item.kind === "direct" ? item.agent?.name || "Trợ lý" : item.title || "Nhóm");
  const seen = new Map<string, number>();
  for (const { item } of bubbles) seen.set(nameOf(item), (seen.get(nameOf(item)) ?? 0) + 1);
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
      <ul className="messenger__items">
        {bubbles.map(({ key, item, unread }) => {
          const name = nameOf(item);
          const scope = (seen.get(name) ?? 0) > 1 && item.kind === "direct"
            ? (item.class_id ? classNames[item.class_id] ?? "Lớp khác" : "Cá nhân") : null;
          const active = key === selectedKey;
          return (
            <li key={key}>
              <button type="button" className={`messenger__item${active ? " is-active" : ""}${unread ? " has-unread" : ""}`} onClick={() => onSelect(item)}
                aria-current={active ? "true" : undefined}>
                {item.kind === "direct"
                  ? <Mascot character={mascotOf(item.agent?.avatar ?? undefined)} mood="still" size={36} />
                  : <span className="messenger__group-avatar" aria-hidden="true"><Icon name="team" /></span>}
                <span className="messenger__item-body">
                  <span className="messenger__item-top">
                    <strong>{name}{scope && <span className="messenger__item-scope"> · {scope}</span>}</strong>
                    <small>{when(item.last_message?.at ?? item.updated_at)}</small>
                  </span>
                  <span className="messenger__item-preview">
                    {item.waiting_for.length > 0 ? <em>Đang chờ {item.waiting_for.join(", ")}</em>
                      : item.last_message ? `${item.last_message.sender ? `${item.last_message.sender}: ` : ""}${item.last_message.text}` : "Chưa có tin nhắn"}
                  </span>
                </span>
                {unread > 0 && <span className="messenger__badge" aria-label={`${unread} tin chưa đọc`}>{unread}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
