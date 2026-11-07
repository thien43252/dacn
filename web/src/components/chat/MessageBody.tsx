import { memo } from "react";

import type { Citation } from "../../api-client/types";

/** Agent mentions are slugs such as @gia-su-toan. */
const MENTION = String.raw`(?<![\w@])@[a-z0-9]+(?:-[a-z0-9]+)*\b`;
const RICH_SPLIT = new RegExp(`(${MENTION}|\\*\\*[^\\n]+?\\*\\*)`, "gi");
const PLAIN_SPLIT = new RegExp(`(${MENTION})`, "gi");

/** Inline text of one line: agent mentions become chips and, for agent text only, **bold** becomes bold. */
export const ChatMessageText = memo(function ChatMessageText({ text, rich = false }: { text: string; rich?: boolean }) {
  const parts = text.split(rich ? RICH_SPLIT : PLAIN_SPLIT);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("@") ? <span key={`${part}-${index}`} className="message__mention">{part}</span>
          : rich && part.startsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
      )}
    </>
  );
});

export type MessageBlock = { kind: "text"; lines: string[] } | { kind: "list"; items: string[] };

const BULLET = /^\s*(?:[-•*]|\d+[.)])\s+/;

/** Split an agent reply into paragraphs and bullet lists, the only shapes the agents are asked to write. */
export function messageBlocks(text: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    if (!line.trim()) {
      if (last?.kind === "text" && last.lines.length) blocks.push({ kind: "text", lines: [] });
      continue;
    }
    if (BULLET.test(line)) {
      const item = line.replace(BULLET, "");
      if (last?.kind === "list") last.items.push(item);
      else blocks.push({ kind: "list", items: [item] });
    } else if (last?.kind === "text") {
      last.lines.push(line.trim());
    } else {
      blocks.push({ kind: "text", lines: [line.trim()] });
    }
  }
  return blocks.filter((block) => (block.kind === "text" ? block.lines.length > 0 : block.items.length > 0));
}

export function MessageBlocks({ blocks, rich }: { blocks: MessageBlock[]; rich: boolean }) {
  return (
    <>
      {blocks.map((block, index) =>
        block.kind === "list" ? (
          <ul className="message__list" key={index}>
            {block.items.map((item, position) => (
              <li key={position}><ChatMessageText rich={rich} text={item} /></li>
            ))}
          </ul>
        ) : (
          <p className="message__para" key={index}>
            {block.lines.map((line, position) => (
              <span key={position}>{position > 0 && <br />}<ChatMessageText rich={rich} text={line} /></span>
            ))}
          </p>
        ),
      )}
    </>
  );
}

/** Unstructured replies stay complete: no inferred summary can safely hide their warnings. */
export function MessageBody({ text, rich = true }: { text: string; rich?: boolean; collapsible?: boolean }) {
  if (!rich) return <ChatMessageText text={text} />;
  return (
    <div className="message__body">
      <MessageBlocks blocks={messageBlocks(text)} rich={rich} />
    </div>
  );
}

const EXCERPT_SHOWN = 160;

/** Sources and follow-ups belong to an answer that stands; follow-ups only under the latest one. */
export function replyExtras(
  message: { status: string; citations?: Citation[]; suggestions?: string[] },
  isLast: boolean,
): { citations: Citation[]; suggestions: string[] } {
  if (message.status !== "ok") return { citations: [], suggestions: [] };
  return { citations: message.citations ?? [], suggestions: isLast ? message.suggestions ?? [] : [] };
}

/** The class documents an answer drew on (class_doc_search), each with its place and a short excerpt. */
export function MessageCitations({ items }: { items: Citation[] }) {
  if (items.length === 0) return null;
  return (
    <details className="ea-citations">
      <summary>Nguồn từ tài liệu lớp ({items.length})</summary>
      <ul>
        {items.map((item) => (
          <li key={`${item.document_id}-${item.location}`}>
            <strong>{item.title}</strong>{item.location && <span className="ea-muted"> · {item.location}</span>}
            <blockquote>{item.excerpt.length > EXCERPT_SHOWN ? `${item.excerpt.slice(0, EXCERPT_SHOWN)}…` : item.excerpt}</blockquote>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Follow-up questions under the latest answer; picking one sends it as the next message. */
export function MessageSuggestions({ items, onPick, disabled = false }: { items: string[]; onPick: (question: string) => void; disabled?: boolean }) {
  if (items.length === 0) return null;
  return (
    <ul className="chat-suggestions ea-followups" aria-label="Câu hỏi gợi ý">
      {items.map((question) => (
        <li key={question}>
          <button type="button" disabled={disabled} onClick={() => onPick(question)}>{question}</button>
        </li>
      ))}
    </ul>
  );
}
