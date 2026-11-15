import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  type ItemViewsResponse,
  type LessonItem,
  type LessonStatus,
  fileUrl,
  lmsApi,
} from "../../api-client/lms";
import { errorMessage, useResource } from "../../app/useResource";
import { navigate } from "../../app/router";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { StatusBadge, type Tone } from "../shared/StatusBadge";
import { useLocation } from "../../app/router";
import { ItemEditor } from "./ItemEditor";
import { LessonEditor } from "./LessonEditor";
import { VideoPlayer } from "./VideoPlayer";
import "./lms.css";

interface LessonViewProps {
  classId: string;
  lessonId: string;
}

const AGENT_READABLE_EXTS = [".pdf", ".docx", ".txt", ".md"];
function isAgentReadableFile(filename?: string | null): boolean {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return AGENT_READABLE_EXTS.some((ext) => lower.endsWith(ext));
}

function isImageFile(filename?: string | null): boolean {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return [".png", ".jpg", ".jpeg", ".webp", ".gif"].some((ext) => lower.endsWith(ext));
}

function isPdfFile(filename?: string | null): boolean {
  if (!filename) return false;
  return filename.toLowerCase().endsWith(".pdf");
}

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

export function LessonView({ classId, lessonId }: LessonViewProps) {
  const { user } = useAuth();
  const role = user?.role ?? "student";
  const isTeacher = role === "teacher";
  const isStudent = role === "student";

  const { search } = useLocation();
  const studentId = new URLSearchParams(search).get("student_id") ?? undefined;
  const lessonResource = useResource(() => lmsApi.lessons.get(classId, lessonId, studentId), [classId, lessonId, studentId]);

  const [editingLesson, setEditingLesson] = useState(false);
  const [addingItem, setAddingItem] = useState(false);
  const [editingItem, setEditingItem] = useState<LessonItem | null>(null);
  const [deletingItem, setDeletingItem] = useState<LessonItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorNotice, setErrorNotice] = useState("");

  const lesson = lessonResource.data;

  // Record item views for students
  useEffect(() => {
    if (!isStudent || !lesson?.items) return;
    for (const item of lesson.items) {
      void lmsApi.items.recordView(classId, item.id).catch(() => {});
    }
  }, [classId, isStudent, lesson?.items]);

  if (lessonResource.error) {
    return (
      <div className="ea-page">
        <div className="ea-error">{lessonResource.error}</div>
        <button
          className="button button--secondary"
          type="button"
          onClick={() => navigate(`/${role}/classes/${classId}${role === "parent" && studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}`)}
        >
          <Icon name="chevron-left" /> Quay lại lớp học
        </button>
      </div>
    );
  }

  if (!lesson) {
    return (
      <div className="ea-page">
        <p className="ea-muted">Đang tải buổi học…</p>
      </div>
    );
  }

  const badge = getLessonBadge(lesson);

  async function handleLessonStatus(newStatus: LessonStatus) {
    try {
      setBusy(true);
      setErrorNotice("");
      const updated = await lmsApi.lessons.update(classId, lessonId, { status: newStatus });
      lessonResource.setData({ ...lesson!, ...updated });
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function moveItem(index: number, direction: "up" | "down") {
    if (!lesson?.items) return;
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= lesson.items.length) return;

    const newItems = [...lesson.items];
    const [moved] = newItems.splice(index, 1);
    newItems.splice(targetIndex, 0, moved);

    lessonResource.setData({ ...lesson, items: newItems });
    try {
      await lmsApi.items.reorder(
        classId,
        lessonId,
        newItems.map((it) => it.id),
      );
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
      lessonResource.reload();
    }
  }

  async function deleteCurrentItem() {
    if (!deletingItem) return;
    setBusy(true);
    try {
      await lmsApi.items.delete(classId, deletingItem.id);
      setDeletingItem(null);
      lessonResource.reload();
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleItemVisibility(item: LessonItem) {
    try {
      const updated = await lmsApi.items.update(classId, item.id, { visible: !item.visible });
      lessonResource.setData({
        ...lesson!,
        items: lesson!.items.map((it) => (it.id === item.id ? { ...it, visible: updated.visible } : it)),
      });
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    }
  }

  async function toggleAgentReadable(item: LessonItem) {
    try {
      const updated = await lmsApi.items.update(classId, item.id, {
        agent_readable: !item.agent_readable,
      });
      lessonResource.setData({
        ...lesson!,
        items: lesson!.items.map((it) =>
          it.id === item.id ? { ...it, agent_readable: updated.agent_readable } : it,
        ),
      });
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    }
  }

  return (
    <div className="ea-page lms-lesson-view">
      <div className="lms-header-actions">
        <button
          className="ea-back"
          type="button"
          onClick={() => navigate(`/${role}/classes/${classId}${role === "parent" && studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}`)}
        >
          <Icon name="chevron-left" /> Quay lại lớp học
        </button>

        {isTeacher && (
          <div className="lms-header-buttons">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setEditingLesson(true)}
            >
              <Icon name="edit" /> Sửa buổi học
            </button>

            {lesson.status === "draft" && (
              <button
                className="button button--primary"
                type="button"
                disabled={busy}
                onClick={() => void handleLessonStatus("published")}
              >
                Công bố
              </button>
            )}

            {lesson.status === "published" && (
              <button
                className="button button--secondary"
                type="button"
                disabled={busy}
                onClick={() => void handleLessonStatus("draft")}
              >
                Hạ về nháp
              </button>
            )}

            {lesson.status !== "archived" ? (
              <button
                className="button button--ghost"
                type="button"
                disabled={busy}
                onClick={() => void handleLessonStatus("archived")}
              >
                Lưu trữ
              </button>
            ) : (
              <button
                className="button button--secondary"
                type="button"
                disabled={busy}
                onClick={() => void handleLessonStatus("draft")}
              >
                Khôi phục về nháp
              </button>
            )}
          </div>
        )}
      </div>

      {errorNotice && (
        <div className="form-error" role="alert" style={{ marginBottom: "1rem" }}>
          {errorNotice}
        </div>
      )}

      <section className="ea-card lms-lesson-card">
        <div className="ea-card__meta">
          <StatusBadge label={badge.label} tone={badge.tone} />
          {lesson.lesson_date && (
            <span>
              <Icon name="calendar" /> Ngày: {new Date(lesson.lesson_date).toLocaleDateString("vi-VN")}
            </span>
          )}
          {lesson.publish_at && (
            <span>
              <Icon name="clock" /> Hẹn giờ mở: {new Date(lesson.publish_at).toLocaleString("vi-VN")}
            </span>
          )}
        </div>

        <h1 className="lms-lesson-title">{lesson.title}</h1>
        {lesson.description && <p className="lms-lesson-desc">{lesson.description}</p>}

        {lesson.locked && (
          <div className="lms-locked-notice">
            <Icon name="lock" />
            <p>
              Buổi học này chưa đến thời điểm mở. Mở lúc:{" "}
              <strong>{lesson.publish_at ? new Date(lesson.publish_at).toLocaleString("vi-VN") : "sau"}</strong>.
            </p>
          </div>
        )}
      </section>

      {!lesson.locked && (
        <section className="lms-items-section">
          <div className="ea-toolbar">
            <h2>Nội dung buổi học ({lesson.items?.length ?? 0})</h2>
            {isTeacher && (
              <button
                className="button button--primary"
                type="button"
                onClick={() => setAddingItem(true)}
              >
                <Icon name="plus" /> Thêm mục nội dung
              </button>
            )}
          </div>

          {(!lesson.items || lesson.items.length === 0) && (
            <div className="ea-empty">
              <Icon name="file" />
              <p>
                Buổi học này chưa có nội dung nào.{" "}
                {isTeacher ? "Hãy bấm nút 'Thêm mục nội dung' để thêm tài liệu, video, bài tập hoặc quiz." : ""}
              </p>
            </div>
          )}

          <div className="lms-items-list">
            {(lesson.items ?? []).map((item, index) => (
              <LessonItemRow
                key={item.id}
                item={item}
                index={index}
                totalItems={lesson.items.length}
                classId={classId}
                role={role}
                studentId={studentId}
                isTeacher={isTeacher}
                onMoveUp={() => void moveItem(index, "up")}
                onMoveDown={() => void moveItem(index, "down")}
                onEdit={() => setEditingItem(item)}
                onDelete={() => setDeletingItem(item)}
                onToggleVisibility={() => void toggleItemVisibility(item)}
                onToggleAgentReadable={() => void toggleAgentReadable(item)}
              />
            ))}
          </div>
        </section>
      )}

      {editingLesson && (
        <LessonEditor
          initial={lesson}
          onSubmit={async (input) => {
            const updated = await lmsApi.lessons.update(classId, lessonId, input);
            lessonResource.setData({ ...lesson, ...updated });
            setEditingLesson(false);
          }}
          onClose={() => setEditingLesson(false)}
        />
      )}

      {addingItem && (
        <ItemEditor
          classId={classId}
          lessonId={lessonId}
          onSubmit={() => {
            lessonResource.reload();
            setAddingItem(false);
          }}
          onClose={() => setAddingItem(false)}
        />
      )}

      {editingItem && (
        <ItemEditor
          classId={classId}
          lessonId={lessonId}
          initial={editingItem}
          onSubmit={() => {
            lessonResource.reload();
            setEditingItem(null);
          }}
          onClose={() => setEditingItem(null)}
        />
      )}

      <ConfirmDialog
        open={Boolean(deletingItem)}
        title={`Xoá "${deletingItem?.title}"?`}
        description="Bạn có chắc chắn muốn xoá mục này khỏi buổi học không?"
        confirmLabel="Xoá mục"
        busy={busy}
        onConfirm={() => void deleteCurrentItem()}
        onCancel={() => setDeletingItem(null)}
      />
    </div>
  );
}

// Single item row component
interface LessonItemRowProps {
  item: LessonItem;
  index: number;
  totalItems: number;
  classId: string;
  role: string;
  studentId?: string;
  isTeacher: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onToggleVisibility: () => void;
  onToggleAgentReadable: () => void;
}

function LessonItemRow({
  item,
  index,
  totalItems,
  classId,
  role,
  studentId,
  isTeacher,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
  onToggleVisibility,
  onToggleAgentReadable,
}: LessonItemRowProps) {
  const [views, setViews] = useState<ItemViewsResponse | null>(null);
  const [showViewsList, setShowViewsList] = useState(false);

  useEffect(() => {
    if (!isTeacher) return;
    let active = true;
    lmsApi.items.getViews(classId, item.id).then((res) => {
      if (active) setViews(res);
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, [classId, isTeacher, item.id]);

  const filename = item.file?.filename || (item.url ? item.url.split("/").pop() : undefined);
  const isImage = isImageFile(filename);
  const isPdf = isPdfFile(filename);
  const canAgent = isAgentReadableFile(filename);

  return (
    <article className={`ea-card lms-item-card ${!item.visible ? "lms-item-card--hidden" : ""}`}>
      <div className="lms-item-header">
        <div className="lms-item-header__left">
          {isTeacher && (
            <div className="lms-reorder-buttons" aria-label="Thứ tự hiển thị">
              <button
                className="icon-button"
                type="button"
                disabled={index === 0}
                onClick={onMoveUp}
                aria-label="Di chuyển lên"
                title="Di chuyển lên"
              >
                <Icon name="chevron-up" />
              </button>
              <button
                className="icon-button"
                type="button"
                disabled={index === totalItems - 1}
                onClick={onMoveDown}
                aria-label="Di chuyển xuống"
                title="Di chuyển xuống"
              >
                <Icon name="chevron-down" />
              </button>
            </div>
          )}

          <div className="lms-item-title-wrap">
            <div className="lms-item-meta">
              <span className="ea-chip">{itemKindLabel(item.kind)}</span>
              {!item.visible && <span className="ea-chip ea-chip--warn">Đã ẩn với học sinh</span>}
              {item.agent_readable && <span className="ea-chip ea-chip--ok">Cho agent đọc</span>}
              {isTeacher && views && (
                <button
                  type="button"
                  className="lms-views-badge"
                  onClick={() => setShowViewsList(!showViewsList)}
                  title="Nhấn để xem danh sách học sinh"
                >
                  <Icon name="eye" /> Đã xem {views.filter((student) => student.viewed).length}/{views.length}
                </button>
              )}
            </div>
            <h3 className="lms-item-title">{item.title}</h3>
          </div>
        </div>

        {isTeacher && (
          <div className="lms-item-actions">
            <button
              className="button button--ghost button--sm"
              type="button"
              onClick={onToggleVisibility}
              title={item.visible ? "Ẩn mục này với học sinh" : "Hiện mục này với học sinh"}
            >
              {item.visible ? "Ẩn" : "Hiện"}
            </button>

            {canAgent && (
              <button
                className="button button--ghost button--sm"
                type="button"
                onClick={onToggleAgentReadable}
                title="Bật/tắt cho agent đọc tài liệu này"
              >
                {item.agent_readable ? "Bỏ đọc AI" : "Cho AI đọc"}
              </button>
            )}

            <button
              className="icon-button"
              type="button"
              onClick={onEdit}
              aria-label="Sửa mục này"
              title="Sửa mục này"
            >
              <Icon name="edit" />
            </button>

            <button
              className="icon-button icon-button--danger"
              type="button"
              onClick={onDelete}
              aria-label="Xoá mục này"
              title="Xoá mục này"
            >
              <Icon name="trash" />
            </button>
          </div>
        )}
      </div>

      {isTeacher && showViewsList && views && (
        <div className="lms-views-popover">
          <h4>Trạng thái xem của học sinh ({views.filter((student) => student.viewed).length}/{views.length})</h4>
          {views.length === 0 ? (
            <p className="ea-muted">Chưa có dữ liệu học sinh trong lớp.</p>
          ) : (
            <ul className="lms-views-student-list">
              {views.map((st) => (
                <li key={st.student_id} className={st.first_viewed_at ? "is-viewed" : "is-not-viewed"}>
                  <strong>{st.name}</strong>
                  <span className="ea-muted">
                    {st.first_viewed_at
                      ? `Đã xem: ${new Date(st.first_viewed_at).toLocaleString("vi-VN")}`
                      : "Chưa xem"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {item.body && <div className="lms-item-body">{renderBodyParagraphs(item.body)}</div>}

      <div className="lms-item-content">
        {/* 1. Video kind */}
        {item.kind === "video" && (
          <VideoPlayer
            url={item.url}
            embedUrl={item.embed_url}
            fileUrl={item.file_id ? fileUrl(classId, item.file_id) : undefined}
            title={item.title}
          />
        )}

        {/* 2. File kind */}
        {item.kind === "file" && item.file_id && (
          <div className="lms-file-render">
            {isImage ? (
              <div className="lms-image-preview">
                <img
                  src={fileUrl(classId, item.file_id)}
                  alt={item.title}
                  loading="lazy"
                />
              </div>
            ) : isPdf ? (
              <div className="lms-pdf-preview">
                <iframe
                  src={fileUrl(classId, item.file_id)}
                  title={item.title}
                  className="lms-pdf-iframe"
                />
                <div className="lms-file-download-row">
                  <a
                    href={fileUrl(classId, item.file_id, true)}
                    download
                    className="button button--secondary button--sm"
                  >
                    <Icon name="upload" /> Tải về tệp PDF
                  </a>
                </div>
              </div>
            ) : (
              <div className="lms-file-download-box">
                <Icon name="file" />
                <div className="lms-file-download-info">
                  <strong>{filename || item.title}</strong>
                  <span className="ea-muted">Bấm vào nút bên cạnh để tải xuống máy tính.</span>
                </div>
                <a
                  href={fileUrl(classId, item.file_id, true)}
                  download
                  className="button button--secondary"
                >
                  Tải xuống tệp
                </a>
              </div>
            )}
          </div>
        )}

        {/* 3. Link kind */}
        {item.kind === "link" && item.url && (
          <div className="lms-link-render">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="button button--secondary"
            >
              <Icon name="globe" /> Mở liên kết: {item.title} ↗
            </a>
          </div>
        )}

        {/* 4. Assignment kind */}
        {item.kind === "assignment" && (
          <div className="lms-assignment-render">
            <p className="ea-muted">Nhiệm vụ bài tập được giao cho học sinh.</p>
            <button
              className="button button--primary"
              type="button"
              onClick={() => {
                if (role === "student") {
                  navigate(`/student/classes/${classId}/assignments/${item.id}`);
                } else if (role === "teacher") {
                  navigate(`/teacher/classes/${classId}/assignments/${item.id}`);
                } else {
                  navigate(`/parent/classes/${classId}/assignments/${item.id}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}`);
                }
              }}
            >
              {role === "student" ? "Làm bài tập / Nộp bài" : role === "teacher" ? "Quản lý bài nộp" : "Xem bài nộp của con"}
            </button>
          </div>
        )}

        {/* 5. Quiz kind */}
        {item.kind === "quiz" && (
          <div className="lms-quiz-render">
            <p className="ea-muted">Bài kiểm tra / Quiz trắc nghiệm đánh giá kiến thức.</p>
            <button
              className="button button--primary"
              type="button"
              onClick={() => {
                if (role === "student") {
                  navigate(`/student/classes/${classId}/quizzes/${item.id}`);
                } else if (role === "teacher") {
                  navigate(`/teacher/classes/${classId}/quizzes/${item.id}`);
                } else {
                  navigate(`/parent/classes/${classId}/quizzes/${item.id}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}`);
                }
              }}
            >
              {role === "student" ? "Bắt đầu làm bài kiểm tra" : role === "teacher" ? "Cấu hình & Kết quả quiz" : "Xem kết quả của con"}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

function itemKindLabel(kind: string): string {
  switch (kind) {
    case "file":
      return "Tài liệu";
    case "video":
      return "Video";
    case "link":
      return "Liên kết";
    case "text":
      return "Hướng dẫn";
    case "assignment":
      return "Bài tập";
    case "quiz":
      return "Bài kiểm tra";
    default:
      return kind;
  }
}

function renderBodyParagraphs(text: string) {
  return text.split(/\n\s*\n/).map((para, i) => (
    <p key={i} className="lms-item-paragraph">
      {para}
    </p>
  ));
}
