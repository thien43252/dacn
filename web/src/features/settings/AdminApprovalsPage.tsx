import { useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { adminApprovalsApi } from "../../api-client/agents";
import type { ApprovalModeRow } from "../../api-client/types";
import { ActivityList } from "../audit/ActivityList";

const KIND_LABELS: Record<string, string> = {
  send: "Gửi cho người khác",
  share: "Chia sẻ",
  post: "Đăng, công bố",
  delete: "Xoá",
  settings: "Đổi cài đặt chia sẻ, quyền",
  money: "Việc liên quan tiền",
  change: "Thay đổi khác",
};
const ROLE_LABELS: Record<ApprovalModeRow["role"], string> = { student: "Học sinh", teacher: "Giáo viên", parent: "Phụ huynh" };
const MODE_LABELS: Record<ApprovalModeRow["mode"], string> = {
  members_choose: "Người dùng tự chọn",
  ask_every_time: "Hỏi mỗi lần",
  do_it_yourself: "Người dùng tự làm",
};
const ROLES: ApprovalModeRow["role"][] = ["student", "teacher", "parent"];

/** Admin (FR-035, FR-034, FR-057): approval modes per action kind and role, admin rules (deny or ask only for kinds
 * that always ask), and the platform's approval decisions without conversation text. */
export function AdminApprovalsPage() {
  const modes = useResource(() => adminApprovalsApi.modes(), []);
  const rules = useResource(() => adminApprovalsApi.rules(), []);
  const activity = useResource(() => adminApprovalsApi.activity(), []);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState("send");
  const [effect, setEffect] = useState<"deny" | "ask">("deny");
  const [agent, setAgent] = useState("");

  async function run(action: () => Promise<unknown>, reload: () => void) {
    setError(null);
    try {
      await action();
      reload();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  const kinds = [...new Set((modes.data ?? []).map((row) => row.action_kind))];
  const modeOf = (actionKind: string, role: ApprovalModeRow["role"]) =>
    modes.data?.find((row) => row.action_kind === actionKind && row.role === role)?.mode ?? "members_choose";

  return (
    <div className="ea-page">
      {error && <div className="ea-error">{error}</div>}
      <section className="ea-card ea-page">
        <h3>Chế độ duyệt theo loại hành động</h3>
        <p className="ea-muted">
          "Hỏi mỗi lần": thẻ chỉ có Cho phép lần này và Từ chối. "Người dùng tự làm": agent không bao giờ làm, thẻ chỉ có Tôi
          đã tự làm và Đừng làm.
        </p>
        {modes.error && <div className="ea-error">{modes.error}</div>}
        {modes.data && (
          <div className="ea-table-wrap">
            <table className="ea-table">
              <thead><tr><th>Loại hành động</th>{ROLES.map((role) => <th key={role}>{ROLE_LABELS[role]}</th>)}</tr></thead>
              <tbody>
                {kinds.map((actionKind) => (
                  <tr key={actionKind}>
                    <td>{KIND_LABELS[actionKind] ?? actionKind}</td>
                    {ROLES.map((role) => (
                      <td key={role}>
                        <select
                          aria-label={`${KIND_LABELS[actionKind] ?? actionKind} – ${ROLE_LABELS[role]}`}
                          value={modeOf(actionKind, role)}
                          onChange={(event) =>
                            void run(
                              () => adminApprovalsApi.setMode({ action_kind: actionKind, role, mode: event.target.value as ApprovalModeRow["mode"] }),
                              modes.reload,
                            )
                          }
                        >
                          {Object.entries(MODE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ea-card ea-page">
        <h3>Quy tắc của admin</h3>
        <p className="ea-muted">Quy tắc của admin chỉ làm chặt hơn: chặn hoặc bắt hỏi. Chỉ câu trả lời trên thẻ mới mở được loại luôn phải hỏi.</p>
        <div className="ea-toolbar__actions">
          <label className="ea-inline-select">
            Loại
            <select value={kind} onChange={(event) => setKind(event.target.value)}>
              {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="ea-inline-select">
            Kết quả
            <select value={effect} onChange={(event) => setEffect(event.target.value as "deny" | "ask")}>
              <option value="deny">Chặn</option>
              <option value="ask">Luôn hỏi</option>
            </select>
          </label>
          <label className="ea-inline-select">
            Agent (tuỳ chọn)
            <input value={agent} placeholder="slug, để trống là mọi agent" onChange={(event) => setAgent(event.target.value.trim())} />
          </label>
          <button
            type="button"
            className="button button--primary"
            onClick={() => void run(() => adminApprovalsApi.addRule({ action_kind: kind, effect, agent_slug: agent || null }), rules.reload)}
          >
            Thêm quy tắc
          </button>
        </div>
        {rules.error && <div className="ea-error">{rules.error}</div>}
        {rules.data && rules.data.length === 0 && <p className="ea-muted">Chưa có quy tắc nào.</p>}
        {rules.data && rules.data.length > 0 && (
          <ul className="ea-rule-list">
            {rules.data.map((rule) => (
              <li key={rule.id}>
                <span>
                  {rule.effect === "deny" ? "Chặn" : rule.effect === "ask" ? "Luôn hỏi" : rule.effect} · {KIND_LABELS[rule.action_kind] ?? rule.action_kind}
                  {rule.agent_slug ? ` · @${rule.agent_slug}` : ""}
                  {rule.tool ? ` · ${rule.tool}` : ""}
                </span>
                <button type="button" className="button button--ghost" onClick={() => void run(() => adminApprovalsApi.removeRule(rule.id), rules.reload)}>Xoá</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="ea-card ea-page">
        <h3>Đã cho phép, bị từ chối và bị lỗi</h3>
        <p className="ea-muted">Toàn hệ thống, không kèm nội dung trò chuyện.</p>
        {activity.error && <div className="ea-error">{activity.error}</div>}
        {activity.data && <ActivityList rows={activity.data} empty="Chưa có hoạt động nào." />}
      </section>
    </div>
  );
}
