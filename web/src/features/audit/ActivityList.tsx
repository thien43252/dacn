import type { ActivityRow } from "../../api-client/types";
import { Icon } from "../../components/Icon";

const TYPE_LABELS: Record<ActivityRow["type"], string> = {
  handoff: "Giao việc",
  person_request: "Hỏi người",
  approval: "Duyệt hành động",
  tool: "Công cụ",
};

const STATUS_LABELS: Record<string, string> = {
  queued: "Đang chờ",
  running: "Đang chạy",
  answered: "Đã trả lời",
  no_answer: "Không nhận được câu trả lời",
  refused: "Bị từ chối",
  hidden: "Nội dung đã được ẩn",
  late: "Về muộn",
  failed: "Lỗi",
  draft: "Chờ duyệt",
  open: "Đang chờ trả lời",
  expired: "Hết hạn",
  cancelled: "Đã huỷ",
  undeliverable: "Không đến được ai",
  allowed: "Đã cho phép",
  denied: "Đã từ chối",
  done: "Xong",
  error: "Lỗi",
};

/** Why a handoff was refused (refusal_reason in backend app/orchestration/handoffs.py). */
const REASON_LABELS: Record<string, string> = {
  not_granted: "Chưa được cấp quyền giao việc",
  unknown_or_hidden: "Agent không tồn tại hoặc không được thấy",
  disabled: "Giao việc đang tắt",
  loop: "Vòng lặp giao việc",
  depth_cap: "Vượt giới hạn số tầng",
  per_run_cap: "Vượt giới hạn số lần giao việc của lượt",
};

const ANSWER_LABELS: Record<string, string> = {
  once: "Cho phép lần này",
  conversation: "Cho phép trong hội thoại này",
  always: "Luôn cho phép ở đây",
  deny: "Từ chối",
  did_it: "Tôi đã tự làm",
  dont: "Đừng làm",
};

function tone(status: string): string {
  if (["refused", "failed", "error", "denied", "undeliverable", "no_answer"].includes(status)) return "ea-chip--warn";
  return "";
}

function what(row: ActivityRow): string {
  if (row.type === "handoff") return `@${row.from_agent} hỏi @${row.to_agent}${row.depth && row.depth > 1 ? ` (tầng ${row.depth})` : ""}`;
  if (row.type === "person_request") return `${row.agent ? `@${row.agent} ` : ""}hỏi người${row.kind ? ` · ${row.kind}` : ""}`;
  if (row.type === "approval") return `${row.agent ? `@${row.agent} · ` : ""}${row.tool ?? row.action_kind ?? "hành động"}`;
  return row.tool ?? "";
}

function detail(row: ActivityRow): string {
  const parts: string[] = [];
  if (row.reason) parts.push(REASON_LABELS[row.reason] ?? row.reason);
  if (row.type === "approval" && row.answer) parts.push(`Lựa chọn trên thẻ: ${ANSWER_LABELS[row.answer] ?? row.answer}`);
  if (row.type === "approval" && row.decided_by === "rule" && !row.reason) parts.push("Do quy tắc quyết định");
  if (row.attempts && row.attempts > 1) parts.push(`Thử ${row.attempts} lần`);
  if (row.task) parts.push(row.task);
  if (row.body) parts.push(row.body);
  return parts.join(" · ");
}

export function formatActivityTime(value: string): string {
  return new Date(value).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

/** Handoffs, questions to people, approval decisions and tool runs, each with its result and what stopped it. */
export function ActivityList({ rows, empty }: { rows: ActivityRow[]; empty: string }) {
  if (rows.length === 0) {
    return <div className="ea-empty"><Icon name="history" /><p>{empty}</p></div>;
  }
  return (
    <div className="ea-table-wrap">
      <table className="ea-table">
        <thead>
          <tr><th>Thời gian</th><th>Loại</th><th>Việc</th><th>Kết quả</th><th>Chi tiết</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.type}-${row.id}`}>
              <td className="ea-nowrap">{formatActivityTime(row.at)}</td>
              <td>{TYPE_LABELS[row.type] ?? row.type}</td>
              <td>{what(row)}</td>
              <td><span className={`ea-chip ${tone(row.status)}`}>{STATUS_LABELS[row.status] ?? row.status}</span></td>
              <td>{detail(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
