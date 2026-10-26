import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { type ChatStreamEvent, consumeChatStream } from "../../api-client/chatStream";
import type { ChatAgent, StoredMessage } from "../../api-client/types";
import { Icon } from "../Icon";
import { Mascot, type MascotName } from "../Mascot";
import { ChatMessageText, MessageBody } from "./MessageBody";

const TOOL_LABELS: Record<string, string> = {
  class_doc_search: "Đang tìm trong tài liệu lớp",
  quiz_generator: "Đang soạn câu hỏi",
  rubric_grader: "Đang chấm theo rubric",
  math_check: "Đang kiểm tra phép tính",
  progress_summary: "Đang tổng hợp tiến độ học tập",
};
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
  role: "user" | "assistant" | "notice";
  content: string;
  agent?: { slug: string; name: string; avatar: string };
  tools: { name: string; status: string }[];
  status: "ok" | "blocked" | "error" | "streaming";
}

export function fromStored(messages: StoredMessage[], agents: ChatAgent[]): ThreadMessage[] {
  const bySlug = new Map(agents.map((agent) => [agent.slug, agent]));
  return messages.map((message) => {
    const agent = message.agent_slug ? bySlug.get(message.agent_slug) : undefined;
    return {
      id: message.id,
      role: message.role,
      content: message.content,
      agent: message.agent_slug ? { slug: message.agent_slug, name: agent?.name ?? message.agent_slug, avatar: agent?.avatar ?? "owl" } : undefined,
      tools: message.meta?.tools ?? [],
      status: message.status,
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
          update(event.message_id!, (message) => ({ ...message, agent: { slug: event.agent!, name: event.name ?? event.agent!, avatar: event.avatar ?? "owl" } }));
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
      abortRef.current = null;
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
        {messages.map((message) => (
          <div key={message.id} className={`message message--${message.role === "notice" ? "assistant" : message.role}${message.role === "notice" ? " ea-notice-message" : ""}${message.status === "error" ? " message--failed" : ""}${message.status === "blocked" ? " ea-blocked-message" : ""}`}>
            {message.role === "assistant" && message.agent && (
              <div className="message__meta">
                <Mascot character={mascotOf(message.agent.avatar)} mood={message.status === "streaming" ? "thinking" : "still"} />
                <strong>{message.agent.name}</strong>
              </div>
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
            ) : (
              <ChatMessageText text={message.content} />
            )}
          </div>
        ))}
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
          placeholder={disabled ? "Chọn lớp để bắt đầu" : "Đặt câu hỏi, hoặc gõ @ để gọi một agent…"}
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
