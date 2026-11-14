import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { type ChatStreamEvent, consumeChatStream } from "../../api-client/chatStream";
import type { AgentRef, AskEvent, PlanEvent, StepEvent, ChatAgent, ChatReply, Citation, StoredMessage } from "../../api-client/types";
import { Icon } from "../Icon";
import { Mascot, type MascotName } from "../Mascot";
import { AskCard, type AskCardData, sentState } from "./AskCard";
import { ChatMessageText, MessageBody, MessageCitations, MessageContributors, MessageSuggestions, replyExtras } from "./MessageBody";
import { applyPlan, applyStep, applyStepTool, finishProcess, ProcessPanel, processFromStored, type ProcessState } from "./ProcessPanel";
import { phaseLine } from "./thinking";

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
  /** `citations`: document passages; `suggestions`: follow-up questions. */
  items?: Citation[] | string[];
  /** `step` (feature 002). */
  key?: string;
  /** `tool` inside a step of the full path. */
  step_key?: string | null;
  /** `done` on the full path. */
  contributors?: AgentRef[];
}

/** Stable empty history; a fresh `[]` on every render would wipe the thread through the sync effect below. */
export const NO_MESSAGES: ThreadMessage[] = [];

export interface ThreadMessage {
  id: string;
  role: "user" | "assistant" | "notice";
  content: string;
  agent?: { slug: string; name: string; avatar: string; reason?: string };
  tools: { name: string; status: string }[];
  status: "ok" | "blocked" | "error" | "streaming";
  // For notices: guard_blocked, redacted, consent_required or context_reset (Dify lost the conversation's memory).
  kind?: string;
  citations?: Citation[];
  suggestions?: string[];
  /** A question or confirmation card (feature 002), live from `ask` or rebuilt from `meta.ask`. */
  ask?: AskCardData;
  /** Waiting line of the full path while no text has arrived (analyze, synthesis). */
  phase?: string;
  /** Agents that did a part of a full-path answer, other than its author (FR-029). */
  contributors?: AgentRef[];
  /** Progress panel of a full-path answer (FR-032 to FR-035). */
  process?: ProcessState;
}

/** Only the newest card that is still open, with no user message after it, can be answered (FR-036). */
export function activeAskId(messages: ThreadMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "user") return null;
    if (message.ask) return message.ask.state === "open" ? message.id : null;
  }
  return null;
}

function askFromStored(message: StoredMessage, agent: AgentRef | undefined): AskCardData | undefined {
  const ask = message.meta?.ask;
  if (!ask) return undefined;
  return { ...ask, agent: ask.agent ?? agent };
}

export function fromStored(messages: StoredMessage[], agents: ChatAgent[]): ThreadMessage[] {
  const bySlug = new Map(agents.map((agent) => [agent.slug, agent]));
  return messages.map((message) => {
    const agent = message.agent_slug ? bySlug.get(message.agent_slug) : undefined;
    // A reply the input guard gave in place of any agent is shown as a notice, as it was live.
    const guardNotice = message.role === "assistant" && message.status === "blocked" && !message.agent_slug;
    return {
      id: message.id,
      role: guardNotice ? "notice" : message.role,
      content: message.content,
      agent: message.agent_slug ? { slug: message.agent_slug, name: agent?.name ?? message.agent_slug, avatar: agent?.avatar ?? "owl", reason: message.meta?.route_reason } : undefined,
      tools: message.meta?.tools ?? [],
      // A question waiting for the user reads as a normal message until the ask card renders it.
      status: message.status === "awaiting_user" ? "ok" : message.status,
      citations: message.meta?.citations,
      suggestions: message.meta?.suggestions,
      contributors: message.meta?.contributors,
      process: processFromStored(message.meta?.process, agents),
      ask: askFromStored(message, agent ? { slug: agent.slug, name: agent.name, avatar: agent.avatar } : undefined),
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
  /** Text already in the box, e.g. a practice set the student opened with "Làm cùng gia sư". */
  initialInput?: string;
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
  initialInput = "",
}: ChatThreadProps) {
  const [messages, setMessages] = useState<ThreadMessage[]>(initialMessages);
  const [input, setInput] = useState(initialInput);
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

  async function send(text: string, reply?: ChatReply) {
    const question = text.trim();
    if (!question || sending || disabled) return;
    if (reply) {
      // The card locks at once with what was sent; the server records the same state (meta.ask.state).
      const state = sentState(reply);
      setMessages((current) => current.map((message) => (message.ask?.run_id === reply.run_id && message.ask.state === "open"
        ? { ...message, ask: { ...message.ask, state, answers: reply.answers } } : message)));
    }
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
          update(event.message_id!, (message) => ({ ...message, phase: undefined, content: message.content + (event.delta ?? "") }));
          break;
        case "step": {
          ensureReply(event.message_id!);
          const line = phaseLine(event.key ?? "");
          update(event.message_id!, (message) => ({
            ...message,
            phase: line ? (event.status === "running" ? line : undefined) : message.phase,
            process: applyStep(message.process, event as unknown as StepEvent),
          }));
          break;
        }
        case "plan":
          ensureReply(event.message_id!);
          update(event.message_id!, (message) => ({ ...message, process: applyPlan(message.process, event as unknown as PlanEvent) }));
          break;
        case "ask": {
          const ask = event as unknown as AskEvent;
          ensureReply(ask.message_id);
          update(ask.message_id, (message) => ({
            ...message,
            phase: undefined,
            agent: message.agent ?? { slug: ask.agent.slug, name: ask.agent.name, avatar: ask.agent.avatar },
            ask: { run_id: ask.run_id, kind: ask.kind, agent: ask.agent, intro: ask.intro, questions: ask.questions, confirm: ask.confirm, skippable: ask.skippable, state: "open" },
          }));
          break;
        }
        case "text_reset":
          // The answer was replaced: its sources and follow-ups no longer apply.
          update(event.message_id!, (message) => ({ ...message, content: "", citations: undefined, suggestions: undefined }));
          break;
        case "citations":
          update(event.message_id!, (message) => ({ ...message, citations: event.items as Citation[] }));
          break;
        case "suggestions":
          update(event.message_id!, (message) => ({ ...message, suggestions: event.items as string[] }));
          break;
        case "tool":
          ensureReply(event.message_id!);
          update(event.message_id!, (message) => {
            // A tool of a step belongs to that step in the panel, not to the answer.
            if (event.step_key) return { ...message, process: applyStepTool(message.process, event.step_key, event.name!, event.status!) };
            const others = message.tools.filter((tool) => tool.name !== event.name);
            return { ...message, tools: [...others, { name: event.name!, status: event.status! }] };
          });
          break;
        case "notice":
          setMessages((current) => [...current, { id: `${event.message_id}-${event.kind ?? "notice"}`, role: "notice", content: event.text ?? "", tools: [], status: "ok", kind: event.kind }]);
          break;
        case "error":
          if (replyId) update(replyId, (message) => ({ ...message, status: "error", content: message.content || (event.message ?? "") }));
          else setMessages((current) => [...current, { id: `${event.message_id}-error`, role: "notice", content: event.message ?? "Đã có lỗi.", tools: [], status: "error" }]);
          break;
        case "done":
          if (event.message_id) {
            // `awaiting_user`: the question card stands in for the answer until the user replies.
            const status = event.status === "blocked" ? "blocked" : event.status === "error" ? "error" : "ok";
            update(event.message_id, (message) => ({ ...message, status, phase: undefined, contributors: event.contributors ?? message.contributors, process: finishProcess(message.process) }));
          }
          break;
        default:
          break;
      }
    };

    try {
      const body = JSON.stringify({ ...requestFields, message: question, conversation_id: conversationRef.current, ...(reply ? { reply } : {}) });
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

  const openAsk = activeAskId(messages);
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
        {messages.map((message, index) => (
          <div key={message.id} className={`message message--${message.role === "notice" ? "assistant" : message.role}${message.role === "notice" ? ` ea-notice-message${message.kind === "context_reset" ? " ea-notice-message--soft" : ""}` : ""}${message.status === "error" ? " message--failed" : ""}${message.status === "blocked" ? " ea-blocked-message" : ""}`}>
            {message.role === "assistant" && message.agent && (
              <div className="message__meta">
                <Mascot character={mascotOf(message.agent.avatar)} mood={message.status === "streaming" ? "thinking" : "still"} />
                <strong>{message.agent.name}</strong>
                {message.agent.reason && AUTO_ROUTED.has(message.agent.reason) && <span className="ea-muted" title="Orchestrator chọn agent theo nội dung câu hỏi">· tự chọn</span>}
              </div>
            )}
            {message.tools.length > 0 && (
              <ul className="ea-tool-lines">
                {message.tools.map((tool) => (
                  <li key={tool.name} className={`ea-tool-line ea-tool-line--${tool.status}`}>
                    <Icon name={tool.status === "start" ? "clock" : tool.status === "done" ? "check" : "alert"} />
                    {tool.status === "start" ? TOOL_LABELS[tool.name] ?? tool.name
                      : tool.status === "done" ? `${(TOOL_LABELS[tool.name] ?? tool.name).replace("Đang ", "Đã ")}`
                      : tool.status === "confirm" ? `Công cụ ${tool.name} đang chờ xác nhận`
                      : tool.status === "denied" ? `Lớp bảo vệ đã chặn công cụ ${tool.name}` : `Công cụ ${tool.name} gặp lỗi`}
                  </li>
                ))}
              </ul>
            )}
            {message.role === "assistant" && message.process && message.process.steps.length > 0 && !message.ask && (
              <ProcessPanel process={message.process} messageId={message.status === "streaming" ? undefined : message.id} />
            )}
            {message.role === "assistant" && message.ask ? (
              <AskCard
                key={`${message.id}-${message.ask.state}`}
                ask={message.ask}
                active={!sending && !disabled && message.id === openAsk}
                mascot={mascotOf(message.ask.agent?.avatar ?? message.agent?.avatar)}
                onReply={(reply, text) => void send(text, reply)}
              />
            ) : message.role === "assistant" ? (
              message.content ? (
                <>
                  <MessageBody text={message.content} />
                  {message.status === "ok" && <MessageContributors items={message.contributors} />}
                  <MessageCitations items={replyExtras(message, index === messages.length - 1).citations} />
                  <MessageSuggestions
                    items={replyExtras(message, index === messages.length - 1).suggestions}
                    disabled={sending || disabled}
                    onPick={(question) => void send(question)}
                  />
                </>
              ) : message.phase ? (
                <span className="ea-phase" role="status"><span className="ea-typing" aria-hidden="true"><i /><i /><i /></span> {message.phase}</span>
              ) : <span className="ea-typing" aria-label="Đang trả lời"><i /><i /><i /></span>
            ) : message.role === "notice" ? (
              <p className="message__para"><Icon name={message.status === "error" ? "alert" : message.kind === "context_reset" ? "history" : "lock"} /> {message.content}</p>
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
