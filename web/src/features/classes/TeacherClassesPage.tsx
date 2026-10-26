import { useState } from "react";

import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { classesApi } from "../../api-client/classes";
import { subjectLabel } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { ClassFormDialog } from "./ClassForm";

export function TeacherClassesPage() {
  const classes = useResource(() => classesApi.list(), []);
  const [creating, setCreating] = useState(false);
  const active = (classes.data ?? []).filter((room) => !room.archived);
  const archived = (classes.data ?? []).filter((room) => room.archived);

  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <h2>{active.length} lớp đang dạy</h2>
        <button className="button button--primary" type="button" onClick={() => setCreating(true)}>
          <Icon name="plus" /> Tạo lớp
        </button>
      </div>

      {classes.error && <div className="ea-error" role="alert">{classes.error}</div>}
      {classes.loading && !classes.data && <p className="ea-muted">Đang tải danh sách lớp…</p>}

      {classes.data && active.length === 0 && (
        <div className="ea-empty">
          <Icon name="school" />
          <p>Bạn chưa có lớp nào. Tạo lớp đầu tiên rồi gửi mã lớp cho học sinh.</p>
          <button className="button button--primary" type="button" onClick={() => setCreating(true)}>Tạo lớp</button>
        </div>
      )}

      <div className="ea-grid">
        {active.map((room) => (
          <button key={room.id} type="button" className="ea-card ea-card--interactive" onClick={() => navigate(`/teacher/classes/${room.id}`)}>
            <div className="ea-card__meta">
              <span className="ea-chip">{subjectLabel(room.subject)}</span>
              <span>Lớp {room.grade}</span>
            </div>
            <h3>{room.name}</h3>
            {room.description && <p className="ea-muted">{room.description}</p>}
            <div className="ea-card__foot">
              <span className="ea-muted"><Icon name="team" /> {room.student_count} học sinh</span>
              {room.join_code && <code className="ea-chip">Mã {room.join_code}</code>}
            </div>
          </button>
        ))}
      </div>

      {archived.length > 0 && (
        <details>
          <summary className="ea-muted">{archived.length} lớp đã lưu trữ</summary>
          <div className="ea-grid" style={{ marginTop: "var(--space-4)" }}>
            {archived.map((room) => (
              <button key={room.id} type="button" className="ea-card ea-card--interactive" onClick={() => navigate(`/teacher/classes/${room.id}`)}>
                <h3>{room.name}</h3>
                <span className="ea-muted">Đã lưu trữ</span>
              </button>
            ))}
          </div>
        </details>
      )}

      {creating && (
        <ClassFormDialog
          onClose={() => setCreating(false)}
          onSubmit={async (input) => {
            const room = await classesApi.create(input);
            setCreating(false);
            navigate(`/teacher/classes/${room.id}`);
          }}
        />
      )}
    </div>
  );
}
