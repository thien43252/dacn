import { useResource } from "../../app/useResource";
import { navigate } from "../../app/router";
import { feedApi } from "../../api-client/classes";
import type { Announcement, AnnouncementAudience, Assignment } from "../../api-client/types";
import { Icon } from "../../components/Icon";

export const AUDIENCE_LABELS: Record<AnnouncementAudience, string> = {
  students: "Học sinh",
  parents: "Phụ huynh",
  all: "Học sinh và phụ huynh",
};

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }) : "";
}

/** The message a student sends to work on a practice set with the tutor: its questions, never its answers. */
export function practiceDraft(assignment: Pick<Assignment, "title" | "questions">): string {
  const questions = assignment.questions.map((item, index) => {
    const options = item.options?.length ? `\n   ${item.options.map((option, i) => `${String.fromCharCode(65 + i)}. ${option}`).join("  ")}` : "";
    return `${index + 1}. ${item.question}${options}`;
  });
  return [`Mình muốn làm bài luyện “${assignment.title}”`, ...questions].join("\n");
}

/** Where "Làm cùng gia sư" goes: the student's chat in that class, with the draft in the box. */
export function practiceLink(classId: string, assignment: Pick<Assignment, "title" | "questions">): string {
  return `/student/home?class=${encodeURIComponent(classId)}&draft=${encodeURIComponent(practiceDraft(assignment))}`;
}

export function AnnouncementItem({ item, onDelete }: { item: Announcement; onDelete?: () => void }) {
  return (
    <li className="ea-feed__item">
      <div className="ea-feed__head">
        <strong>{item.title}</strong>
        <span className="ea-chip">{AUDIENCE_LABELS[item.audience]}</span>
        {item.source === "agent" && <span className="ea-chip" title="Đăng qua agent sau khi giáo viên xác nhận">Qua agent</span>}
        {onDelete && (
          <button type="button" className="icon-button" aria-label={`Xoá thông báo ${item.title}`} onClick={onDelete}><Icon name="trash" /></button>
        )}
      </div>
      <p className="ea-feed__body">{item.body}</p>
      <small className="ea-muted">{item.author_name ?? "Giáo viên"} · {formatDate(item.created_at)}</small>
    </li>
  );
}

export function AssignmentItem({
  item,
  showAnswers = false,
  action,
  onDelete,
}: {
  item: Assignment;
  showAnswers?: boolean;
  action?: { label: string; onClick: () => void };
  onDelete?: () => void;
}) {
  return (
    <li className="ea-feed__item">
      <div className="ea-feed__head">
        <strong>{item.title}</strong>
        <span className="ea-chip">{item.questions.length} câu</span>
        {item.due_at && <span className="ea-chip ea-chip--warn">Hạn {formatDate(item.due_at)}</span>}
        {onDelete && (
          <button type="button" className="icon-button" aria-label={`Xoá bài luyện ${item.title}`} onClick={onDelete}><Icon name="trash" /></button>
        )}
      </div>
      {item.instructions && <p className="ea-feed__body">{item.instructions}</p>}
      <details>
        <summary>Xem câu hỏi</summary>
        <ol className="ea-feed__questions">
          {item.questions.map((question, index) => (
            <li key={index}>
              {question.question}
              {question.options && question.options.length > 0 && <span className="ea-muted"> ({question.options.join(" · ")})</span>}
            </li>
          ))}
        </ol>
        {showAnswers && item.answer_key && item.answer_key.length > 0 && (
          <div className="ea-feed__answers">
            <strong>Đáp án (chỉ giáo viên thấy)</strong>
            <ol>{item.answer_key.map((key) => <li key={key.index} value={key.index}>{key.answer}{key.explanation ? ` · ${key.explanation}` : ""}</li>)}</ol>
          </div>
        )}
      </details>
      {action && (
        <div><button type="button" className="button button--secondary" onClick={action.onClick}><Icon name="message" /> {action.label}</button></div>
      )}
    </li>
  );
}

/** What a student or a parent sees of one class: announcements meant for them and the practice sets. */
export function ClassFeedList({ classId, role }: { classId: string; role: "student" | "parent" }) {
  const announcements = useResource(() => feedApi.announcements(classId), [classId]);
  const assignments = useResource(() => feedApi.assignments(classId), [classId]);
  const empty = announcements.data?.length === 0 && assignments.data?.length === 0;
  return (
    <div className="ea-feed">
      {(announcements.error || assignments.error) && <div className="ea-error">{announcements.error || assignments.error}</div>}
      {empty && <p className="ea-muted">Chưa có thông báo hay bài luyện nào.</p>}
      {(announcements.data ?? []).length > 0 && (
        <ul className="ea-feed__list" aria-label="Thông báo của lớp">
          {(announcements.data ?? []).map((item) => <AnnouncementItem key={item.id} item={item} />)}
        </ul>
      )}
      {(assignments.data ?? []).length > 0 && (
        <ul className="ea-feed__list" aria-label="Bài luyện của lớp">
          {(assignments.data ?? []).map((item) => (
            <AssignmentItem
              key={item.id}
              item={item}
              action={role === "student" ? { label: "Làm cùng gia sư", onClick: () => navigate(practiceLink(classId, item)) } : undefined}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
