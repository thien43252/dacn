import { useState } from "react";

import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { familyApi, reportsApi } from "../../api-client/classes";
import type { ClassRoom } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { ReportView } from "./ReportView";

function PeriodSelect({ days, onChange }: { days: number; onChange: (days: number) => void }) {
  return (
    <label className="ea-inline-select">
      Khoảng
      <select value={days} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={7}>7 ngày</option>
        <option value={14}>14 ngày</option>
        <option value={30}>30 ngày</option>
      </select>
    </label>
  );
}

/** Parent: weekly learning report for one linked child. */
export function ParentReportsPage() {
  const children = useResource(() => familyApi.children(), []);
  const [chosen, setChosen] = useState("");
  const [days, setDays] = useState(7);
  const childId = chosen || children.data?.[0]?.id || "";
  const report = useResource(() => (childId ? reportsApi.child(childId, days) : Promise.resolve(null)), [childId, days]);

  if (children.data && children.data.length === 0) {
    return (
      <div className="ea-empty">
        <Icon name="team" />
        <p>Chưa liên kết với con. Nhập mã liên kết của con ở mục “Con của tôi”.</p>
        <button className="button button--primary" type="button" onClick={() => navigate("/parent/home")}>Liên kết với con</button>
      </div>
    );
  }
  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <div className="ea-toolbar__actions">
          {children.data && children.data.length > 1 && (
            <label className="ea-inline-select">
              Con
              <select value={childId} onChange={(event) => setChosen(event.target.value)}>
                {children.data.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}
              </select>
            </label>
          )}
          <PeriodSelect days={days} onChange={setDays} />
        </div>
        {report.data && <h3>{report.data.student_name}</h3>}
      </div>
      {(children.error || report.error) && <div className="ea-error">{children.error || report.error}</div>}
      {report.loading && !report.data && <p className="ea-muted">Đang tổng hợp báo cáo…</p>}
      {report.data && <ReportView report={report.data} audience="parent" />}
    </div>
  );
}

/** Teacher: per-student activity in one class, with a report per student. */
export function ClassProgressTab({ room }: { room: ClassRoom }) {
  const [days, setDays] = useState(7);
  const rows = useResource(() => reportsApi.classProgress(room.id, days), [room.id, days]);
  const [open, setOpen] = useState<string | null>(null);
  const report = useResource(() => (open ? reportsApi.student(room.id, open, days) : Promise.resolve(null)), [room.id, open, days]);

  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <p className="ea-muted">Số liệu tổng hợp theo học sinh trong lớp này; không hiển thị nguyên văn tin nhắn.</p>
        <PeriodSelect days={days} onChange={setDays} />
      </div>
      {rows.error && <div className="ea-error">{rows.error}</div>}
      {rows.data && (
        <div className="ea-table-wrap">
          <table className="ea-table">
            <thead><tr><th>Học sinh</th><th>Câu hỏi</th><th>Ngày có học</th><th>Agent dùng nhiều</th><th>Bị chặn</th><th>Cần quan tâm</th><th /></tr></thead>
            <tbody>
              {rows.data.map((row) => (
                <tr key={row.student_id} className={row.activity.wellbeing_alerts ? "ea-row--alert" : undefined}>
                  <td>{row.student_name}</td>
                  <td>{row.activity.questions_asked}</td>
                  <td>{row.activity.active_days}</td>
                  <td>{Object.keys(row.activity.agents_used)[0] ? `@${Object.keys(row.activity.agents_used)[0]}` : "–"}</td>
                  <td>{row.activity.blocked_messages}</td>
                  <td>{row.activity.wellbeing_alerts || "–"}</td>
                  <td><button className="button button--ghost" type="button" onClick={() => setOpen(row.student_id)}><Icon name="eye" /> Báo cáo</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && report.data && (
        <section className="ea-card ea-page">
          <div className="ea-toolbar">
            <h3>{report.data.student_name}</h3>
            <button className="icon-button" type="button" aria-label="Đóng báo cáo" onClick={() => setOpen(null)}><Icon name="x" /></button>
          </div>
          <ReportView report={report.data} audience="teacher" />
        </section>
      )}
    </div>
  );
}
