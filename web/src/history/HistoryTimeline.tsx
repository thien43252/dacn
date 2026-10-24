import { useEffect, useRef } from "react";

import { Icon } from "../components/Icon";
import type { HistoryEvent } from "./api";
import {
  actorFor,
  type BadgeMeta,
  badgeFor,
  EVENT_ICONS,
  formatTime,
  groupEventsByDay,
  SCHOOL_TIME_ZONE,
  SUGGESTION_EVENT,
  versionLine,
} from "./format";

interface HistoryTimelineProps {
  events: HistoryEvent[];
  today: string;
  showPlanOwner: boolean;
  onOpenDetail: (event: HistoryEvent, trigger: HTMLElement) => void;
}

export function HistoryTimeline({ events, today, showPlanOwner, onOpenDetail }: HistoryTimelineProps) {
  return (
    <div className="history-timeline" data-guide="history-list">
      {groupEventsByDay(events, today).map((day) => (
        <section className="history-day" key={day.key} aria-labelledby={`history-day-${day.key}`}>
          <h3 className="history-day__label" id={`history-day-${day.key}`}>{day.label}</h3>
          <ol className="history-list">
            {day.events.map((event) => (
              <li key={event.id}>
                <HistoryCard event={event} showPlanOwner={showPlanOwner} onOpenDetail={onOpenDetail} />
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

interface HistoryCardProps {
  event: HistoryEvent;
  showPlanOwner: boolean;
  onOpenDetail: (event: HistoryEvent, trigger: HTMLElement) => void;
}

function HistoryCard({ event, showPlanOwner, onOpenDetail }: HistoryCardProps) {
  const badge = badgeFor(event);
  const actor = actorFor(event);
  const version = versionLine(event);
  const titleId = `history-title-${event.id}`;

  return (
    <article className={`history-card frosted history-card--${event.category}`} aria-labelledby={titleId}>
      <header className="history-card__head">
        <span className="history-card__icon" aria-hidden="true"><Icon name={EVENT_ICONS[event.type]} /></span>
        {badge && <HistoryBadge {...badge} />}
        <time dateTime={event.occurred_at}>{formatTime(event.occurred_at)}</time>
      </header>
      <h4 id={titleId}>{event.title}</h4>
      <p className="history-card__actor">
        <Icon name={actor.icon} /> {actor.label}
        {showPlanOwner && event.plan_owner_name && event.actor.name !== event.plan_owner_name && (
          <span> · Kế hoạch của {event.plan_owner_name}</span>
        )}
      </p>
      {version && <p className="history-card__version">{version}</p>}
      <p className="history-card__summary">{event.summary}</p>
      {event.detail && (
        <button
          className="history-card__more"
          type="button"
          onClick={(clickEvent) => onOpenDetail(event, clickEvent.currentTarget)}
          aria-label={`Xem chi tiết: ${event.title}`}
        >
          Xem chi tiết <Icon name="arrow-right" />
        </button>
      )}
    </article>
  );
}

/** Status badge shared with the proposals tab: icon plus text, never colour alone. */
export function HistoryBadge({ label, icon, tone }: BadgeMeta) {
  return (
    <span className={`history-badge history-badge--${tone}`}>
      <Icon name={icon} /> {label}
    </span>
  );
}

const EVALUATION_NOTE = "Kết quả của agent này độc lập, không suy ra kết quả của agent đánh giá còn lại.";
const SUBMISSION_NOTE = "Gửi không đồng nghĩa với được duyệt; chỉ người có thẩm quyền mới ra quyết định.";
const SUGGESTION_NOTE = "Đề xuất được gửi để xem xét, chưa tạo hoặc kích hoạt agent.";

function noteFor(event: HistoryEvent): string | null {
  if (event.type.startsWith("evaluation.")) return EVALUATION_NOTE;
  if (event.type === "plan.submitted") return SUBMISSION_NOTE;
  return event.type === SUGGESTION_EVENT ? SUGGESTION_NOTE : null;
}

export function HistoryDetailModal({ event, onClose }: { event: HistoryEvent; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const badge = badgeFor(event);
  const actor = actorFor(event);
  const version = versionLine(event);
  const note = noteFor(event);

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === "Escape") onClose();
      if (keyEvent.key === "Tab") {
        keyEvent.preventDefault();
        closeRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="history-modal-backdrop" onMouseDown={(mouseEvent) => mouseEvent.target === mouseEvent.currentTarget && onClose()}>
      <div className="history-modal" role="dialog" aria-modal="true" aria-labelledby="history-modal-title">
        <header className="history-modal__head">
          <span className="history-card__icon" aria-hidden="true"><Icon name={EVENT_ICONS[event.type]} /></span>
          <div>
            {badge && <HistoryBadge {...badge} />}
            <h2 id="history-modal-title">{event.title}</h2>
          </div>
          <button ref={closeRef} className="icon-button" type="button" onClick={onClose} aria-label="Đóng chi tiết">
            <Icon name="x" />
          </button>
        </header>

        <dl className="history-modal__meta">
          <div><dt>Người thực hiện</dt><dd><Icon name={actor.icon} /> {actor.label}</dd></div>
          {event.plan_owner_name && <div><dt>Kế hoạch của</dt><dd>{event.plan_owner_name}</dd></div>}
          {version && <div><dt>Phiên bản</dt><dd>{version}</dd></div>}
          <div><dt>Thời gian</dt><dd>{new Date(event.occurred_at).toLocaleString("vi-VN", { timeZone: SCHOOL_TIME_ZONE })}</dd></div>
          {event.subject && <div><dt>Nội dung</dt><dd>{event.subject}</dd></div>}
        </dl>

        <p className="history-modal__summary">{event.summary}</p>

        {event.detail?.map((section) => (
          <section className="history-modal__section" key={section.label}>
            <h3>{section.label}</h3>
            <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        ))}

        {note && <p className="history-modal__note"><Icon name="alert" /> {note}</p>}
      </div>
    </div>
  );
}
