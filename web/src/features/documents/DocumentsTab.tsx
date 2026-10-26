import { type FormEvent, useEffect, useRef, useState } from "react";

import { Modal } from "../../agents/Modal";
import { errorMessage, useResource } from "../../app/useResource";
import { documentsApi } from "../../api-client/agents";
import type { ClassDocument, ClassRoom } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";

const ACCEPT = ".pdf,.docx,.txt,.md";
const STATUS: Record<ClassDocument["status"], { label: string; tone: string }> = {
  processing: { label: "Đang xử lý", tone: "ea-chip--warn" },
  ready: { label: "Sẵn sàng", tone: "ea-chip--ok" },
  failed: { label: "Lỗi", tone: "ea-chip--danger" },
};

function size(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Class documents the agents may search; teachers upload, students only see the list. */
export function DocumentsTab({ room }: { room: ClassRoom }) {
  const documents = useResource(() => documentsApi.list(room.id), [room.id]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<ClassDocument | null>(null);
  const [removing, setRemoving] = useState<ClassDocument | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const teacher = room.my_role === "teacher";
  const processing = (documents.data ?? []).some((document) => document.status === "processing");

  // Parsing and embedding run in the background; poll until every document settles.
  useEffect(() => {
    if (!processing) return;
    const timer = window.setTimeout(documents.reload, 2000);
    return () => window.clearTimeout(timer);
  }, [processing, documents]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await documentsApi.upload(room.id, file, title.trim());
      setFile(null);
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      documents.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await documentsApi.remove(room.id, removing.id);
      setRemoving(null);
      documents.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ea-page">
      {teacher && (
        <form className="ea-card ea-form" onSubmit={upload}>
          <div className="ea-form__row">
            <label className="field">
              <span>Tệp (PDF, DOCX, TXT, MD; tối đa 15 MB)</span>
              <input ref={fileRef} type="file" accept={ACCEPT} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <label className="field">
              <span>Tiêu đề hiển thị (không bắt buộc)</span>
              <input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} placeholder="Chương 3 – Phương trình bậc nhất" />
            </label>
          </div>
          <p className="ea-muted">
            Agent chỉ dùng tài liệu để trả lời trong lớp này và coi nội dung là dữ liệu tham khảo: chỉ dẫn viết trong tài liệu sẽ bị bỏ qua.
          </p>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div><button className="button button--primary" type="submit" disabled={!file || busy}><Icon name="upload" /> Tải lên</button></div>
        </form>
      )}

      {documents.error && <div className="ea-error">{documents.error}</div>}
      {documents.data && documents.data.length === 0 && (
        <div className="ea-empty"><Icon name="file" /><p>Lớp chưa có tài liệu. {teacher ? "Tải giáo án, đề cương để agent trả lời đúng nội dung lớp." : ""}</p></div>
      )}
      {(documents.data ?? []).length > 0 && (
        <div className="ea-table-wrap">
          <table className="ea-table">
            <thead><tr><th>Tài liệu</th><th>Trạng thái</th><th>Đoạn</th><th>Ngày tải</th>{teacher && <th aria-label="Thao tác" />}</tr></thead>
            <tbody>
              {(documents.data ?? []).map((document) => (
                <tr key={document.id}>
                  <td><strong>{document.title}</strong><br /><span className="ea-muted">{document.filename} · {size(document.size_bytes)}</span></td>
                  <td>
                    <span className={`ea-chip ${STATUS[document.status].tone}`}>{STATUS[document.status].label}</span>
                    {document.error && <div className="ea-muted">{document.error}</div>}
                  </td>
                  <td>{document.chunk_count}</td>
                  <td>{new Date(document.created_at).toLocaleDateString("vi-VN")}</td>
                  {teacher && (
                    <td className="ea-row-actions">
                      {document.status === "ready" && <button className="button button--ghost" type="button" onClick={() => setViewing(document)}><Icon name="eye" /> Xem đoạn</button>}
                      {document.status === "failed" && (
                        <button className="button button--ghost" type="button" onClick={() => void documentsApi.reprocess(room.id, document.id).then(documents.reload)}>Xử lý lại</button>
                      )}
                      <button className="icon-button icon-button--danger" type="button" aria-label={`Xoá ${document.title}`} onClick={() => setRemoving(document)}><Icon name="trash" /></button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {viewing && <ChunksDialog room={room} document={viewing} onClose={() => setViewing(null)} />}
      <ConfirmDialog
        open={removing !== null}
        title={`Xoá “${removing?.title ?? ""}”?`}
        description="Agent sẽ không còn đọc được tài liệu này."
        confirmLabel="Xoá tài liệu"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}

function ChunksDialog({ room, document, onClose }: { room: ClassRoom; document: ClassDocument; onClose: () => void }) {
  const chunks = useResource(() => documentsApi.chunks(room.id, document.id), [room.id, document.id]);
  return (
    <Modal title={document.title} eyebrow="CÁC ĐOẠN AGENT ĐỌC ĐƯỢC" onClose={onClose} wide>
      {chunks.error && <div className="ea-error">{chunks.error}</div>}
      <ol className="ea-chunks">
        {(chunks.data ?? []).map((chunk) => (
          <li key={chunk.position}>
            {chunk.location && <span className="ea-chip">{chunk.location}</span>}
            <p>{chunk.content}</p>
          </li>
        ))}
      </ol>
    </Modal>
  );
}
