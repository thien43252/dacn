import { memo } from "react";


const MENTION = String.raw`(?<![\w@])@(?:Project\s+Design|Feasibility\s*&\s*Capability|Policy\s*&\s*Governance|Safety\s*&\s*Governance|Progress\s*&\s*Evidence|planner|feasibility|safety|progress|all)\b`;
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
