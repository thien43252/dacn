import { type FormEvent, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { feedApi } from "../../api-client/classes";
import type { AnnouncementAudience, ClassRoom } from "../../api-client/types";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { AnnouncementItem, AssignmentItem, AUDIENCE_LABELS } from "./ClassFeed";

type Removal = { kind: "announcement" | "assignment"; id: string; title: string };

/**
 * "Bảng tin": the class's announcements and practice sets. Teachers post announcements here or through an agent
 * after confirming; practice sets come only from the assign_practice tool. Everything can be removed again (FR-050).
 */
export function ClassFeedTab({ room }: { room: ClassRoom }) {
  const announcements = useResource(() => feedApi.announcements(room.id), [room.id]);
  const assignments = useResource(() => feedApi.assignments(room.id), [room.id]);
  const [form, setForm] = useState({ title: "", body: "", audience: "students" as AnnouncementAudience });
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<Removal | null>(null);

  async function post(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      const created = await feedApi.postAnnouncement(room.id, form);
      announcements.setData([created, ...(announcements.data ?? [])]);
      setForm({ ...form, title: "", body: "" });
      setStatus({ kind: "ok", text: "Đã đăng thông báo." });
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      if (removing.kind === "announcement") {
        await feedApi.deleteAnnouncement(room.id, removing.id);
        announcements.setData((announcements.data ?? []).filter((item) => item.id !== removing.id));
      } else {
        await feedApi.deleteAssignment(room.id, removing.id);
        assignments.setData((assignments.data ?? []).filter((item) => item.id !== removing.id));
      }
      setRemoving(null);
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
      setRemoving(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ea-feed-tab">
      <form className="ea-card ea-form" onSubmit={post}>
        <h3>Đăng thông báo</h3>
        <label className="field">
          <span>Tiêu đề</span>
          <input value={form.title} maxLength={120} onChange={(event) => setForm({ ...form, title: event.target.value })} />
        </label>
        <label className="field">
          <span>Nội dung</span>
          <textarea rows={3} maxLength={2000} value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} />
        </label>
        <label className="field">
          <span>Gửi tới</span>
          <select value={form.audience} onChange={(event) => setForm({ ...form, audience: event.target.value as AnnouncementAudience })}>
            {(Object.keys(AUDIENCE_LABELS) as AnnouncementAudience[]).map((key) => <option key={key} value={key}>{AUDIENCE_LABELS[key]}</option>)}
          </select>
        </label>
        {status && <div className={status.kind === "ok" ? "ea-notice" : "form-error"} role="status">{status.text}</div>}
        <div>
          <button className="button button--primary" type="submit" disabled={busy || form.title.trim().length < 3 || form.body.trim().length < 10}>Đăng</button>
        </div>
      </form>

      <section className="ea-card">
        <h3>Thông báo</h3>
        {announcements.error && <div className="ea-error">{announcements.error}</div>}
        {announcements.data?.length === 0 && <p className="ea-muted">Chưa có thông báo nào.</p>}
        <ul className="ea-feed__list">
          {(announcements.data ?? []).map((item) => (
            <AnnouncementItem key={item.id} item={item} onDelete={() => setRemoving({ kind: "announcement", id: item.id, title: item.title })} />
          ))}
        </ul>
      </section>

      <section className="ea-card">
        <h3>Bài luyện đã giao</h3>
        <p className="ea-muted">Nhờ agent “giao bài luyện cho cả lớp” trong khung chat; bài chỉ được giao sau khi bạn bấm “Đồng ý”.</p>
        {assignments.error && <div className="ea-error">{assignments.error}</div>}
        {assignments.data?.length === 0 && <p className="ea-muted">Chưa có bài luyện nào.</p>}
        <ul className="ea-feed__list">
          {(assignments.data ?? []).map((item) => (
            <AssignmentItem key={item.id} item={item} showAnswers onDelete={() => setRemoving({ kind: "assignment", id: item.id, title: item.title })} />
          ))}
        </ul>
      </section>

      <ConfirmDialog
        open={removing !== null}
        title={removing?.kind === "assignment" ? "Xoá bài luyện?" : "Xoá thông báo?"}
        description={removing ? `“${removing.title}” sẽ không còn hiện với học sinh và phụ huynh.` : undefined}
        confirmLabel="Xoá"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
