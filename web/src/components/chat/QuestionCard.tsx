import { type KeyboardEvent, useId, useRef } from "react";

import { Icon } from "../Icon";
import { Mascot, mascotFor } from "../Mascot";

export type IntakeOption = { label: string; description?: string };
export type IntakeQuestion = { field: string; question: string; placeholder?: string; options?: IntakeOption[]; recommended?: string };

/** Brief fields and the outline decision are never supplied by a skip. */
export const UNSKIPPABLE_FIELDS = new Set(["topic", "users", "inputs", "outcome", "criteria", "timeframe", "outline"]);
const OPTIONAL_FIELDS = new Set(["members", "dates", "resources", "cadence"]);

/** Only rounds whose existing workflow accepts missing detail can be skipped. Unknown fields stay required. */
export function canSkipQuestion(field: string): boolean {
  return OPTIONAL_FIELDS.has(field) || field.startsWith("topic:") || field.startsWith("assignee:");
}

/** The workflow's explicit skip wording carries no suggested answer or implied consent. */
export const SKIPPED_ANSWER = "Bỏ qua";

/**
 * One round of questions as a single turn: each answer under its own question so the agent reads it verbatim, and
 * each skipped question said in words (the Planner reads that as "left open"). Unanswered, unskipped questions
 * are left out.
 */
export function questionRoundMessage(
  questions: IntakeQuestion[],
  answers: Record<string, string>,
  skipped: Record<string, boolean> = {},
): string {
  const parts = questions.flatMap((item) => {
    const answer = (answers[item.field] || "").trim();
    if (skipped[item.field] && canSkipQuestion(item.field)) return [`${item.question}\n${SKIPPED_ANSWER}`];
    return answer ? [`${item.question}\n${answer}`] : [];
  });
  return parts.join("\n\n");
}

export function firstUnanswered(questions: IntakeQuestion[], answers: Record<string, string>, skipped: Record<string, boolean>): number {
  return questions.findIndex((item) => !(answers[item.field] || "").trim() && !(canSkipQuestion(item.field) && skipped[item.field]));
}

interface QuestionCardProps {
  questions: IntakeQuestion[];
  active: number;
  answers: Record<string, string>;
  skipped: Record<string, boolean>;
  agent?: string;
  agentLabel: string;
  busy: boolean;
  /** Set while the running turn waits on these answers; they go back into that turn. */
  live: boolean;
  onSelect: (index: number) => void;
  onAnswer: (field: string, value: string) => void;
  onSkip: (field: string, skip: boolean) => void;
  onSkipAll: () => void;
  onSubmit: () => void;
}

/**
 * The agent's questions in their own card right under the agent's reply, one at a time, like the question prompt of
 * Claude: pick a suggestion or write an answer, skip what the group has not decided, and send the round once. The
 * chat box stays below for ordinary messages.
 */
export function QuestionCard({
  questions,
  active,
  answers,
  skipped,
  agent,
  agentLabel,
  busy,
  live,
  onSelect,
  onAnswer,
  onSkip,
  onSkipAll,
  onSubmit,
}: QuestionCardProps) {
  const index = Math.min(active, questions.length - 1);
  const current = questions[index];
  const options = current.options || [];
  const answer = answers[current.field] || "";
  const chosen = options.find((option) => option.label === answer.trim());
  const canSkip = canSkipQuestion(current.field);
  const isSkipped = canSkip && Boolean(skipped[current.field]);
  const last = index >= questions.length - 1;
  const answeredCount = questions.filter(item => !(canSkipQuestion(item.field) && skipped[item.field]) && (answers[item.field] || "").trim()).length;
  const skippedCount = questions.filter(item => canSkipQuestion(item.field) && skipped[item.field]).length;
  const freeRef = useRef<HTMLTextAreaElement>(null);
  const cardId = useId();

  function next() {
    if (last) onSubmit();
    else onSelect(index + 1);
  }

  function onCardKeys(event: KeyboardEvent<HTMLElement>) {
    if (busy) return;
    const target = event.target as HTMLElement;
    if (target.getAttribute("role") === "tab") {
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? questions.length - 1
        : event.key === "ArrowRight" ? (index + 1) % questions.length
        : event.key === "ArrowLeft" ? (index + questions.length - 1) % questions.length : null;
      if (nextIndex !== null) {
        event.preventDefault();
        onSelect(nextIndex);
        document.getElementById(`${cardId}-tab-${nextIndex}`)?.focus();
        return;
      }
    }
    if (target.tagName === "TEXTAREA") return;
    const number = Number(event.key);
    if (Number.isInteger(number) && number >= 1 && number <= options.length) {
      event.preventDefault();
      onAnswer(current.field, options[number - 1].label);
    }
  }

  function onFreeKeys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !busy) {
      event.preventDefault();
      next();
    }
  }

  return (
    <section className="question-card" aria-labelledby={`${cardId}-title`} aria-busy={busy} onKeyDown={onCardKeys}>
      <header className="question-card__head">
        <Mascot character={mascotFor(agent)} mood="still" />
        <div>
          <strong id={`${cardId}-title`}>{agentLabel} cần thêm thông tin</strong>
          <small>
            Câu {index + 1}/{questions.length}
            {` · Đã trả lời: ${answeredCount}`}{skippedCount > 0 ? ` · Bỏ qua: ${skippedCount}` : ""}
          </small>
        </div>
      </header>
      <ol className="question-card__steps" role="tablist" aria-label="Các câu hỏi">
        {questions.map((item, position) => {
          const filled = Boolean((answers[item.field] || "").trim());
          const state = skipped[item.field] && canSkipQuestion(item.field) ? "is-skipped" : filled ? "is-filled" : "";
          return (
            <li key={item.field}>
              <button
                type="button"
                role="tab"
                id={`${cardId}-tab-${position}`}
                aria-controls={`${cardId}-panel`}
                aria-label={`Câu ${position + 1}: ${item.question}${skipped[item.field] && canSkipQuestion(item.field) ? " · Để sau" : filled ? " · Đã trả lời" : " · Chưa trả lời"}`}
                tabIndex={position === index ? 0 : -1}
                disabled={busy}
                aria-selected={position === index}
                className={`question-card__step ${position === index ? "is-active" : ""} ${state}`}
                onClick={() => onSelect(position)}
                title={item.question}
              >
                {skipped[item.field] && canSkipQuestion(item.field) ? <Icon name="skip" /> : filled ? <Icon name="check" /> : position + 1}
              </button>
            </li>
          );
        })}
      </ol>

      <div id={`${cardId}-panel`} role="tabpanel" aria-labelledby={`${cardId}-tab-${index}`}>
      <p className="question-card__question" id={`${cardId}-question`}>{current.question}</p>

      {isSkipped && canSkip ? (
        <div className="question-card__skipped" role="status">
          <Icon name="skip" />
          <span>Bạn đã bỏ qua câu này. Thông tin này vẫn chưa được cung cấp.</span>
          <button type="button" className="link-button" disabled={busy} onClick={() => onSkip(current.field, false)}>Trả lời lại</button>
        </div>
      ) : (
        <>
          {options.length > 0 && (
            <ul className="question-card__options">
              {options.map((option, position) => (
                <li key={option.label}>
                  <button
                    type="button"
                    className={`question-card__option${chosen?.label === option.label ? " is-chosen" : ""}`}
                    aria-pressed={chosen?.label === option.label}
                    disabled={busy}
                    onClick={() => onAnswer(current.field, chosen?.label === option.label ? "" : option.label)}
                  >
                    <kbd aria-hidden="true">{position + 1}</kbd>
                    <span>
                      <strong>
                        {option.label}
                        {current.recommended === option.label && <em className="question-card__badge">Đề xuất</em>}
                      </strong>
                      {option.description && <small>{option.description}</small>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <label className="question-card__free">
            <span>{options.length ? "Hoặc tự viết câu trả lời của nhóm" : "Câu trả lời của nhóm"}</span>
            <textarea
              ref={freeRef}
              rows={2}
              maxLength={live ? 1500 : 2000}
              value={chosen ? "" : answer}
              disabled={busy}
              aria-labelledby={`${cardId}-question`}
              aria-required={!canSkip}
              placeholder={current.placeholder || "Nhập câu trả lời…"}
              onChange={(event) => onAnswer(current.field, event.target.value)}
              onKeyDown={onFreeKeys}
            />
          </label>
        </>
      )}
      </div>

      <footer className="question-card__foot">
        {canSkip && !isSkipped && (
          <button type="button" className="question-card__skip" onClick={() => { onSkip(current.field, true); if (!last) onSelect(index + 1); }} disabled={busy}>
            <Icon name="skip" /> Bỏ qua câu này
          </button>
        )}
        {!canSkip && <small className="question-card__hint">Cần trả lời câu này.</small>}
        <span className="question-card__spacer" />
        <button type="button" className="question-card__nav" onClick={() => onSelect(index - 1)} disabled={index === 0 || busy} aria-label="Câu trước">
          <Icon name="chevron-left" />
        </button>
        {last ? (
          <button type="button" className="question-card__submit" onClick={onSubmit} disabled={busy}>
            <Icon name="send" /> {busy ? "Đang gửi…" : "Gửi câu trả lời"}
          </button>
        ) : (
          <button type="button" className="question-card__next" onClick={() => onSelect(index + 1)} disabled={busy}>
            Câu tiếp <Icon name="chevron-right" />
          </button>
        )}
      </footer>
      {questions.some((item) => canSkipQuestion(item.field)) && (
        <button type="button" className="question-card__skip-all link-button" onClick={onSkipAll} disabled={busy}>
          Bỏ qua các câu tùy chọn
        </button>
      )}
    </section>
  );
}
