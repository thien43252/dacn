import { useState } from "react";

import { useResource } from "../../app/useResource";
import { auditApi } from "../../api-client/agents";
import type { UsageRow } from "../../api-client/types";
import { AuditLogView } from "./AuditLogView";

const PURPOSE_LABELS: Record<string, string> = {
  agent: "Agent trả lời",
  router: "Định tuyến",
  input_guard: "Guard đầu vào",
  output_guard: "Guard đầu ra",
  tool: "Công cụ",
  embed: "Embedding tài liệu",
  certify: "Kiểm định: chạy agent",
  judge: "Kiểm định: giám khảo",
};

/** Teacher: guard events from every class they teach. */
export function TeacherAuditPage() {
  return (
    <div className="ea-page">
      <div className="ea-notice">
        Nhật ký ghi lại mỗi lần lớp bảo vệ chặn tin nhắn, ẩn thông tin cá nhân, từ chối một công cụ hoặc thu hồi câu trả lời.
        Dòng tô đỏ là dấu hiệu học sinh cần được quan tâm (ví dụ buồn chán, muốn tự làm hại); hãy trao đổi trực tiếp với em
        và phụ huynh. Trích đoạn đã được ẩn thông tin cá nhân.
      </div>
      <AuditLogView load={(filters) => auditApi.events(filters)} scope="teacher" showClass />
    </div>
  );
}

function money(value: number): string {
  return value < 0.01 && value > 0 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

function UsageTable({ rows, label, labels = {} }: { rows: UsageRow[]; label: string; labels?: Record<string, string> }) {
  return (
    <div className="ea-table-wrap">
      <table className="ea-table">
        <thead><tr><th>{label}</th><th>Lượt gọi</th><th>Token vào</th><th>Token ra</th><th>Chi phí</th><th>Độ trễ TB</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{labels[row.key] ?? row.key}</td>
              <td>{row.calls.toLocaleString("vi-VN")}</td>
              <td>{row.input_tokens.toLocaleString("vi-VN")}</td>
              <td>{row.output_tokens.toLocaleString("vi-VN")}</td>
              <td>{money(row.cost_usd)}</td>
              <td>{row.avg_latency_ms.toLocaleString("vi-VN")} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsagePanel() {
  const [days, setDays] = useState(7);
  const usage = useResource(() => auditApi.usage(days), [days]);
  const total = usage.data?.total;
  return (
    <section className="ea-card ea-page">
      <div className="ea-toolbar">
        <h3>Chi phí gọi mô hình</h3>
        <label className="ea-inline-select">
          Khoảng
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={1}>24 giờ</option>
            <option value={7}>7 ngày</option>
            <option value={30}>30 ngày</option>
          </select>
        </label>
      </div>
      {usage.error && <div className="ea-error">{usage.error}</div>}
      {total && (
        <div className="ea-stats">
          <div className="ea-stat"><span>Lượt gọi</span><strong>{total.calls.toLocaleString("vi-VN")}</strong></div>
          <div className="ea-stat"><span>Token</span><strong>{(total.input_tokens + total.output_tokens).toLocaleString("vi-VN")}</strong></div>
          <div className="ea-stat"><span>Chi phí</span><strong>{money(total.cost_usd)}</strong></div>
          <div className="ea-stat"><span>Độ trễ TB</span><strong>{total.avg_latency_ms.toLocaleString("vi-VN")} ms</strong></div>
        </div>
      )}
      {usage.data && usage.data.by_purpose.length > 0 && <UsageTable rows={usage.data.by_purpose} label="Mục đích" labels={PURPOSE_LABELS} />}
      {usage.data && usage.data.by_model.length > 0 && <UsageTable rows={usage.data.by_model} label="Mô hình" />}
      <p className="ea-muted">Chi phí chỉ tính cho mô hình có bảng giá (Anthropic); nhà cung cấp khác ghi token, chưa ghi tiền.</p>
    </section>
  );
}

/** Admin: model usage and cost, and guard events platform-wide. */
export function AdminAuditPage() {
  return (
    <div className="ea-page">
      <UsagePanel />
      <section className="ea-page">
        <h3>Sự kiện an toàn</h3>
        <AuditLogView load={(filters) => auditApi.events(filters)} scope="admin" showClass showSource />
      </section>
    </div>
  );
}
