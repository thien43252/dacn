import { useState } from "react";

import { useResource } from "../../app/useResource";
import type { AuditFilters } from "../../api-client/agents";
import { type AgentRole, type AuditLog, categoryLabel, type GuardEvent, ROLE_LABELS } from "../../api-client/types";
import { Icon } from "../../components/Icon";

const STAGE_LABELS: Record<string, string> = { input: "Đầu vào", tool: "Công cụ", output: "Đầu ra" };
const VERDICT_LABELS: Record<string, string> = { block: "Đã chặn", support: "Hỗ trợ an toàn", redact: "Ẩn thông tin", flag: "Gắn cờ" };
const DETECTOR_LABELS: Record<string, string> = { rule: "Luật", policy: "Chính sách", llm: "Mô hình" };
const SOURCE_LABELS: Record<string, string> = { chat: "Lớp học", sandbox: "Phòng thử", certify: "Kiểm định" };

function verdictTone(event: GuardEvent): string {
  if (event.severity === "high") return "ea-chip--danger";
  if (event.verdict === "block") return "ea-chip--warn";
  return "";
}

export function formatTime(value: string): string {
  return new Date(value).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

interface AuditLogViewProps {
  load: (filters: AuditFilters) => Promise<AuditLog>;
  /** Changes when the log belongs to another class. */
  scope: string;
  showClass?: boolean;
  showSource?: boolean;
}

/** Guard events with a 30-day summary: what the platform stopped, changed or flagged, where and why. */
export function AuditLogView({ load, scope, showClass = false, showSource = false }: AuditLogViewProps) {
  const [stage, setStage] = useState("");
  const [verdict, setVerdict] = useState("");
  const [source, setSource] = useState("chat");
  const log = useResource(() => load({ stage, verdict, ...(showSource ? { source } : {}) }), [scope, stage, verdict, source]);
  const summary = log.data?.summary;

  return (
    <div className="ea-page">
      {summary && (
        <div className="ea-stats">
          <div className="ea-stat"><span>Sự kiện {summary.days} ngày</span><strong>{summary.total}</strong></div>
          <div className="ea-stat"><span>Đã chặn</span><strong>{summary.by_verdict.block ?? 0}</strong></div>
          <div className="ea-stat ea-stat--danger"><span>Cần quan tâm</span><strong>{summary.high_severity}</strong></div>
          <div className="ea-stat"><span>Ẩn thông tin cá nhân</span><strong>{summary.by_verdict.redact ?? 0}</strong></div>
        </div>
      )}
      {summary && Object.keys(summary.by_category).length > 0 && (
        <div className="ea-card__meta">
          {Object.entries(summary.by_category).sort((a, b) => b[1] - a[1]).map(([category, count]) => (
            <span key={category} className="ea-chip">{categoryLabel(category)} · {count}</span>
          ))}
        </div>
      )}

      <div className="ea-toolbar">
        <div className="ea-toolbar__actions">
          <label className="ea-inline-select">
            Giai đoạn
            <select value={stage} onChange={(event) => setStage(event.target.value)}>
              <option value="">Tất cả</option>
              {Object.entries(STAGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="ea-inline-select">
            Kết quả
            <select value={verdict} onChange={(event) => setVerdict(event.target.value)}>
              <option value="">Tất cả</option>
              {Object.entries(VERDICT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {showSource && (
            <label className="ea-inline-select">
              Nguồn
              <select value={source} onChange={(event) => setSource(event.target.value)}>
                {Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          )}
        </div>
        <button className="button button--ghost" type="button" onClick={log.reload}><Icon name="history" /> Tải lại</button>
      </div>

      {log.error && <div className="ea-error">{log.error}</div>}
      {log.data && log.data.events.length === 0 && (
        <div className="ea-empty"><Icon name="shield" /><p>Chưa có sự kiện nào. Khi lớp bảo vệ chặn, ẩn thông tin hay phát hiện dấu hiệu cần hỗ trợ, sự kiện sẽ hiện ở đây.</p></div>
      )}
      {log.data && log.data.events.length > 0 && (
        <div className="ea-table-wrap">
          <table className="ea-table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Người dùng</th>
                {showClass && <th>Lớp</th>}
                <th>Giai đoạn</th>
                <th>Kết quả</th>
                <th>Lý do và trích đoạn</th>
              </tr>
            </thead>
            <tbody>
              {log.data.events.map((event) => (
                <tr key={event.id} className={event.severity === "high" ? "ea-row--alert" : undefined}>
                  <td className="ea-nowrap">{formatTime(event.created_at)}</td>
                  <td>
                    {event.user_name ?? "Không rõ"}
                    <br /><span className="ea-muted">{ROLE_LABELS[event.role as AgentRole] ?? event.role}{event.agent_slug ? ` · @${event.agent_slug}` : ""}</span>
                  </td>
                  {showClass && <td>{event.class_name ?? (showSource ? SOURCE_LABELS[event.source] : "Ngoài lớp")}</td>}
                  <td>{STAGE_LABELS[event.stage] ?? event.stage}<br /><span className="ea-muted">{DETECTOR_LABELS[event.detector] ?? event.detector}</span></td>
                  <td>
                    <span className={`ea-chip ${verdictTone(event)}`}>{VERDICT_LABELS[event.verdict] ?? event.verdict}</span>
                    <br /><span className="ea-muted">{categoryLabel(event.category)}</span>
                  </td>
                  <td>
                    {event.reason}
                    {event.excerpt && <blockquote className="ea-excerpt">{event.excerpt}</blockquote>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
