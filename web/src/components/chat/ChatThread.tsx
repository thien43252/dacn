import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { conversationsApi } from "../../api-client/chat";
import { type ChatStreamEvent, consumeChatStream } from "../../api-client/chatStream";
import type { ApprovalCard as ApprovalCardData, ChatAgent, HandoffNode, MessageSender, PersonRequest, StoredMessage } from "../../api-client/types";
import { useConversationEvents } from "../../features/chat/useConversationEvents";
import { Icon } from "../Icon";
import { Mascot, type MascotName } from "../Mascot";
import { ApprovalCard } from "./ApprovalCard";
import { HandoffBar } from "./HandoffBar";
import { ChatMessageText, MessageBody } from "./MessageBody";
import { PersonRequestCard } from "./PersonRequestCard";

const TOOL_LABELS: Record<string, string> = {
  class_doc_search: "Đang tìm trong tài liệu lớp",
  quiz_generator: "Đang soạn câu hỏi",
  rubric_grader: "Đang chấm theo rubric",
  math_check: "Đang kiểm tra phép tính",
  progress_summary: "Đang tổng hợp tiến độ học tập",
};
/** Route reasons where the orchestrator, not the user, picked the agent. */
const AUTO_ROUTED = new Set(["llm", "keyword", "sticky"]);
const MASCOT_NAMES = new Set(["fox", "cat", "panda", "penguin", "owl", "bear", "bunny", "deer", "frog", "hamster", "hedgehog", "koala", "otter", "raccoon", "redpanda"]);

export function mascotOf(avatar: string | undefined): MascotName {
  return (avatar && MASCOT_NAMES.has(avatar) ? avatar : "owl") as MascotName;
}

interface StreamEvent extends ChatStreamEvent {
  conversation_id?: string;
  name?: string;
  avatar?: string;
  reason?: string;
  status?: string;
  text?: string;
  kind?: string;
  message?: string;
}

/** Stable empty history; a fresh `[]` on every render would wipe the thread through the sync effect below. */
export const NO_MESSAGES: ThreadMessage[] = [];

export interface ThreadMessage {
  id: string;
  role: "user" | "assistant" | "notice" | "system";
  content: string;
  agent?: { slug: string; name: string; avatar: string; reason?: string };
  tools: { name: string; status: string }[];
  status: "ok" | "blocked" | "error" | "streaming" | "hidden";
  // Feature 003
  seq?: number;
  sender?: MessageSender;
  /** Set on a handoff's verbatim answer; in a group it is its own message "trả lời cho <agent>". */
  replyToAgent?: string | null;
  handoffs?: HandoffNode[];
  personRequest?: PersonRequest | null;
  approvalCard?: ApprovalCardData | null;
}

/** `kind` "direct": handoff answers live inside the asking message's "Đã hỏi" bars instead of the thread. */
export function fromStored(messages: StoredMessage[], agents: ChatAgent[], kind: "direct" | "group" = "direct"): ThreadMessage[] {
  const bySlug = new Map(agents.map((agent) => [agent.slug, agent]));
  return messages.filter((message) => kind === "group" || !message.handoff_id).map((message) => {
    const agent = message.agent_slug ? bySlug.get(message.agent_slug) : undefined;
    // A reply the input guard gave in place of any agent is shown as a notice, as it was live.
    const guardNotice = message.role === "assistant" && message.status === "blocked" && !message.agent_slug;
    const senderAvatar = message.sender?.kind === "agent" ? message.sender.avatar : null;
    return {
      id: message.id,
      role: guardNotice ? "notice" : message.role,
      content: message.content,
      agent: message.agent_slug ? { slug: message.agent_slug, name: agent?.name ?? message.sender?.name ?? message.agent_slug, avatar: agent?.avatar ?? senderAvatar ?? "owl", reason: message.meta?.route_reason } : undefined,
      tools: message.meta?.tools ?? [],
      status: message.status,
      seq: message.seq,
      sender: message.sender,
      replyToAgent: message.reply_to_agent,
      handoffs: message.handoffs ?? [],
      personRequest: message.person_request,
      approvalCard: message.approval_card,
    };
  });
}

interface ChatThreadProps {
  /** SSE endpoint; the builder sandbox uses its own. */
  endpoint?: string;
  /** Extra request fields (class_id, as_role…); the thread adds message, conversation_id and agent. */
  requestFields: Record<string, unknown>;
  agents: ChatAgent[];
  conversationId: string | null;
  initialMessages: ThreadMessage[];
  onConversation: (id: string) => void;
  onBusyChange?: (busy: boolean) => void;
  emptyHint: string;
  disabled?: boolean;
  /** Feature 003: who is reading (own messages, cards they may answer) and what kind of conversation this is. */
  viewerId?: string;
  kind?: "direct" | "group";
  /** Follow the conversation's event stream (handoff answers, conclusions, other members). Off in the sandbox. */
  live?: boolean;
  composerPlaceholder?: string;
}

export function ChatThread({
  endpoint = "/api/chat/stream",
  requestFields,
  agents,
  conversationId,
  initialMessages,
  onConversation,
  onBusyChange,
  emptyHint,
  disabled = false,
  viewerId,
  kind = "direct",
  live = true,
  composerPlaceholder,
}: ChatThreadProps) {
  const [messages, setMessages] = useState<ThreadMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [mention, setMention] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const conversationRef = useRef(conversationId);
  conversationRef.current = conversationId;
  const sendingRef = useRef(false);
  sendingRef.current = sending;
  const pendingRefresh = useRef(false);

  // Messages that arrive after the turn (handoff answers, the conclusion, other members, cards) come through the
  // conversation's event stream; the thread then reloads the stored messages, which carry seq and handoff trees.
  const refresh = useCallback(async () => {
    const id = conversationRef.current;
    if (!id) return;
    if (sendingRef.current) {
      pendingRefresh.current = true;
      return;
    }
    try {
      const stored = await conversationsApi.messages(id);
      if (sendingRef.current) {
        pendingRefresh.current = true;
        return;
      }
      setMessages(fromStored(stored, agents, kind));
      const last = stored[stored.length - 1]?.seq;
      if (last) void conversationsApi.markRead(id, last).catch(() => {});
    } catch {
      // The stream reconnects and asks again.
    }
  }, [agents, kind]);
  useConversationEvents(live ? conversationId : null, refresh);
  useEffect(() => {
    if (!sending && pendingRefresh.current) {
      pendingRefresh.current = false;
      void refresh();
    }
  }, [sending, refresh]);

  const agentOf = useCallback((slug: string) => {
    const found = agents.find((agent) => agent.slug === slug);
    return { name: found?.name ?? slug, avatar: mascotOf(found?.avatar) };
  }, [agents]);

  // Replaces the thread only when the caller loads a different history (pass NO_MESSAGES, not a fresh []).
  useEffect(() => setMessages(initialMessages), [initialMessages]);
  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => onBusyChange?.(sending), [onBusyChange, sending]);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  const matches = useMemo(() => {
    if (mention === null) return [];
    const needle = mention.toLowerCase();
    return agents.filter((agent) => agent.slug.includes(needle) || agent.name.toLowerCase().includes(needle)).slice(0, 6);
  }, [agents, mention]);

  function syncMention(element: HTMLTextAreaElement) {
    const before = element.value.slice(0, element.selectionStart ?? element.value.length);
    const match = /(^|\s)@([a-z0-9-]*)$/i.exec(before);
    setMention(match ? match[2] : null);
    setHighlighted(0);
  }

  function pickMention(agent: ChatAgent) {
    const element = inputRef.current;
    const caret = element?.selectionStart ?? input.length;
    const before = input.slice(0, caret).replace(/@([a-z0-9-]*)$/i, `@${agent.slug} `);
    const next = before + input.slice(caret);
    setInput(next);
    setMention(null);
    requestAnimationFrame(() => {
      element?.focus();
      element?.setSelectionRange(before.length, before.length);
    });
  }

  function update(id: string, change: (message: ThreadMessage) => ThreadMessage) {
    setMessages((current) => current.map((message) => (message.id === id ? change(message) : message)));
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || sending || disabled) return;
    const controller = new AbortController();
    abortRef.current = controller;
    const userId = `local-${crypto.randomUUID()}`;
    let replyId: string | null = null;
    setMessages((current) => [...current, { id: userId, role: "user", content: question, tools: [], status: "ok" }]);
    setInput("");
    setSending(true);

    const ensureReply = (id: string) => {
      if (replyId === id) return;
      replyId = id;
      setMessages((current) =>
        current.some((message) => message.id === id)
          ? current
          : [...current, { id, role: "assistant", content: "", tools: [], status: "streaming" }],
      );
    };

    const apply = (event: StreamEvent) => {
      switch (event.type) {
        case "conversation":
          if (event.conversation_id && event.conversation_id !== conversationRef.current) onConversation(event.conversation_id);
          break;
        case "agent":
          ensureReply(event.message_id!);
          update(event.message_id!, (message) => ({ ...message, agent: { slug: event.agent!, name: event.name ?? event.agent!, avatar: event.avatar ?? "owl", reason: event.reason } }));
          break;
        case "text_delta":
          ensureReply(event.message_id!);
          update(event.message_id!, (message) => ({ ...message, content: message.content + (event.delta ?? "") }));
          break;
        case "text_reset":
          update(event.message_id!, (message) => ({ ...message, content: "" }));
          break;
        case "tool":
          ensureReply(event.message_id!);
          update(event.message_id!, (message) => {
            const others = message.tools.filter((tool) => tool.name !== event.name);
            return { ...message, tools: [...others, { name: event.name!, status: event.status! }] };
          });
          break;
        case "notice":
          setMessages((current) => [...current, { id: `${event.message_id}-notice`, role: "notice", content: event.text ?? "", tools: [], status: "ok" }]);
          break;
        case "error":
          if (replyId) update(replyId, (message) => ({ ...message, status: "error", content: message.content || (event.message ?? "") }));
          else setMessages((current) => [...current, { id: `${event.message_id}-error`, role: "notice", content: event.message ?? "Đã có lỗi.", tools: [], status: "error" }]);
          break;
        case "done":
          if (event.message_id) {
            const status = event.status === "blocked" ? "blocked" : event.status === "error" ? "error" : "ok";
            update(event.message_id, (message) => ({ ...message, status }));
          }
          break;
        default:
          break;
      }
    };

    try {
      const body = JSON.stringify({ ...requestFields, message: question, conversation_id: conversationRef.current });
      await consumeChatStream<StreamEvent>(body, controller.signal, apply, 250, endpoint);
    } catch (error) {
      if (!controller.signal.aborted) {
        const text = error instanceof Error ? error.message : "Kết nối gián đoạn. Vui lòng thử lại.";
        setMessages((current) => [...current, { id: `err-${crypto.randomUUID()}`, role: "notice", content: text, tools: [], status: "error" }]);
      }
    } finally {
      setSending(false);
      sendingRef.current = false;
      abortRef.current = null;
      if (live) void refresh();
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (matches.length > 0) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setHighlighted((value) => (value + (event.key === "ArrowDown" ? 1 : matches.length - 1)) % matches.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        pickMention(matches[highlighted]);
        return;
      }
      if (event.key === "Escape") {
        setMention(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(input);
    }
  }

  const starters = agents.flatMap((agent) => agent.starter_prompts.slice(0, 1).map((prompt) => ({ prompt, agent }))).slice(0, 4);

  return (
    <>
      <div className="chat-panel__messages" ref={listRef} aria-live="polite" aria-label="Nội dung hội thoại">
        {messages.length === 0 && (
          <div className="ea-chat-empty">
            <p className="chat-panel__empty">{emptyHint}</p>
            {starters.length > 0 && (
              <ul className="chat-suggestions">
                {starters.map(({ prompt, agent }) => (
                  <li key={`${agent.slug}-${prompt}`}>
                    <button type="button" disabled={disabled} onClick={() => void send(agent.slug === "tro-ly-lop" ? prompt : `@${agent.slug} ${prompt}`)}>
                      {prompt}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {messages.map((message) => {
          if (message.role === "system") {
            return (
              <div key={message.id} className="message message--system">
                {message.approvalCard ? <ApprovalCard card={message.approvalCard} viewerId={viewerId ?? ""} onAnswered={() => void refresh()} />
                  : message.personRequest ? <PersonRequestCard request={message.personRequest} viewerId={viewerId ?? ""} onChanged={() => void refresh()} />
                  : <p className="message__para ea-muted"><Icon name="alert" /> {message.content}</p>}
              </div>
            );
          }
          const fromOther = message.role === "user" && !!message.sender?.id && !!viewerId && message.sender.id !== viewerId;
          const role = message.role === "notice" ? "assistant" : fromOther ? "assistant" : message.role;
          return (
          <div key={message.id} className={`message message--${role}${fromOther ? " message--person" : ""}${message.role === "notice" ? " ea-notice-message" : ""}${message.status === "error" ? " message--failed" : ""}${message.status === "blocked" ? " ea-blocked-message" : ""}${message.status === "hidden" ? " ea-hidden-message" : ""}`}>
            {fromOther && (
              <div className="message__meta">
                <span className="profile-avatar profile-avatar--small" aria-hidden="true">{(message.sender?.name ?? "?").charAt(0).toUpperCase()}</span>
                <strong>{message.sender?.name}</strong>
                {message.sender?.role_label && <span className="ea-muted">· {message.sender.role_label}</span>}
                {message.personRequest && <span className="ea-muted">· trả lời câu hỏi của agent</span>}
              </div>
            )}
            {message.role === "assistant" && message.agent && (
              <div className="message__meta">
                <Mascot character={mascotOf(message.agent.avatar)} mood={message.status === "streaming" ? "thinking" : "still"} />
                <strong>{message.agent.name}</strong>
                {message.replyToAgent && <span className="ea-muted ea-reply-to">· trả lời cho {agentOf(message.replyToAgent).name}</span>}
                {message.agent.reason && AUTO_ROUTED.has(message.agent.reason) && <span className="ea-muted" title="Orchestrator chọn agent theo nội dung câu hỏi">· tự chọn</span>}
              </div>
            )}
            {kind === "direct" && message.role === "assistant" && (message.handoffs?.length ?? 0) > 0 && (
              <div className="ea-handoffs" aria-label="Các agent đã được hỏi">
                {message.handoffs!.map((node) => <HandoffBar key={node.id} node={node} agentOf={agentOf} />)}
              </div>
            )}
            {kind === "group" && message.role === "assistant" && (message.handoffs?.length ?? 0) > 0 && (
              <ul className="ea-handoff-notes">
                {message.handoffs!.map((node) => (
                  <li key={node.id}><Icon name="sparkles" /> {message.agent?.name} đã hỏi {agentOf(node.to_agent).name}</li>
                ))}
              </ul>
            )}
            {message.tools.length > 0 && (
              <ul className="ea-tool-lines">
                {message.tools.map((tool) => (
                  <li key={tool.name} className={`ea-tool-line ea-tool-line--${tool.status}`}>
                    <Icon name={tool.status === "start" ? "clock" : tool.status === "done" ? "check" : "alert"} />
                    {tool.status === "start" ? TOOL_LABELS[tool.name] ?? tool.name
                      : tool.status === "done" ? `${(TOOL_LABELS[tool.name] ?? tool.name).replace("Đang ", "Đã ")}`
                      : tool.status === "denied" ? `Lớp bảo vệ đã chặn công cụ ${tool.name}` : `Công cụ ${tool.name} gặp lỗi`}
                  </li>
                ))}
              </ul>
            )}
            {message.role === "assistant" ? (
              message.content ? <MessageBody text={message.content} /> : <span className="ea-typing" aria-label="Đang trả lời"><i /><i /><i /></span>
            ) : message.role === "notice" ? (
              <p className="message__para"><Icon name={message.status === "error" ? "alert" : "lock"} /> {message.content}</p>
            ) : message.status === "hidden" ? (
              <p className="message__para ea-muted"><Icon name="lock" /> Nội dung đã được ẩn</p>
            ) : (
              <ChatMessageText text={message.content} />
            )}
          </div>
          );
        })}
      </div>

      <form className="chat-composer" onSubmit={submit}>
        {matches.length > 0 && (
          <ul className="mention-menu" id="chat-mention-menu" role="listbox" aria-label="Agent có thể gọi">
            {matches.map((agent, index) => (
              <li key={agent.slug} id={`chat-mention-${agent.slug}`} role="option" aria-selected={index === highlighted}>
                <button type="button" className={index === highlighted ? "is-active" : ""} onMouseDown={(event) => event.preventDefault()} onClick={() => pickMention(agent)}>
                  <span className="mention-menu__name">{agent.name}</span>
                  <span className="mention-menu__hint">@{agent.slug}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <label className="visually-hidden" htmlFor="chat-input">Nhập câu hỏi</label>
        <textarea
          id="chat-input"
          ref={inputRef}
          rows={2}
          value={input}
          maxLength={4000}
          disabled={disabled}
          placeholder={disabled ? "Chọn lớp để bắt đầu" : composerPlaceholder ?? "Đặt câu hỏi, hoặc gõ @ để gọi một agent…"}
          onChange={(event) => { setInput(event.target.value); syncMention(event.target); }}
          onSelect={(event) => syncMention(event.currentTarget)}
          onBlur={() => setMention(null)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={matches.length > 0}
          aria-controls={matches.length > 0 ? "chat-mention-menu" : undefined}
          aria-autocomplete="list"
        />
        {sending ? (
          <button className="send-button send-button--stop" type="button" aria-label="Dừng" onClick={() => abortRef.current?.abort()}>
            <Icon name="stop" />
          </button>
        ) : (
          <button className="send-button" type="submit" disabled={!input.trim() || disabled} aria-label="Gửi câu hỏi">
            <Icon name="send" />
          </button>
        )}
        <div className="chat-composer__foot">
          <button
            className={`mention-button ${mention !== null ? "is-active" : ""}`}
            type="button"
            disabled={disabled}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              const next = input && !input.endsWith(" ") ? `${input} @` : `${input}@`;
              setInput(next);
              setMention("");
              inputRef.current?.focus();
            }}
            aria-label="Gọi agent"
            title="Gọi agent"
          >
            @
          </button>
          <span className="ea-muted">Agent có thể sai. Hãy kiểm tra lại thông tin quan trọng.</span>
        </div>
      </form>
    </>
  );
}
