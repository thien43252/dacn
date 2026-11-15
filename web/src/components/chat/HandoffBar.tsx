import { useState } from "react";

import type { HandoffNode, HandoffStatus } from "../../api-client/types";
import { Icon } from "../Icon";
import { Mascot, type MascotName } from "../Mascot";
import { MessageBody } from "./MessageBody";

const STATUS_LABELS: Record<HandoffStatus, string> = {
  queued: "Đang hỏi",
  running: "Đang hỏi",
  answered: "Đã trả lời",
  no_answer: "Không nhận được câu trả lời",
  refused: "Bị từ chối",
  hidden: "Nội dung đã được ẩn",
  late: "Về muộn",
};

export interface AgentLookup {
  (slug: string): { name: string; avatar: MascotName };
}

/** "▸ Đã hỏi <agent>": one collapsible row per handoff in a direct chat, nested by depth (FR-020 to FR-022). */
export function HandoffBar({ node, agentOf, defaultOpen = false }: { node: HandoffNode; agentOf: AgentLookup; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const agent = agentOf(node.to_agent);
  const pending = node.status === "queued" || node.status === "running";
  const panelId = `handoff-${node.id}`;
  return (
    <div className={`ea-handoff ea-handoff--${node.status}`} data-testid="handoff-bar">
      <button
        type="button"
        className="ea-handoff__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="ea-handoff__caret" aria-hidden="true">{open ? "▾" : "▸"}</span>
        <Mascot character={agent.avatar} mood={pending ? "thinking" : "still"} size={22} />
        <span>Đã hỏi <strong>{agent.name}</strong></span>
        <span className={`ea-handoff__status${pending ? " is-pending" : ""}`}>
          {pending ? <span className="ea-typing" aria-hidden="true"><i /><i /><i /></span> : <Icon name={node.status === "answered" || node.status === "late" ? "check" : "alert"} />}
          {STATUS_LABELS[node.status]}
        </span>
      </button>
      {open && (
        <div className="ea-handoff__panel" id={panelId}>
          <dl className="ea-handoff__request">
            <div><dt>Việc cần làm</dt><dd>{node.task}</dd></div>
            <div><dt>Giới hạn</dt><dd>{node.bounds}</dd></div>
            <div><dt>Câu trả lời tốt</dt><dd>{node.good_answer}</dd></div>
          </dl>
          <div className="ea-handoff__answer">
            {node.answer ? <MessageBody text={node.answer} />
              : <p className="ea-muted">{pending ? `${agent.name} đang trả lời…` : STATUS_LABELS[node.status]}</p>}
          </div>
          {node.children.length > 0 && (
            <div className="ea-handoff__children">
              {node.children.map((child) => <HandoffBar key={child.id} node={child} agentOf={agentOf} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
