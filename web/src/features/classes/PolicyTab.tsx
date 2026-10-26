import { type FormEvent, useEffect, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { classesApi } from "../../api-client/classes";
import type { ClassPolicy, ClassRoom } from "../../api-client/types";

function toList(text: string): string[] {
  return text.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
}

/** Class rules applied to every agent in the class; the runtime and output guard enforce them (week 7–8). */
export function PolicyTab({ room }: { room: ClassRoom }) {
  const policy = useResource(() => classesApi.policy(room.id), [room.id]);
  const [form, setForm] = useState<ClassPolicy | null>(null);
  const [topics, setTopics] = useState("");
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (policy.data) {
      setForm(policy.data);
      setTopics(policy.data.blocked_topics.join(", "));
    }
  }, [policy.data]);

  if (policy.error) return <div className="ea-error">{policy.error}</div>;
  if (!form) return <p className="ea-muted">Đang tải chính sách…</p>;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    setStatus(null);
    try {
      const saved = await classesApi.savePolicy(room.id, { ...form, blocked_topics: toList(topics) });
      policy.setData(saved);
      setStatus({ kind: "ok", text: "Đã lưu. Chính sách áp dụng cho mọi agent trong lớp từ tin nhắn tiếp theo." });
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="ea-card ea-form" onSubmit={save}>
      <label className="ea-switch">
        <input type="checkbox" checked={form.no_direct_answers} onChange={(event) => setForm({ ...form, no_direct_answers: event.target.checked })} />
        <span>
          <strong>Không đưa đáp án trực tiếp cho học sinh</strong><br />
          <small className="ea-muted">Agent chỉ gợi ý từng bước và kiểm tra bài học sinh tự làm.</small>
        </span>
      </label>
      <label className="ea-switch">
        <input type="checkbox" checked={form.allow_personal_agents} onChange={(event) => setForm({ ...form, allow_personal_agents: event.target.checked })} />
        <span>
          <strong>Cho phép học sinh dùng agent cá nhân trong lớp</strong><br />
          <small className="ea-muted">Agent học sinh tự kéo từ Hub (đã kiểm định) vẫn chịu chính sách này.</small>
        </span>
      </label>
      <label className="field">
        <span>Chủ đề không thảo luận trong lớp</span>
        <textarea rows={2} value={topics} onChange={(event) => setTopics(event.target.value)} placeholder="Ví dụ: game, thần tượng, chính trị" />
        <small className="field__hint">Ngăn cách bằng dấu phẩy.</small>
      </label>
      <label className="field">
        <span>Ghi chú cho agent</span>
        <textarea rows={3} maxLength={1000} value={form.notes_for_agents} onChange={(event) => setForm({ ...form, notes_for_agents: event.target.value })}
          placeholder="Ví dụ: Xưng “cô”, gọi học sinh là “em”. Ưu tiên ví dụ gần gũi với nông thôn." />
      </label>
      {status && <div className={status.kind === "ok" ? "ea-notice" : "form-error"} role="status">{status.text}</div>}
      <div><button className="button button--primary" type="submit" disabled={busy}>Lưu chính sách</button></div>
    </form>
  );
}
