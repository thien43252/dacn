import { type FormEvent, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { classesApi, familyApi } from "../../api-client/classes";
import { subjectLabel } from "../../api-client/types";
import { Icon } from "../../components/Icon";

export function StudentClassesPage() {
  const classes = useResource(() => classesApi.list(), []);
  const linkCode = useResource(() => familyApi.myLinkCode(), []);
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function join(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus(null);
    try {
      const room = await classesApi.join(code);
      setCode("");
      setStatus({ kind: "ok", text: `Đã tham gia lớp ${room.name}.` });
      classes.reload();
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ea-page">
      <form className="ea-card ea-inline-form" onSubmit={join}>
        <label className="field">
          <span>Mã lớp giáo viên gửi</span>
          <input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} placeholder="VD: 7KQ2PX" maxLength={12} autoComplete="off" />
        </label>
        <button className="button button--primary" type="submit" disabled={busy || code.trim().length < 4}>Tham gia lớp</button>
        {status && <p className={status.kind === "ok" ? "ea-muted" : "form-error"} role="status" style={{ flexBasis: "100%" }}>{status.text}</p>}
      </form>

      {classes.error && <div className="ea-error">{classes.error}</div>}
      {classes.data && classes.data.length === 0 && (
        <div className="ea-empty"><Icon name="school" /><p>Bạn chưa tham gia lớp nào. Nhập mã lớp ở trên để bắt đầu.</p></div>
      )}
      <div className="ea-grid">
        {(classes.data ?? []).map((room) => (
          <article key={room.id} className="ea-card">
            <div className="ea-card__meta"><span className="ea-chip">{subjectLabel(room.subject)}</span><span>Lớp {room.grade}</span></div>
            <h3>{room.name}</h3>
            <span className="ea-muted">Giáo viên: {room.teacher_name}</span>
          </article>
        ))}
      </div>

      <section className="ea-card">
        <h3>Mã liên kết cho phụ huynh</h3>
        <p className="ea-muted">
          Đưa mã này cho bố mẹ. Phụ huynh nhập mã trong tài khoản của mình để theo dõi việc học và quyết định cho phép bạn dùng agent.
        </p>
        {linkCode.data && <span className="ea-code">{linkCode.data.code}</span>}
        {linkCode.data && linkCode.data.parents.length > 0 && (
          <p className="ea-muted">Đã liên kết: {linkCode.data.parents.map((parent) => parent.name).join(", ")}</p>
        )}
        {linkCode.error && <div className="ea-error">{linkCode.error}</div>}
      </section>
    </div>
  );
}
