import { type FormEvent, useState } from "react";

import { inboxApi } from "../../api-client/chat";
import type { PersonRequest } from "../../api-client/types";
import { Icon } from "../Icon";

const STATUS_TEXT: Record<PersonRequest["status"], string> = {
  draft: "Chờ người hỏi duyệt",
  open: "Đang chờ trả lời",
  answered: "Đã trả lời",
  expired: "Đã hết hạn",
  cancelled: "Đã huỷ",
  undeliverable: "Không đến được người nhận",
};

/** A question an agent sent to a person (ask_person): options, free answer, status (FR-027 to FR-030). */
export function PersonRequestCard({ request, viewerId, onChanged }: { request: PersonRequest; viewerId: string; onChanged?: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canAnswer = request.status === "open" && request.recipient?.id === viewerId;
  const canCancel = request.status === "open" && request.requester?.id === viewerId && request.recipient?.id !== viewerId;
  const toSelf = request.recipient?.id === request.requester?.id;

  async function send(choice?: string) {
    if (!choice && !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await inboxApi.answer(request.id, { choice, text: text.trim() || undefined });
      setText("");
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không gửi được câu trả lời.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      await inboxApi.cancel(request.id);
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không huỷ được.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send();
  }

  return (
    <div className={`ea-person-request ea-person-request--${request.status}`} role="group" aria-label="Câu hỏi gửi người">
      <header>
        <Icon name={toSelf ? "sparkles" : "team"} />
        <span>
          {toSelf ? <><strong>{request.agent?.name ?? "Agent"}</strong> hỏi bạn</>
            : <><strong>{request.agent?.name ?? "Agent"}</strong> hỏi <strong>{request.recipient?.name}</strong> {request.recipient?.role_label ? `(${request.recipient.role_label})` : ""}</>}
          {request.requester && !toSelf && request.recipient?.id === viewerId && <> thay cho {request.requester.name}{request.requester.class ? `, lớp ${request.requester.class}` : ""}</>}
        </span>
        <span className="ea-muted">{STATUS_TEXT[request.status]}</span>
      </header>
      <p className="ea-person-request__body">{request.body}</p>
      {request.status === "answered" && (
        <p className="ea-person-request__answer"><Icon name="check" /> {request.answer_hidden ? "Câu trả lời đã được ẩn." : request.answer} {request.answered_by && <span className="ea-muted">· {request.answered_by}</span>}</p>
      )}
      {canAnswer && (
        <form className="ea-person-request__form" onSubmit={submit}>
          {request.options.length > 0 && (
            <div className="ea-approval__choices">
              {request.options.map((option) => (
                <button key={option} type="button" className="button" disabled={busy} onClick={() => void send(option)}>{option}</button>
              ))}
            </div>
          )}
          <label className="visually-hidden" htmlFor={`answer-${request.id}`}>Trả lời</label>
          <input id={`answer-${request.id}`} value={text} maxLength={2000} placeholder="Hoặc viết câu trả lời…" onChange={(event) => setText(event.target.value)} />
          <button className="button button--primary" type="submit" disabled={busy || !text.trim()}>Gửi</button>
        </form>
      )}
      {canCancel && <button type="button" className="button button--ghost" disabled={busy} onClick={() => void cancel()}>Huỷ câu hỏi</button>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
