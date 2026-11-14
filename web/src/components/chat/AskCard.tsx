import { type KeyboardEvent, useId, useState } from "react";

import type { AgentRef, AskConfirm, AskQuestion, AskState, ChatReply } from "../../api-client/types";
import { Icon } from "../Icon";
import { Mascot, type MascotName } from "../Mascot";

/** What a question card needs: the live `ask` event or `meta.ask` of a stored question message. */
export interface AskCardData {
  run_id: string;
  kind: "clarify" | "confirm";
  agent?: AgentRef;
  intro?: string;
  questions?: AskQuestion[];
  confirm?: AskConfirm;
  skippable?: boolean;
  state: AskState;
  answers?: Record<string, string>;
}

export const SKIP_ALL_MESSAGE = "Cứ làm luôn";
export const APPROVE_MESSAGE = "Đồng ý";
export const REJECT_MESSAGE = "Không";

export const ASK_STATE_LABELS: Record<AskState, string> = {
  open: "Đang chờ trả lời",
  answered: "Đã trả lời",
  skipped: "Đã chọn “Cứ làm luôn”",
  approved: "Đã đồng ý",
  rejected: "Đã từ chối",
  expired: "Câu hỏi đã hết hạn",
  cancelled: "Đã bỏ qua câu hỏi này",
};

/** The text of the user's turn: each answered question with its answer, so history reads naturally (FR-037). */
export function askMessage(questions: AskQuestion[], answers: Record<string, string>): string {
  const parts = questions.flatMap((item) => {
    const answer = (answers[item.id] || "").trim();
    return answer ? [`${item.question}\n${answer}`] : [];
  });
  return parts.join("\n\n") || SKIP_ALL_MESSAGE;
}

/** The `reply` and message for answers through the card; nothing answered counts as "Cứ làm luôn". */
export function clarifyReply(runId: string, questions: AskQuestion[], answers: Record<string, string>, skipAll = false): { reply: ChatReply; message: string } {
  const kept = Object.fromEntries(
    questions.flatMap((item) => {
      const answer = (answers[item.id] || "").trim();
      return answer && !skipAll ? [[item.id, answer.slice(0, 500)]] : [];
    }),
  );
  const skip = skipAll || Object.keys(kept).length === 0;
  return { reply: { run_id: runId, answers: kept, skip_all: skip }, message: skip ? SKIP_ALL_MESSAGE : askMessage(questions, kept) };
}

export function confirmReply(runId: string, approve: boolean): { reply: ChatReply; message: string } {
  return { reply: { run_id: runId, decision: approve ? "approve" : "reject" }, message: approve ? APPROVE_MESSAGE : REJECT_MESSAGE };
}

/** The state a card shows right after the user sent it, before the server's answer arrives. */
export function sentState(reply: ChatReply): AskState {
  if (reply.decision) return reply.decision === "approve" ? "approved" : "rejected";
  return reply.skip_all ? "skipped" : "answered";
}

interface AskCardProps {
  ask: AskCardData;
  /** Only the newest open card, with no message after it and nothing sending, can be used. */
  active: boolean;
  mascot: MascotName;
  onReply: (reply: ChatReply, message: string) => void;
}

/**
 * The question an agent asks before it goes on (clarify), or the confirmation it needs (confirm), as a card under the
 * conversation. Answers go back once; the card then locks. The chat box stays usable: typing there instead is a new
 * message that the backend may read as the answer or as a new request.
 */
export function AskCard({ ask, active, mascot, onReply }: AskCardProps) {
  const [sent, setSent] = useState(false);
  const locked = sent || !active || ask.state !== "open";
  const send = ({ reply, message }: { reply: ChatReply; message: string }) => {
    if (locked) return;
    setSent(true);
    onReply(reply, message);
  };
  const cardId = useId();
  const name = ask.agent?.name ?? "Agent";

  return (
    <section className={`question-card ask-card${locked ? " is-locked" : ""}`} aria-labelledby={`${cardId}-title`}>
      <header className="question-card__head">
        <Mascot character={mascot} mood="still" />
        <div>
          <strong id={`${cardId}-title`}>{ask.kind === "confirm" ? `${name} cần bạn xác nhận` : `${name} cần thêm thông tin`}</strong>
          <small>{ask.state !== "open" ? ASK_STATE_LABELS[ask.state] : ask.intro}</small>
        </div>
      </header>
      {ask.kind === "confirm" && ask.confirm
        ? <ConfirmBody confirm={ask.confirm} locked={locked} onDecide={(approve) => send(confirmReply(ask.run_id, approve))} />
        : <ClarifyBody ask={ask} locked={locked} onSend={(answers, skipAll) => send(clarifyReply(ask.run_id, ask.questions ?? [], answers, skipAll))} />}
    </section>
  );
}

function ClarifyBody({ ask, locked, onSend }: { ask: AskCardData; locked: boolean; onSend: (answers: Record<string, string>, skipAll: boolean) => void }) {
  const questions = ask.questions ?? [];
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>(ask.answers ?? {});
  const cardId = useId();
  if (questions.length === 0) return null;
  const current = questions[Math.min(index, questions.length - 1)];
  const answer = answers[current.id] || "";
  const chosen = current.options.find((option) => option === answer.trim());
  const last = index >= questions.length - 1;
  const answer_ = (value: string) => setAnswers((all) => ({ ...all, [current.id]: value }));

  function onKeys(event: KeyboardEvent<HTMLElement>) {
    if (locked || (event.target as HTMLElement).tagName === "TEXTAREA") return;
    const number = Number(event.key);
    if (Number.isInteger(number) && number >= 1 && number <= current.options.length) {
      event.preventDefault();
      answer_(current.options[number - 1]);
    }
  }

  return (
    <div className="ask-card__body" onKeyDown={onKeys}>
      {questions.length > 1 && (
        <ol className="question-card__steps" aria-label="Các câu hỏi">
          {questions.map((item, position) => (
            <li key={item.id}>
              <button
                type="button"
                className={`question-card__step${position === index ? " is-active" : ""}${(answers[item.id] || "").trim() ? " is-filled" : ""}`}
                aria-current={position === index}
                aria-label={`Câu ${position + 1}: ${item.question}`}
                onClick={() => setIndex(position)}
              >
                {(answers[item.id] || "").trim() ? <Icon name="check" /> : position + 1}
              </button>
            </li>
          ))}
        </ol>
      )}
      <p className="question-card__question" id={`${cardId}-question`}>{current.question}</p>
      {current.options.length > 0 && (
        <ul className="question-card__options">
          {current.options.map((option, position) => (
            <li key={option}>
              <button
                type="button"
                className={`question-card__option${chosen === option ? " is-chosen" : ""}`}
                aria-pressed={chosen === option}
                disabled={locked}
                onClick={() => answer_(chosen === option ? "" : option)}
              >
                <kbd aria-hidden="true">{position + 1}</kbd>
                <span><strong>{option}</strong></span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!locked && (
        <label className="question-card__free">
          <span>{current.options.length ? "Hoặc tự viết câu trả lời" : "Câu trả lời của bạn"}</span>
          <textarea
            rows={2}
            maxLength={500}
            value={chosen ? "" : answer}
            aria-labelledby={`${cardId}-question`}
            placeholder="Nhập câu trả lời…"
            onChange={(event) => answer_(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (last) onSend(answers, false);
                else setIndex(index + 1);
              }
            }}
          />
        </label>
      )}
      <footer className="question-card__foot">
        {ask.skippable !== false && (
          <button type="button" className="question-card__skip" disabled={locked} onClick={() => onSend({}, true)}>
            <Icon name="skip" /> {SKIP_ALL_MESSAGE}
          </button>
        )}
        <span className="question-card__spacer" />
        {questions.length > 1 && (
          <button type="button" className="question-card__nav" onClick={() => setIndex(index - 1)} disabled={index === 0} aria-label="Câu trước">
            <Icon name="chevron-left" />
          </button>
        )}
        {last ? (
          <button type="button" className="question-card__submit" onClick={() => onSend(answers, false)} disabled={locked}>
            <Icon name="send" /> Gửi câu trả lời
          </button>
        ) : (
          <button type="button" className="question-card__next" onClick={() => setIndex(index + 1)}>
            Câu tiếp <Icon name="chevron-right" />
          </button>
        )}
      </footer>
    </div>
  );
}

function ConfirmBody({ confirm, locked, onDecide }: { confirm: AskConfirm; locked: boolean; onDecide: (approve: boolean) => void }) {
  const preview = confirm.preview ?? {};
  const hasPreview = Boolean(preview.title || preview.body || preview.items?.length || preview.before !== undefined || preview.after !== undefined);
  return (
    <div className="ask-card__body">
      <p className="question-card__question">{confirm.summary}</p>
      {confirm.impact && <p className="ask-card__impact"><Icon name="alert" /> {confirm.impact}</p>}
      {typeof confirm.audience_count === "number" && (
        <p className="ea-muted ask-card__audience">Số người sẽ thấy: {confirm.audience_count}</p>
      )}
      {hasPreview && (
        <div className="ask-card__preview" aria-label="Xem trước">
          {preview.title && <strong>{preview.title}</strong>}
          {preview.body && <p>{preview.body}</p>}
          {preview.items && preview.items.length > 0 && (
            <ol>{preview.items.map((item, position) => <li key={position}>{item}</li>)}</ol>
          )}
          {(preview.before !== undefined || preview.after !== undefined) && (
            <dl className="ask-card__diff">
              <dt>Trước</dt><dd>{preview.before || "(trống)"}</dd>
              <dt>Sau</dt><dd>{preview.after || "(trống)"}</dd>
            </dl>
          )}
        </div>
      )}
      <footer className="question-card__foot">
        <span className="question-card__spacer" />
        <button type="button" className="ask-card__reject" disabled={locked} onClick={() => onDecide(false)}>
          {REJECT_MESSAGE}
        </button>
        <button type="button" className="question-card__submit" disabled={locked} onClick={() => onDecide(true)}>
          <Icon name="check" /> {APPROVE_MESSAGE}
        </button>
      </footer>
    </div>
  );
}
