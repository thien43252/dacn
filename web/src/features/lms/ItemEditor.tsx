import { type FormEvent, useState } from "react";
import { Modal } from "../../agents/Modal";
import {
  type LessonItem,
  type LessonItemKind,
  type LmsFile,
  lmsApi,
} from "../../api-client/lms";
import { FileUpload } from "./FileUpload";

interface ItemEditorProps {
  classId: string;
  lessonId: string;
  initial?: LessonItem | null;
  onSubmit: (savedItem: LessonItem) => void;
  onClose: () => void;
}

const AGENT_READABLE_EXTS = [".pdf", ".docx", ".txt", ".md"];

function isAgentReadableCandidate(filename?: string | null): boolean {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return AGENT_READABLE_EXTS.some((ext) => lower.endsWith(ext));
}

export function ItemEditor({ classId, lessonId, initial, onSubmit, onClose }: ItemEditorProps) {
  const isEditing = Boolean(initial);
  const [kind, setKind] = useState<LessonItemKind>(initial?.kind ?? "file");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [fileId, setFileId] = useState(initial?.file_id ?? "");
  const [uploadedFile, setUploadedFile] = useState<LmsFile | null>(initial?.file ?? null);
  const [visible, setVisible] = useState(initial ? initial.visible : true);
  const [agentReadable, setAgentReadable] = useState(initial?.agent_readable ?? false);

  // Video source type: link vs file upload
  const [videoMode, setVideoMode] = useState<"link" | "upload">(
    initial?.file_id ? "upload" : "link",
  );

  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const canBeAgentReadable = isAgentReadableCandidate(uploadedFile?.filename);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setError("Vui lòng nhập tiêu đề cho mục nội dung.");
      return;
    }

    if (kind === "file" && !fileId) {
      setError("Vui lòng tải lên một tệp tài liệu.");
      return;
    }

    if (kind === "video") {
      if (videoMode === "link" && !url.trim()) {
        setError("Vui lòng dán đường link video (YouTube, Vimeo, ...).");
        return;
      }
      if (videoMode === "upload" && !fileId) {
        setError("Vui lòng tải lên tệp video.");
        return;
      }
    }

    if (kind === "link" && !url.trim()) {
      setError("Vui lòng nhập địa chỉ liên kết (URL).");
      return;
    }

    if (kind === "text" && !body.trim()) {
      setError("Vui lòng nhập nội dung đoạn văn bản.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      if (isEditing && initial) {
        const updated = await lmsApi.items.update(classId, initial.id, {
          title: title.trim(),
          body: body.trim(),
          url: kind === "video" && videoMode === "upload" ? null : url.trim() || null,
          file_id: kind === "video" && videoMode === "link" ? null : fileId || null,
          visible,
          agent_readable: canBeAgentReadable ? agentReadable : false,
        });
        onSubmit(updated);
      } else {
        const created = await lmsApi.items.create(classId, lessonId, {
          kind,
          title: title.trim(),
          body: body.trim(),
          url: kind === "video" && videoMode === "upload" ? null : url.trim() || null,
          file_id: kind === "video" && videoMode === "link" ? null : fileId || null,
        });

        // If agent_readable or visible need to be updated after creation
        if ((canBeAgentReadable && agentReadable) || !visible) {
          const patched = await lmsApi.items.update(classId, created.id, {
            visible,
            agent_readable: canBeAgentReadable ? agentReadable : false,
          });
          onSubmit(patched);
        } else {
          onSubmit(created);
        }
      }
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đã có lỗi xảy ra khi lưu mục nội dung.");
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isEditing ? "Sửa mục nội dung" : "Thêm mục nội dung"}
      eyebrow="NỘI DUNG BUỔI HỌC"
      onClose={onClose}
      busy={busy}
      wide
      footer={
        <>
          <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>
            Huỷ
          </button>
          <button className="button button--primary" type="submit" form="item-editor-form" disabled={busy}>
            {busy ? "Đang lưu…" : isEditing ? "Lưu thay đổi" : "Thêm mục"}
          </button>
        </>
      }
    >
      <form id="item-editor-form" className="ea-form" onSubmit={handleSubmit}>
        {!isEditing && (
          <div className="ea-form__row">
            <label className="field">
              <span>Loại nội dung *</span>
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as LessonItemKind);
                  setError("");
                }}
              >
                <option value="file">Tài liệu (tệp đính kèm)</option>
                <option value="video">Video (YouTube, Vimeo hoặc tệp tải lên)</option>
                <option value="link">Liên kết ngoài</option>
                <option value="text">Đoạn văn bản hướng dẫn</option>
                <option value="assignment">Bài tập</option>
                <option value="quiz">Quiz / Bài kiểm tra</option>
              </select>
            </label>
          </div>
        )}

        <label className="field">
          <span>Tiêu đề *</span>
          <input
            type="text"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Ví dụ: Bài giảng dạng PDF / Video thí nghiệm / Hướng dẫn tự học"
            required
            autoFocus
          />
        </label>

        {/* Kind-specific inputs */}
        {kind === "file" && (
          <div className="lms-item-editor__section">
            <FileUpload
              classId={classId}
              purpose="content"
              accept=".pdf,.docx,.pptx,.xlsx,.txt,.md,.png,.jpg,.webp,.zip"
              label="Chọn tệp tài liệu (PDF, DOCX, PPTX, ảnh... tối đa 25 MB)"
              onUploaded={(f) => {
                setFileId(f.id);
                setUploadedFile(f);
                if (!title) setTitle(f.filename.replace(/\.[^/.]+$/, ""));
              }}
            />

            {canBeAgentReadable && (
              <label className="ea-switch" style={{ marginTop: "1rem" }}>
                <input
                  type="checkbox"
                  checked={agentReadable}
                  onChange={(e) => setAgentReadable(e.target.checked)}
                />
                <span>
                  <strong>Cho agent đọc</strong>
                  <br />
                  <small className="ea-muted">
                    Đưa tài liệu này vào kho tri thức để các trợ lý AI trong lớp dùng khi trả lời câu hỏi của học sinh.
                  </small>
                </span>
              </label>
            )}
          </div>
        )}

        {kind === "video" && (
          <div className="lms-item-editor__section">
            <div className="chip-row" style={{ marginBottom: "0.75rem" }}>
              <button
                type="button"
                className={`chip ${videoMode === "link" ? "is-selected" : ""}`}
                onClick={() => setVideoMode("link")}
              >
                Đường link video (YouTube, Vimeo, MP4)
              </button>
              <button
                type="button"
                className={`chip ${videoMode === "upload" ? "is-selected" : ""}`}
                onClick={() => setVideoMode("upload")}
              >
                Tải tệp video lên máy chủ (tối đa 200 MB)
              </button>
            </div>

            {videoMode === "link" ? (
              <label className="field">
                <span>Đường link video *</span>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=... hoặc https://vimeo.com/..."
                />
              </label>
            ) : (
              <FileUpload
                classId={classId}
                purpose="content"
                accept="video/mp4,video/webm,.mp4,.webm"
                label="Chọn tệp video MP4 hoặc WebM (tối đa 200 MB)"
                onUploaded={(f) => {
                  setFileId(f.id);
                  setUploadedFile(f);
                  if (!title) setTitle(f.filename.replace(/\.[^/.]+$/, ""));
                }}
              />
            )}
          </div>
        )}

        {kind === "link" && (
          <label className="field">
            <span>Địa chỉ liên kết (URL) *</span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/tai-lieu-tham-khao"
              required
            />
          </label>
        )}

        <label className="field">
          <span>{kind === "text" ? "Nội dung văn bản *" : "Mô tả / Hướng dẫn thêm (không bắt buộc)"}</span>
          <textarea
            rows={kind === "text" ? 6 : 3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={
              kind === "text"
                ? "Nhập nội dung hướng dẫn chi tiết cho học sinh…"
                : "Ghi chú ngắn cho học sinh khi mở mục này…"
            }
            required={kind === "text"}
          />
        </label>

        <label className="ea-switch" style={{ marginTop: "0.5rem" }}>
          <input
            type="checkbox"
            checked={!visible}
            onChange={(e) => setVisible(!e.target.checked)}
          />
          <span>
            <strong>Ẩn với học sinh</strong>
            <br />
            <small className="ea-muted">
              Mục này sẽ tạm thời bị ẩn với học sinh và phụ huynh trong buổi học.
            </small>
          </span>
        </label>

        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
