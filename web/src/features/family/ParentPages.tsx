import { type FormEvent, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { familyApi } from "../../api-client/classes";
import { type Child, subjectLabel } from "../../api-client/types";
import { type MyGrades, type TodoItem, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
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

      <div style={{ display: "grid", gap: "var(--space-4)" }}>
        {(children.data ?? []).map((child) => <ChildCard key={child.id} child={child} />)}
      </div>
    </div>
  );
}

function ChildCard({ child }: { child: Child }) {
  const [activeTab, setActiveTab] = useState<"classes" | "todo" | "grades">("classes");

  return (
    <article className="ea-card" style={{ display: "grid", gap: "var(--space-3)" }}>
      <div className="ea-toolbar">
        <div>
          <h3>{child.name}</h3>
          <span className="ea-muted">{child.email}</span>
        </div>
        <div>
          {child.consent.allow_agents ? (
            <span className="ea-chip ea-chip--ok">Đã cho phép dùng agent</span>
          ) : (
            <span className="ea-chip ea-chip--warn">Chưa cho phép dùng agent</span>
          )}
        </div>
      </div>

      {/* Child Tabs */}
      <div className="ea-subtabs" style={{ display: "flex", gap: "var(--space-2)", borderBottom: "1px solid var(--line)", paddingBottom: "var(--space-2)" }}>
        <button
          type="button"
          className={`button ${activeTab === "classes" ? "button--primary" : "button--ghost"}`}
          style={{ fontSize: "0.85rem", padding: "4px 10px" }}
          onClick={() => setActiveTab("classes")}
        >
          Lớp đang học ({child.classes.length})
        </button>
        <button
          type="button"
          className={`button ${activeTab === "todo" ? "button--primary" : "button--ghost"}`}
          style={{ fontSize: "0.85rem", padding: "4px 10px" }}
          onClick={() => setActiveTab("todo")}
        >
          Việc cần làm của con
        </button>
        <button
          type="button"
          className={`button ${activeTab === "grades" ? "button--primary" : "button--ghost"}`}
          style={{ fontSize: "0.85rem", padding: "4px 10px" }}
          onClick={() => setActiveTab("grades")}
        >
          Điểm đã trả
        </button>
      </div>

      {activeTab === "classes" && (
        <div>
          {child.classes.length === 0 ? (
            <p className="ea-muted">Con chưa tham gia lớp nào.</p>
          ) : (
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              {child.classes.map((room) => (
                <div
                  key={room.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div>
                    <strong>{room.name}</strong> · {subjectLabel(room.subject)} lớp {room.grade} · GV: {room.teacher_name}
                  </div>
                  <button
                    type="button"
                    className="button button--secondary"
                    style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                    onClick={() => navigate(`/parent/classes/${room.id}?student_id=${encodeURIComponent(child.id)}`)}
                  >
                    Xem buổi học
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "todo" && <ChildTodoList childId={child.id} />}
      {activeTab === "grades" && <ChildGradesList child={child} />}
    </article>
  );
}

function ChildTodoList({ childId }: { childId: string }) {
  const todoResource = useResource(() => lmsApi.todo.list(childId), [childId]);
  const items: TodoItem[] = todoResource.data ?? [];

  if (todoResource.loading && !todoResource.data) {
    return <p className="ea-muted">Đang tải việc cần làm của con…</p>;
  }

  if (todoResource.error) {
    return <div className="ea-error">{todoResource.error}</div>;
  }

  if (items.length === 0) {
    return <p className="ea-muted">Con đã hoàn thành tất cả nhiệm vụ học tập.</p>;
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-2)" }}>
      {items.map((item) => {
        const due = item.due_at ? new Date(item.due_at) : null;
        const isOverdue = due ? new Date() > due : false;
        const path =
          item.kind === "quiz"
            ? `/parent/classes/${item.class_id}/quizzes/${item.item_id}`
            : `/parent/classes/${item.class_id}/assignments/${item.item_id}`;

        return (
          <div
            key={item.item_id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "8px 12px",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius-sm)",
              borderLeft: isOverdue ? "4px solid var(--danger, #ef4444)" : "4px solid var(--primary)",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span className="ea-chip" style={{ fontSize: "0.75rem" }}>
                  {item.kind === "quiz" ? "Quiz" : "Bài tập"}
                </span>
                <span className="ea-muted" style={{ fontSize: "0.8rem" }}>{item.class_name}</span>
              </div>
              <strong style={{ fontSize: "0.95rem" }}>{item.title}</strong>
              <div style={{ fontSize: "0.8rem", color: isOverdue ? "var(--danger)" : "var(--muted)" }}>
                {due ? `Hạn nộp: ${due.toLocaleString("vi-VN")}${isOverdue ? " (Quá hạn)" : ""}` : "Không có hạn nộp"}
              </div>
            </div>

            <button
              type="button"
              className="button button--secondary"
              style={{ fontSize: "0.8rem", padding: "4px 8px" }}
              onClick={() => navigate(`${path}?student_id=${encodeURIComponent(childId)}`)}
            >
              Xem chi tiết
            </button>
          </div>
        );
      })}
    </div>
  );
}

function ChildGradesList({ child }: { child: Child }) {
  if (child.classes.length === 0) {
    return <p className="ea-muted">Con chưa tham gia lớp nào.</p>;
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      {child.classes.map((room) => (
        <ChildClassGradeSection key={room.id} classId={room.id} className={room.name} childId={child.id} />
      ))}
    </div>
  );
}

function ChildClassGradeSection({
  classId,
  className,
  childId,
}: {
  classId: string;
  className: string;
  childId: string;
}) {
  const gradesResource = useResource(() => lmsApi.myGrades.get(classId, childId), [classId, childId]);
  const data: MyGrades | null = gradesResource.data;

  if (gradesResource.loading && !data) {
    return <p className="ea-muted">Đang tải điểm lớp {className}…</p>;
  }

  if (gradesResource.error) return <div className="ea-error">{gradesResource.error}</div>;

  if (!data || data.items.length === 0) {
    return (
      <div style={{ padding: "8px 12px", border: "1px dashed var(--line)", borderRadius: "var(--radius-sm)" }}>
        <strong>{className}:</strong> <span className="ea-muted">Chưa có bài nào được trả điểm.</span>
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 12px", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <strong>{className}</strong>
        {data.overall_average !== null && data.overall_average !== undefined && (
          <span style={{ fontWeight: 700, color: "var(--primary)" }}>
            Trung bình: {Number(data.overall_average).toFixed(1)} / 10
          </span>
        )}
      </div>

      <div style={{ display: "grid", gap: "4px" }}>
        {data.items.map((it) => {
          const path =
            it.kind === "quiz"
              ? `/parent/classes/${classId}/quizzes/${it.item_id}`
              : `/parent/classes/${classId}/assignments/${it.item_id}`;

          return (
            <div
              key={it.item_id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: "0.85rem",
                padding: "4px 0",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <span>
                <span className="ea-chip" style={{ fontSize: "0.7rem", marginRight: "6px" }}>
                  {it.kind === "quiz" ? "Quiz" : "Bài tập"}
                </span>
                {it.title}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <strong style={{ color: "var(--primary)" }}>
                  {it.score !== null && it.score !== undefined ? `${it.score}/${it.max_points}đ` : "—"}
                </strong>
                <button
                  type="button"
                  className="button button--ghost"
                  style={{ fontSize: "0.75rem", padding: "2px 6px" }}
                  onClick={() => navigate(`${path}?student_id=${encodeURIComponent(childId)}`)}
                >
                  Xem bài
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
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
      {error && <div className="ea-error">{error}</div>}
      <div className="ea-grid">
        {(children.data ?? []).map((child) => (
          <article className="ea-card" key={child.id}>
            <h3>{child.name}</h3>
            <span className="ea-muted">{child.email}</span>
            <label className="field-checkbox">
              <input
                type="checkbox"
                checked={child.consent.allow_agents}
                disabled={saving === child.id}
                onChange={(event) => void update(child, { allow_agents: event.target.checked })}
              />
              <span>Cho phép con dùng agent trong lớp và chat</span>
            </label>
            <label className="field-checkbox">
              <input
                type="checkbox"
                checked={child.consent.allow_progress_reports}
                disabled={saving === child.id}
                onChange={(event) => void update(child, { allow_progress_reports: event.target.checked })}
              />
              <span>Nhận báo cáo học tập định kỳ của con</span>
            </label>
          </article>
        ))}
      </div>
    </div>
  );
}
