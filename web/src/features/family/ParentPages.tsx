import { type FormEvent, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { familyApi } from "../../api-client/classes";
import { type Child, subjectLabel } from "../../api-client/types";
import { Icon } from "../../components/Icon";

function useChildren() {
  return useResource(() => familyApi.children(), []);
}

export function ParentHomePage() {
  const children = useChildren();
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function link(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      children.setData(await familyApi.linkChild(code));
      setCode("");
      setStatus({ kind: "ok", text: "Đã liên kết. Vào “Đồng ý & quyền riêng tư” để cho phép con dùng agent." });
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ea-page">
      <form className="ea-card ea-inline-form" onSubmit={link}>
        <label className="field">
          <span>Mã liên kết của con</span>
          <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder="Con xem mã trong mục “Lớp của tôi”" maxLength={12} autoComplete="off" />
        </label>
        <button className="button button--primary" type="submit" disabled={busy || code.trim().length < 4}>Liên kết với con</button>
        {status && <p className={status.kind === "ok" ? "ea-muted" : "form-error"} role="status" style={{ flexBasis: "100%" }}>{status.text}</p>}
      </form>

      {children.error && <div className="ea-error">{children.error}</div>}
      {children.data && children.data.length === 0 && (
        <div className="ea-empty"><Icon name="team" /><p>Chưa liên kết với con. Hỏi con mã liên kết rồi nhập ở trên.</p></div>
      )}

      <div className="ea-grid">
        {(children.data ?? []).map((child) => <ChildCard key={child.id} child={child} />)}
      </div>
    </div>
  );
}

function ChildCard({ child }: { child: Child }) {
  return (
    <article className="ea-card">
      <h3>{child.name}</h3>
      <span className="ea-muted">{child.email}</span>
      {child.consent.allow_agents
        ? <span className="ea-chip ea-chip--ok">Đã cho phép dùng agent</span>
        : <span className="ea-chip ea-chip--warn">Chưa cho phép dùng agent</span>}
      <strong>Lớp đang học</strong>
      {child.classes.length === 0 && <span className="ea-muted">Con chưa tham gia lớp nào.</span>}
      <ul className="ea-muted" style={{ margin: 0, paddingLeft: "1.2em" }}>
        {child.classes.map((room) => (
          <li key={room.id}>{room.name} · {subjectLabel(room.subject)} lớp {room.grade} · {room.teacher_name}</li>
        ))}
      </ul>
    </article>
  );
}

export function ParentConsentPage() {
  const children = useChildren();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function update(child: Child, patch: Partial<Child["consent"]>) {
    setSaving(child.id);
    setError("");
    try {
      const consent = await familyApi.setConsent(child.id, {
        allow_agents: patch.allow_agents ?? child.consent.allow_agents,
        allow_progress_reports: patch.allow_progress_reports ?? child.consent.allow_progress_reports,
      });
      children.setData((children.data ?? []).map((item) => (item.id === child.id ? { ...item, consent } : item)));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="ea-page">
      <div className="ea-notice">
        Theo quy định về bảo vệ dữ liệu cá nhân, việc xử lý dữ liệu của trẻ em cần sự đồng ý của cha mẹ. Bạn có thể thay đổi
        hoặc rút lại đồng ý bất cứ lúc nào; thay đổi có hiệu lực từ tin nhắn tiếp theo của con.
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {children.data && children.data.length === 0 && (
        <div className="ea-empty"><Icon name="lock" /><p>Liên kết với con ở trang “Con của tôi” trước.</p></div>
      )}
      {(children.data ?? []).map((child) => (
        <section key={child.id} className="ea-card" aria-busy={saving === child.id}>
          <h3>{child.name}</h3>
          <label className="ea-switch">
            <input type="checkbox" checked={child.consent.allow_agents} disabled={saving === child.id}
              onChange={(event) => void update(child, { allow_agents: event.target.checked })} />
            <span>
              <strong>Cho phép con dùng agent AI trong các lớp</strong><br />
              <small className="ea-muted">Agent đọc tin nhắn con gửi để trả lời. Mọi agent đều đi qua lớp kiểm duyệt an toàn.</small>
            </span>
          </label>
          <label className="ea-switch">
            <input type="checkbox" checked={child.consent.allow_progress_reports} disabled={saving === child.id}
              onChange={(event) => void update(child, { allow_progress_reports: event.target.checked })} />
            <span>
              <strong>Tổng hợp báo cáo học tập cho phụ huynh</strong><br />
              <small className="ea-muted">Bạn nhận bản tóm tắt chủ đề con đã học, không phải nguyên văn tin nhắn.</small>
            </span>
          </label>
          {child.consent.updated_at && (
            <span className="ea-muted">Cập nhật lần cuối: {new Date(child.consent.updated_at).toLocaleString("vi-VN")}</span>
          )}
        </section>
      ))}
    </div>
  );
}
