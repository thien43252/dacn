import { useState } from "react";
import type { ClassRoom } from "../../api-client/types";
import { type Lesson, type LessonStatus, lmsApi } from "../../api-client/lms";
import { errorMessage, useResource } from "../../app/useResource";
import { navigate, useLocation } from "../../app/router";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { StatusBadge, type Tone } from "../shared/StatusBadge";
import { LessonEditor } from "./LessonEditor";
import "./lms.css";

function getLessonBadge(lesson: { status: LessonStatus; publish_at?: string | null; locked?: boolean }): {
  label: string;
  tone: Tone;
} {
  if (lesson.locked) {
    return { label: "Sắp mở", tone: "warn" };
  }
  if (lesson.status === "archived") {
    return { label: "Lưu trữ", tone: "muted" };
  }
  if (lesson.status === "draft") {
    return { label: "Nháp", tone: "neutral" };
  }
  if (lesson.publish_at && new Date(lesson.publish_at) > new Date()) {
    return { label: "Hẹn giờ", tone: "info" };
  }
  return { label: "Đã công bố", tone: "positive" };
}

export function LessonsTab({ room }: { room: ClassRoom }) {
  const isTeacher = room.my_role === "teacher";
  const role = room.my_role || "student";

  const { search } = useLocation();
  const studentId = new URLSearchParams(search).get("student_id") ?? undefined;
  const lessonsResource = useResource(() => lmsApi.lessons.list(room.id, studentId), [room.id, studentId]);

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Lesson | null>(null);
  const [deleting, setDeleting] = useState<Lesson | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");

  const lessons = lessonsResource.data ?? [];

  async function handleStatusChange(lesson: Lesson, newStatus: LessonStatus) {
    try {
      setBusy(true);
      setErrorNotice("");
      await lmsApi.lessons.update(room.id, lesson.id, { status: newStatus });
      lessonsResource.reload();
      setNotice(
        newStatus === "published"
          ? `Đã công bố buổi học "${lesson.title}".`
          : newStatus === "archived"
            ? `Đã lưu trữ buổi học "${lesson.title}".`
            : `Đã chuyển buổi học "${lesson.title}" về bản nháp.`,
      );
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function moveLesson(index: number, direction: "up" | "down") {
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= lessons.length) return;

    const newLessons = [...lessons];
    const [moved] = newLessons.splice(index, 1);
    newLessons.splice(targetIndex, 0, moved);

    lessonsResource.setData(newLessons);
    try {
      await lmsApi.lessons.reorder(
        room.id,
        newLessons.map((l) => l.id),
      );
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
      lessonsResource.reload();
    }
  }

  // HTML5 Drag and Drop handlers
  function handleDragStart(index: number) {
    setDraggedIndex(index);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  async function handleDrop(targetIndex: number) {
    if (!isTeacher || draggedIndex === null || draggedIndex === targetIndex) {
      setDraggedIndex(null);
      return;
    }

    const newLessons = [...lessons];
    const [moved] = newLessons.splice(draggedIndex, 1);
    newLessons.splice(targetIndex, 0, moved);
    setDraggedIndex(null);

    lessonsResource.setData(newLessons);
    try {
      await lmsApi.lessons.reorder(
        room.id,
        newLessons.map((l) => l.id),
      );
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
      lessonsResource.reload();
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    setErrorNotice("");
    try {
      await lmsApi.lessons.delete(room.id, deleting.id);
      setDeleting(null);
      lessonsResource.reload();
      setNotice(`Đã xoá buổi học "${deleting.title}".`);
    } catch (err: unknown) {
      // If 409: lesson has attempts/submissions, alert user to archive instead
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function openLesson(lessonId: string) {
    const prefix = isTeacher ? "/teacher" : role === "parent" ? "/parent" : "/student";
    navigate(`${prefix}/classes/${room.id}/lessons/${lessonId}${role === "parent" && studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}`);
  }

  return (
    <div className="ea-page lms-lessons-tab">
      <div className="ea-toolbar">
        <div>
          <h2>Danh sách buổi học ({lessons.length})</h2>
          <p className="ea-muted">
            {isTeacher
              ? "Tạo buổi học, đăng tài liệu, video, bài tập và bài kiểm tra cho học sinh."
              : "Các buổi học và tài liệu học tập của lớp."}
          </p>
        </div>

        {isTeacher && (
          <div className="ea-toolbar__actions">
            <button
              className="button button--primary"
              type="button"
              onClick={() => setCreating(true)}
            >
              <Icon name="plus" /> Tạo buổi học
            </button>
          </div>
        )}
      </div>

      {notice && (
        <p className="ea-muted" role="status">
          {notice}
        </p>
      )}

      {errorNotice && (
        <div className="form-error" role="alert">
          {errorNotice}
        </div>
      )}

      {lessonsResource.error && <div className="ea-error">{lessonsResource.error}</div>}

      {lessons.length === 0 && !lessonsResource.loading && (
        <div className="ea-empty">
          <Icon name="book" />
          <p>
            {isTeacher
              ? "Lớp chưa có buổi học nào. Hãy bấm 'Tạo buổi học' để bắt đầu thiết kế nội dung bài giảng."
              : "Lớp chưa có buổi học nào được công bố."}
          </p>
        </div>
      )}

      <div className="lms-lesson-list">
        {lessons.map((lesson, index) => {
          const badge = getLessonBadge(lesson);

          return (
            <article
              key={lesson.id}
              className={`ea-card lms-lesson-card-item ${lesson.status === "archived" ? "lms-lesson-card-item--archived" : ""}`}
              draggable={isTeacher}
              onDragStart={() => handleDragStart(index)}
              onDragOver={handleDragOver}
              onDrop={() => void handleDrop(index)}
            >
              <div className="lms-lesson-item-main">
                {isTeacher && (
                  <div className="lms-reorder-buttons" aria-label="Thứ tự buổi học">
                    <button
                      className="icon-button"
                      type="button"
                      disabled={index === 0}
                      onClick={() => void moveLesson(index, "up")}
                      aria-label="Di chuyển lên"
                      title="Di chuyển lên"
                    >
                      <Icon name="chevron-up" />
                    </button>
                    <button
                      className="icon-button"
                      type="button"
                      disabled={index === lessons.length - 1}
                      onClick={() => void moveLesson(index, "down")}
                      aria-label="Di chuyển xuống"
                      title="Di chuyển xuống"
                    >
                      <Icon name="chevron-down" />
                    </button>
                  </div>
                )}

                <div className="lms-lesson-item-body">
                  <div className="ea-card__meta">
                    <StatusBadge label={badge.label} tone={badge.tone} />
                    {lesson.lesson_date && (
                      <span>
                        <Icon name="calendar" /> {new Date(lesson.lesson_date).toLocaleDateString("vi-VN")}
                      </span>
                    )}
                    {lesson.publish_at && (
                      <span>
                        <Icon name="clock" /> Hẹn giờ mở: {new Date(lesson.publish_at).toLocaleString("vi-VN")}
                      </span>
                    )}
                    {lesson.items.length !== undefined && (
                      <span>· {lesson.items.length} mục</span>
                    )}
                  </div>

                  <h3 className="lms-lesson-item-title">
                    {lesson.locked ? (
                      <span>{lesson.title}</span>
                    ) : (
                      <button
                        className="lms-link-button"
                        type="button"
                        onClick={() => openLesson(lesson.id)}
                      >
                        {lesson.title}
                      </button>
                    )}
                  </h3>

                  {lesson.description && (
                    <p className="ea-muted lms-lesson-item-desc">{lesson.description}</p>
                  )}

                  {lesson.locked && (
                    <div className="lms-locked-pill">
                      <Icon name="lock" /> Sắp mở lúc:{" "}
                      {lesson.publish_at ? new Date(lesson.publish_at).toLocaleString("vi-VN") : "sau"}
                    </div>
                  )}
                </div>
              </div>

              <div className="lms-lesson-item-actions">
                {!lesson.locked && (
                  <button
                    className="button button--secondary button--sm"
                    type="button"
                    onClick={() => openLesson(lesson.id)}
                  >
                    {isTeacher ? "Xem & soạn nội dung" : "Vào buổi học"} <Icon name="chevron-right" />
                  </button>
                )}

                {isTeacher && (
                  <div className="lms-teacher-actions">
                    {lesson.status === "draft" && (
                      <button
                        className="button button--ghost button--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleStatusChange(lesson, "published")}
                      >
                        Công bố
                      </button>
                    )}

                    {lesson.status === "published" && (
                      <button
                        className="button button--ghost button--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleStatusChange(lesson, "draft")}
                      >
                        Hạ về nháp
                      </button>
                    )}

                    {lesson.status !== "archived" ? (
                      <button
                        className="button button--ghost button--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleStatusChange(lesson, "archived")}
                      >
                        Lưu trữ
                      </button>
                    ) : (
                      <button
                        className="button button--ghost button--sm"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleStatusChange(lesson, "draft")}
                      >
                        Khôi phục
                      </button>
                    )}

                    <button
                      className="icon-button"
                      type="button"
                      onClick={() => setEditing(lesson)}
                      aria-label={`Sửa ${lesson.title}`}
                      title="Sửa thông tin buổi học"
                    >
                      <Icon name="edit" />
                    </button>

                    <button
                      className="icon-button icon-button--danger"
                      type="button"
                      onClick={() => setDeleting(lesson)}
                      aria-label={`Xoá ${lesson.title}`}
                      title="Xoá buổi học"
                    >
                      <Icon name="trash" />
                    </button>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {creating && (
        <LessonEditor
          onSubmit={async (input) => {
            await lmsApi.lessons.create(room.id, input);
            lessonsResource.reload();
            setCreating(false);
          }}
          onClose={() => setCreating(false)}
        />
      )}

      {editing && (
        <LessonEditor
          initial={editing}
          onSubmit={async (input) => {
            await lmsApi.lessons.update(room.id, editing.id, input);
            lessonsResource.reload();
            setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      )}

      <ConfirmDialog
        open={Boolean(deleting)}
        title={`Xoá buổi học "${deleting?.title}"?`}
        description="Nếu buổi học đã có bài nộp hoặc lượt làm bài kiểm tra, hãy chọn lưu trữ thay vì xoá."
        confirmLabel="Xoá buổi học"
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
