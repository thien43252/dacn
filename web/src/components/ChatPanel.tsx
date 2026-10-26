import { useCallback, useEffect, useMemo, useState } from "react";

import { useResource } from "../app/useResource";
import { chatApi } from "../api-client/agents";
import { classesApi } from "../api-client/classes";
import type { Role } from "../auth/api";
import { ChatThread, fromStored, mascotOf, NO_MESSAGES, type ThreadMessage } from "./chat/ChatThread";
import { Icon } from "./Icon";
import { Mascot } from "./Mascot";

const PERSONAL = "__personal__";
const STORAGE_KEY = "eduagent.chat.class";

function readStoredClass(userId: string): string | null {
  try {
    return localStorage.getItem(`${STORAGE_KEY}:${userId}`);
  } catch {
    return null;
  }
}

function storeClass(userId: string, value: string) {
  try {
    localStorage.setItem(`${STORAGE_KEY}:${userId}`, value);
  } catch {
    // Storage can be blocked; the choice then lasts only for this page.
  }
}

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
  onBusyChange: (busy: boolean) => void;
  userId: string;
  role: Role;
  /** Class shown on the current page, preferred over the remembered one. */
  contextClassId?: string;
  /** Renders inside the page (student home) instead of as the slide-out panel. */
  inline?: boolean;
}

/** Slide-out chat with the agents of one class (or the user's personal agents). */
export function ChatPanel({ open, onClose, onBusyChange, userId, role, contextClassId, inline = false }: ChatPanelProps) {
  const classes = useResource(() => classesApi.list(), [userId]);
  const [classId, setClassId] = useState<string>(() => contextClassId ?? readStoredClass(userId) ?? "");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [initial, setInitial] = useState<ThreadMessage[]>(NO_MESSAGES);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [threadKey, setThreadKey] = useState(0);

  useEffect(() => {
    if (contextClassId) setClassId(contextClassId);
  }, [contextClassId]);

  // Default to the first class once the list arrives; parents and admins may chat outside a class.
  useEffect(() => {
    if (!classes.data || classId) return;
    setClassId(classes.data.find((room) => !room.archived)?.id ?? PERSONAL);
  }, [classes.data, classId]);

  const scope = classId === PERSONAL || !classId ? null : classId;
  const agents = useResource(() => (classId ? chatApi.agents(scope) : Promise.resolve([])), [classId, threadKey]);
  const history = useResource(() => (classId && historyOpen ? chatApi.conversations(scope) : Promise.resolve([])), [classId, historyOpen, threadKey]);
  const room = classes.data?.find((item) => item.id === scope);
  const requestFields = useMemo(() => ({ class_id: scope }), [scope]);
  const onConversation = useCallback((id: string) => setConversationId(id), []);

  function chooseClass(value: string) {
    setClassId(value);
    storeClass(userId, value);
    startNew();
  }

  function startNew() {
    setConversationId(null);
    setInitial(NO_MESSAGES);
    setThreadKey((value) => value + 1);
  }

  async function openConversation(id: string) {
    const stored = await chatApi.messages(id);
    setConversationId(id);
    setInitial(fromStored(stored, agents.data ?? []));
    setHistoryOpen(false);
  }

  if (!open && !inline) return null;
  const roomless = classes.data && classes.data.length === 0;
  const Frame = inline ? "section" : "aside";

  return (
    <Frame className={inline ? "ea-inline-chat" : "chat-panel chat-panel--open"} aria-labelledby="chat-panel-title">
      <div className="chat-panel__inner">
        <header className="chat-panel__header">
          <div className="agent-avatar agent-avatar--mascot"><Mascot character="fox" mood="idle" interactive /></div>
          <div>
            <strong id="chat-panel-title">Trợ lý lớp học</strong>
            <span>{room ? `${room.name} · ${(agents.data ?? []).length} agent` : "Agent cá nhân"}</span>
          </div>
          <button className="icon-button" type="button" onClick={startNew} aria-label="Cuộc trò chuyện mới" title="Cuộc trò chuyện mới"><Icon name="plus" /></button>
          <button className={`icon-button${historyOpen ? " is-active" : ""}`} type="button" onClick={() => setHistoryOpen((value) => !value)} aria-expanded={historyOpen} aria-label="Lịch sử trò chuyện" title="Lịch sử trò chuyện"><Icon name="history" /></button>
          {!inline && <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng trợ lý"><Icon name="x" /></button>}
        </header>

        <div className="ea-chat-context">
          <label className="visually-hidden" htmlFor="chat-class">Lớp</label>
          <select id="chat-class" value={classId} onChange={(event) => chooseClass(event.target.value)}>
            {(classes.data ?? []).filter((item) => !item.archived).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
            <option value={PERSONAL}>Không thuộc lớp (agent cá nhân)</option>
          </select>
          {(agents.data ?? []).length > 0 && (
            <ul className="ea-agent-strip" aria-label="Agent trong cuộc trò chuyện">
              {(agents.data ?? []).map((agent) => (
                <li key={agent.slug} title={`${agent.name}: ${agent.description}`}>
                  <Mascot character={mascotOf(agent.avatar)} mood="still" size={26} />
                  <span>@{agent.slug}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {historyOpen && (
          <div className="ea-chat-history">
            {history.loading && <p className="ea-muted">Đang tải…</p>}
            {history.data && history.data.length === 0 && <p className="ea-muted">Chưa có cuộc trò chuyện nào.</p>}
            <ul>
              {(history.data ?? []).map((item) => (
                <li key={item.id}>
                  <button type="button" className={item.id === conversationId ? "is-active" : ""} onClick={() => void openConversation(item.id)}>
                    <strong>{item.title || "Cuộc trò chuyện"}</strong>
                    <small>{new Date(item.updated_at).toLocaleString("vi-VN")}</small>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {agents.error && <p className="chat-control-note" role="alert">{agents.error}</p>}
        <ChatThread
          key={`${classId}:${threadKey}`}
          requestFields={requestFields}
          agents={agents.data ?? []}
          conversationId={conversationId}
          initialMessages={initial}
          onConversation={onConversation}
          onBusyChange={onBusyChange}
          disabled={!classId}
          emptyHint={
            roomless && role === "student" ? "Bạn chưa tham gia lớp nào. Vào “Lớp của tôi” để nhập mã lớp, hoặc trò chuyện với agent cá nhân."
              : role === "teacher" ? "Hỏi các agent của lớp: tạo đề, chấm bài, tóm tắt tài liệu… Gõ @ để gọi đích danh."
              : role === "parent" ? "Hỏi về việc học của con hoặc cách kèm con học ở nhà."
              : "Hỏi bài, ôn tập hoặc luyện tập. Agent sẽ gợi ý từng bước để bạn tự làm."
          }
        />
      </div>
    </Frame>
  );
}
