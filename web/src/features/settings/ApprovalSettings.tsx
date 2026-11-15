import { useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { approvalsApi } from "../../api-client/chat";
import type { ApprovalRule } from "../../api-client/types";
import "../chat/messenger.css";

const KIND_LABELS: Record<string, string> = {
  send: "Gửi cho người khác",
  share: "Chia sẻ",
  post: "Đăng, công bố",
  delete: "Xoá",
  settings: "Đổi cài đặt chia sẻ, quyền",
  money: "Việc liên quan tiền",
  change: "Thay đổi khác",
};

function describe(rule: ApprovalRule): string {
  return [KIND_LABELS[rule.action_kind] ?? rule.action_kind, rule.agent_slug && `agent ${rule.agent_slug}`, rule.tool && `công cụ ${rule.tool}`]
    .filter(Boolean)
    .join(" · ");
}

/** Cài đặt duyệt (FR-032, FR-033): the "extra vigilant" switch and the allowances saved from cards. */
export function ApprovalSettingsPage() {
  const settings = useResource(() => approvalsApi.settings(), []);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      settings.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  if (settings.error) return <p className="form-error">{settings.error}</p>;
  if (!settings.data) return <p className="ea-muted">Đang tải…</p>;
  const data = settings.data;
  return (
    <div className="ea-card ea-form">
      <label className="ea-switch">
        <input type="checkbox" checked={data.extra_vigilant} onChange={(event) => void run(() => approvalsApi.setVigilant(event.target.checked))} />
        <span>
          <strong>Cực kỳ cẩn thận</strong><br />
          <small className="ea-muted">Hỏi bạn trước mọi thay đổi. Gửi, chia sẻ, đăng, xoá luôn hỏi dù tắt công tắc này.</small>
        </span>
      </label>
      <section>
        <h3>Luôn cho phép ở đây</h3>
        {data.rules.length === 0 ? <p className="ea-muted">Chưa có quy tắc nào.</p> : (
          <ul className="ea-rule-list">
            {data.rules.map((rule) => (
              <li key={rule.id}>
                <span>{describe(rule)}</span>
                <button type="button" className="button button--ghost" onClick={() => void run(() => approvalsApi.removeRule(rule.id))}>Xoá</button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h3>Cho phép trong hội thoại</h3>
        {data.conversation_allowances.length === 0 ? <p className="ea-muted">Chưa có cho phép nào.</p> : (
          <ul className="ea-rule-list">
            {data.conversation_allowances.map((rule) => (
              <li key={rule.id}>
                <span>{describe(rule)}</span>
                <button type="button" className="button button--ghost" onClick={() => void run(() => approvalsApi.removeRule(rule.id))}>Tắt</button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
