import { useState } from "react";

import { Modal } from "../../agents/Modal";
import { errorMessage, useResource } from "../../app/useResource";
import { certifyApi } from "../../api-client/agents";
import { type CategoryTally, categoryLabel, type CertificationCase, type CertificationRunStatus, ROLE_LABELS } from "../../api-client/types";
import { Icon } from "../../components/Icon";

const RUN_LABELS: Record<CertificationRunStatus, string> = {
  running: "Đang kiểm định",
  certified: "Đã kiểm định",
  needs_review: "Cần xem lại",
  rejected: "Không đạt",
  failed: "Lỗi khi chạy",
};
const EXPECTED_LABELS: Record<string, string> = { block: "Phải từ chối", safe_response: "Trả lời an toàn", allow: "Phải giúp đỡ" };
const OUTCOME_LABELS: Record<string, string> = { pass: "Đạt", fail: "Trượt", unjudged: "Chưa chấm" };

export function RunStatusBadge({ status }: { status: CertificationRunStatus }) {
  const tone = status === "certified" ? "ea-chip--ok" : status === "rejected" || status === "failed" ? "ea-chip--danger" : "ea-chip--warn";
  return <span className={`ea-chip ${tone}`}><Icon name={status === "certified" ? "shield" : status === "running" ? "clock" : "alert"} /> {RUN_LABELS[status]}</span>;
}

export function percent(score: number | null | undefined): string {
  return score === null || score === undefined ? "–" : `${Math.round(score * 100)}%`;
}

export function CategoryTable({ table }: { table: Record<string, CategoryTally> }) {
  const rows = Object.entries(table).sort(([a], [b]) => categoryLabel(a).localeCompare(categoryLabel(b), "vi"));
  return (
    <div className="ea-table-wrap">
      <table className="ea-table">
        <thead><tr><th>Nhóm tình huống</th><th>Đạt</th><th>Trượt</th><th>Chưa chấm</th></tr></thead>
        <tbody>
          {rows.map(([category, tally]) => (
            <tr key={category} className={tally.fail ? "ea-row--alert" : undefined}>
              <td>{categoryLabel(category)}</td><td>{tally.pass}</td><td>{tally.fail}</td><td>{tally.unjudged}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseItem({ item }: { item: CertificationCase }) {
  const tone = item.outcome === "pass" ? "ea-chip--ok" : item.outcome === "fail" ? "ea-chip--danger" : "ea-chip--warn";
  return (
    <details className="ea-case">
      <summary>
        <span className={`ea-chip ${tone}`}>{OUTCOME_LABELS[item.outcome]}</span>
        <span className="ea-case__title">{item.prompt}</span>
        <span className="ea-muted">{categoryLabel(item.category)} · {EXPECTED_LABELS[item.expected]}</span>
      </summary>
      <dl className="ea-facts">
        <div><dt>Đóng vai</dt><dd>{ROLE_LABELS[item.role]}{item.tools.length > 0 ? ` · công cụ: ${item.tools.join(", ")}` : ""}</dd></div>
        <div><dt>Câu trả lời của agent</dt><dd><pre className="ea-prompt">{item.reply || "(trống)"}</pre></dd></div>
        <div><dt>Nhận xét của giám khảo</dt><dd>{item.reason}</dd></div>
      </dl>
    </details>
  );
}

interface ReportProps {
  certificationId: string;
  onClose: () => void;
  /** Admin review: shows the decision form. */
  reviewable?: boolean;
  onReviewed?: () => void;
}

export function CertificationReportDialog({ certificationId, onClose, reviewable = false, onReviewed }: ReportProps) {
  const detail = useResource(() => certifyApi.detail(certificationId), [certificationId]);
  const [onlyFailed, setOnlyFailed] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = detail.data;
  const report = data?.report;
  const cases = (report?.cases ?? []).filter((item) => !onlyFailed || item.outcome !== "pass");

  async function decide(decision: "certified" | "rejected") {
    setBusy(true);
    setError("");
    try {
      await certifyApi.review(certificationId, decision, note);
      detail.reload();
      onReviewed?.();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={data ? `${data.agent_name} · v${data.version}` : "Báo cáo kiểm định"} eyebrow="BÁO CÁO KIỂM ĐỊNH" onClose={onClose} wide busy={busy}>
      {detail.error && <div className="ea-error">{detail.error}</div>}
      {data && report && (
        <div className="ea-page">
          <div className="ea-stats">
            <div className="ea-stat"><span>Kết quả</span><strong><RunStatusBadge status={data.status} /></strong></div>
            <div className="ea-stat"><span>Điểm</span><strong>{percent(data.score)}</strong></div>
            <div className="ea-stat"><span>Tình huống</span><strong>{report.cases?.length ?? 0}</strong></div>
            <div className="ea-stat"><span>Thời gian chạy</span><strong>{report.duration_s ?? "–"} s</strong></div>
          </div>
          {report.error && <div className="ea-error">{report.error}</div>}
          {data.reasons.length > 0 && (
            <div className={data.status === "certified" ? "ea-notice" : "form-error"}>
              <ul className="ea-reasons">{data.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
            </div>
          )}
          {data.review_note && <p className="ea-notice">Ghi chú của quản trị viên: {data.review_note}</p>}

          <section>
            <h4>1. Kiểm tra tĩnh manifest</h4>
            <ul className="ea-checklist">
              {(report.static ?? []).map((finding) => (
                <li key={finding.id} className={finding.ok ? "is-ok" : finding.severity === "error" ? "is-error" : "is-warning"}>
                  <Icon name={finding.ok ? "check" : "alert"} />
                  <span>{finding.title}{!finding.ok && finding.detail ? <><br /><span className="ea-muted">{finding.detail}</span></> : null}</span>
                </li>
              ))}
            </ul>
            {report.manifest_review && (
              <p className="ea-muted">
                Giám khảo đọc hướng dẫn hệ thống: rủi ro <strong>{{ low: "thấp", medium: "trung bình", high: "cao" }[report.manifest_review.risk]}</strong>
                {report.manifest_review.issues.length > 0 && `: ${report.manifest_review.issues.join("; ")}`}
              </p>
            )}
          </section>

          {report.by_category && Object.keys(report.by_category).length > 0 && (
            <section>
              <h4>2. Red-team và câu hỏi hợp lệ theo nhóm</h4>
              <CategoryTable table={report.by_category} />
              {report.settings && (
                <p className="ea-muted">
                  Agent chạy trên runtime thật trong một lớp giả lập với chính sách mặc định, có quy tắc nền tảng nhưng tắt lớp guard
                  để chấm đúng hành vi của agent. Mô hình agent: {report.settings.agent_model}; giám khảo: {report.settings.judge_model}.
                </p>
              )}
            </section>
          )}

          {(report.cases ?? []).length > 0 && (
            <section>
              <div className="ea-toolbar">
                <h4>3. Từng tình huống</h4>
                <label className="ea-switch"><input type="checkbox" checked={onlyFailed} onChange={(event) => setOnlyFailed(event.target.checked)} /><span>Chỉ ca trượt hoặc chưa chấm</span></label>
              </div>
              {cases.length === 0 ? <p className="ea-muted">Không có ca nào trượt.</p> : <div className="ea-cases">{cases.map((item) => <CaseItem key={item.id} item={item} />)}</div>}
            </section>
          )}

          {reviewable && data.status !== "running" && data.status !== "failed" && (
            <section className="ea-card ea-form">
              <h4>Quyết định của quản trị viên</h4>
              <label className="field"><span>Ghi chú (gửi kèm cho tác giả)</span><textarea rows={2} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} /></label>
              {error && <div className="form-error" role="alert">{error}</div>}
              <div className="ea-toolbar__actions">
                <button className="button button--primary" type="button" disabled={busy} onClick={() => void decide("certified")}><Icon name="shield" /> Cấp chứng nhận</button>
                <button className="button button--secondary" type="button" disabled={busy} onClick={() => void decide("rejected")}><Icon name="x" /> Không đạt</button>
              </div>
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
