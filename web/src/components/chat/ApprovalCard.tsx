import { useState } from "react";

import { approvalsApi } from "../../api-client/chat";
import type { ApprovalCard as Card } from "../../api-client/types";
import { Icon } from "../Icon";

const STATUS_TEXT: Record<Card["status"], string> = {
  open: "Đang chờ bạn duyệt",
  allowed: "Đã cho phép",
  denied: "Đã từ chối",
  expired: "Đã hết hạn",
};

/** The approval card (FR-033): what is about to happen, a preview, who it affects, and the allowed answers. */
export function ApprovalCard({ card, viewerId, onAnswered }: { card: Card; viewerId: string; onAnswered?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const targets = card.preview.targets ?? [];
  const [recipient, setRecipient] = useState(targets[0]?.id ?? "");
  const mine = card.user_id === viewerId;
  const open = card.status === "open" && mine;

  async function answer(choice: string) {
    setBusy(true);
    setError(null);
    try {
      await approvalsApi.answer(card.id, choice, targets.length > 1 ? recipient : undefined);
      onAnswered?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không gửi được câu trả lời.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`ea-approval ea-approval--${card.status}`} role="group" aria-label="Yêu cầu duyệt">
      <header>
        <Icon name="shield" />
        <strong>{card.summary}</strong>
        <span className="ea-muted">{STATUS_TEXT[card.status]}</span>
      </header>
      {card.preview.body && <blockquote className="ea-approval__preview">{card.preview.body}</blockquote>}
      {targets.length > 1 && open ? (
        <label className="field">
          <span>Gửi cho</span>
          <select value={recipient} onChange={(event) => setRecipient(event.target.value)}>
            {targets.map((target) => <option key={target.id} value={target.id}>{target.name} ({target.role_label})</option>)}
          </select>
        </label>
      ) : targets.length > 0 ? (
        <p className="ea-muted">Người nhận: {targets.map((target) => `${target.name} ${target.role_label ? `(${target.role_label})` : ""}`).join(", ")}</p>
      ) : null}
      {open && (
        <div className="ea-approval__choices">
          {card.choices.map((choice) => (
            <button
              key={choice.id}
              type="button"
              disabled={busy}
              className={`button ${choice.id === "deny" || choice.id === "dont" ? "button--ghost" : choice.id === "once" ? "button--primary" : ""}`}
              onClick={() => void answer(choice.id)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
