import { useCallback, useEffect, useMemo, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { chatApi } from "../../api-client/agents";
import { conversationsApi } from "../../api-client/chat";
import { classesApi } from "../../api-client/classes";
import type { ChatAgent, ConversationListItem } from "../../api-client/types";
import { useAuth } from "../../auth/AuthContext";
import { ChatThread, fromStored, NO_MESSAGES, type ThreadMessage } from "../../components/chat/ChatThread";
import { Icon } from "../../components/Icon";
import { ConversationList } from "./ConversationList";
import { DirectChatDialog } from "./DirectChatDialog";
import { GroupSettingsPanel } from "./GroupSettingsPanel";
import { NewGroupDialog } from "./NewGroupDialog";
import "./messenger.css";

const SELECTED_KEY = "eduagent.messenger.selected";

function readSelected(userId: string): string | null {
  try {
    return localStorage.getItem(`${SELECTED_KEY}:${userId}`);
  } catch {
    return null;
  }
}

function storeSelected(userId: string, id: string) {
  try {
    localStorage.setItem(`${SELECTED_KEY}:${userId}`, id);
  } catch {
    // Remembering the open chat is a convenience only.
  }
}

/** Messenger-style chat (FR-049): direct chats with each agent and groups on the left, the open one on the right. */
export function ChatHomePage() {
  const { user } = useAuth();
  const userId = user?.id ?? "";
  const [search, setSearch] = useState("");
  const list = useResource(() => conversationsApi.all(search), [search]);
  const classes = useResource(() => classesApi.list(), [userId]);
  const [selectedId, setSelectedId] = useState<string | null>(() => readSelected(userId));
  const [dialog, setDialog] = useState<"direct" | "group" | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [initial, setInitial] = useState<ThreadMessage[]>(NO_MESSAGES);
  const [agents, setAgents] = useState<ChatAgent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [threadKey, setThreadKey] = useState(0);

  const selected = useMemo(
    () => list.data?.find((item) => item.id === selectedId) ?? null,
    [list.data, selectedId],
  );

  // Refresh the list (unread counts, last messages) while the page is open.
  useEffect(() => {
    const timer = setInterval(() => list.reload(), 15000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const open = useCallback(async (conversation: ConversationListItem) => {
    setSelectedId(conversation.id);
    storeSelected(userId, conversation.id);
    setSettingsOpen(false);
    setError(null);
    try {
      const [usable, stored] = await Promise.all([chatApi.agents(conversation.class_id), conversationsApi.messages(conversation.id)]);
      setAgents(usable);
      setInitial(fromStored(stored, usable, conversation.kind));
      setThreadKey((value) => value + 1);
      const last = stored[stored.length - 1]?.seq;
      if (last) void conversationsApi.markRead(conversation.id, last).catch(() => {});
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }, [userId]);

  // Open the remembered chat once the list arrives.
  useEffect(() => {
    if (selected && threadKey === 0) void open(selected);
  }, [selected, threadKey, open]);

  function created(conversation: ConversationListItem) {
    setDialog(null);
    list.reload();
    void open(conversation);
  }

  const groupAgents = useMemo(() => {
    if (!selected || selected.kind !== "group") return agents;
    const inGroup = new Set(selected.members_preview.filter((member) => member.kind === "agent").map((member) => member.id));
    return inGroup.size ? agents.filter((agent) => inGroup.has(agent.slug)) : agents;
  }, [agents, selected]);
  const requestFields = useMemo(() => ({ class_id: selected?.class_id ?? null }), [selected?.class_id]);
  const room = classes.data?.find((item) => item.id === selected?.class_id);

  if (!user) return null;
  return (
    <div className="messenger" data-testid="messenger">
      <ConversationList
        items={list.data ?? []}
        loading={list.loading}
        error={list.error}
        selectedId={selectedId}
        search={search}
        onSearch={setSearch}
        onSelect={(item) => void open(item)}
        onNewDirect={() => setDialog("direct")}
        onNewGroup={() => setDialog("group")}
        canCreateGroup={(classes.data ?? []).some((item) => !item.archived)}
      />
      <section className="messenger__thread" aria-label="Cuộc trò chuyện">
        {!selected ? (
          <div className="messenger__empty">
            <Icon name="sparkles" />
            <p>Chọn một cuộc trò chuyện, chat riêng với một agent hoặc tạo nhóm với bạn bè, thầy cô.</p>
            <div className="messenger__empty-actions">
              <button className="button button--primary" type="button" onClick={() => setDialog("direct")}>Chat với agent</button>
              <button className="button" type="button" onClick={() => setDialog("group")}>Tạo nhóm</button>
            </div>
          </div>
        ) : (
          <div className="chat-panel__inner messenger__inner">
            <header className="chat-panel__header messenger__header">
              <div>
                <strong>{selected.kind === "direct" && selected.agent?.slug ? selected.agent.name : selected.title || "Trợ lý"}</strong>
                <span>
                  {selected.kind === "group"
                    ? `Nhóm · ${selected.member_count ?? selected.members_preview.length} thành viên${room ? ` · ${room.name}` : ""}`
                    : `Chat riêng${room ? ` · ${room.name}` : " · không thuộc lớp"} · chỉ bạn xem được`}
                </span>
                {selected.waiting_for.length > 0 && <small className="ea-waiting">Đang chờ {selected.waiting_for.join(", ")} trả lời</small>}
              </div>
              {selected.kind === "direct" && (
                <button className="icon-button" type="button" title="Bắt đầu cuộc trò chuyện mới với agent này" aria-label="Cuộc trò chuyện mới"
                  onClick={async () => { const fresh = await conversationsApi.restartDirect(selected.id); list.reload(); void open(fresh); }}>
                  <Icon name="plus" />
                </button>
              )}
              {selected.kind === "group" && (
                <button className={`icon-button${settingsOpen ? " is-active" : ""}`} type="button" aria-label="Thành viên nhóm" aria-expanded={settingsOpen}
                  onClick={() => setSettingsOpen((value) => !value)}>
                  <Icon name="team" />
                </button>
              )}
            </header>
            {settingsOpen && selected.kind === "group" && (
              <GroupSettingsPanel group={selected} viewerId={user.id} onChanged={() => list.reload()} onLeft={() => { setSelectedId(null); list.reload(); }} />
            )}
            {error && <p className="chat-control-note" role="alert">{error}</p>}
            <ChatThread
              key={`${selected.id}:${threadKey}`}
              requestFields={requestFields}
              agents={groupAgents}
              conversationId={selected.id}
              initialMessages={initial}
              onConversation={() => list.reload()}
              viewerId={user.id}
              kind={selected.kind}
              emptyHint={selected.kind === "group"
                ? "Nhắn cho cả nhóm. Gõ @ để gọi một agent; tin trò chuyện giữa mọi người không làm agent lên tiếng."
                : "Hỏi bài, ôn tập hoặc nhờ việc. Nếu cần, agent sẽ hỏi agent khác hoặc xin ý kiến thầy cô, phụ huynh."}
              composerPlaceholder={selected.kind === "group" ? "Nhắn cho nhóm, hoặc gõ @ để gọi một agent…" : undefined}
            />
          </div>
        )}
      </section>
      {dialog === "direct" && <DirectChatDialog classes={classes.data ?? []} onClose={() => setDialog(null)} onOpened={created} />}
      {dialog === "group" && <NewGroupDialog classes={classes.data ?? []} onClose={() => setDialog(null)} onCreated={created} />}
    </div>
  );
}
