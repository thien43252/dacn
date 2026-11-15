import { type FormEvent, useState } from "react";
import { Modal } from "../../agents/Modal";
import { type Lesson, type LessonInput } from "../../api-client/lms";

interface LessonEditorProps {
  initial?: Lesson | null;
  onSubmit: (input: LessonInput) => Promise<void>;
  onClose: () => void;
}

export function LessonEditor({ initial, onSubmit, onClose }: LessonEditorProps) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [lessonDate, setLessonDate] = useState(initial?.lesson_date ?? "");
  const [publishAt, setPublishAt] = useState(() => {
    if (!initial?.publish_at) return "";
    try {
      const d = new Date(initial.publish_at);
      const pad = (n: number) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return "";
    }
  });

  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setError("Vui lòng nhập tiêu đề buổi học.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      await onSubmit({
        title: title.trim(),
        description: description.trim(),
        lesson_date: lessonDate ? lessonDate : null,
        publish_at: publishAt ? new Date(publishAt).toISOString() : null,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đã có lỗi xảy ra. Vui lòng thử lại.");
      setBusy(false);
    }
  }

  return (
    <Modal
      title={initial ? "Sửa buổi học" : "Tạo buổi học mới"}
      eyebrow="BUỔI HỌC"
      onClose={onClose}
      busy={busy}
      footer={
        <>
          <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>
            Huỷ
          </button>
          <button className="button button--primary" type="submit" form="lesson-editor-form" disabled={busy}>
            {busy ? "Đang lưu…" : initial ? "Lưu thay đổi" : "Tạo buổi học"}
          </button>
        </>
      }
    >
      <form id="lesson-editor-form" className="ea-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>Tiêu đề buổi học *</span>
          <input
            type="text"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ví dụ: Buổi 1 – Giới thiệu và Khái niệm cơ bản"
            required
            autoFocus
          />
        </label>

        <label className="field">
          <span>Mô tả ngắn</span>
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Mục tiêu hoặc hướng dẫn chung cho học sinh trong buổi này…"
          />
        </label>

        <div className="ea-form__row">
          <label className="field">
            <span>Ngày học</span>
            <input
              type="date"
              value={lessonDate}
              onChange={(e) => setLessonDate(e.target.value)}
            />
          </label>

          <label className="field">
            <span>Hẹn giờ công bố</span>
            <input
              type="datetime-local"
              value={publishAt}
              onChange={(e) => setPublishAt(e.target.value)}
            />
            <small className="ea-muted">Để trống để mở ngay khi công bố.</small>
          </label>
        </div>

        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
