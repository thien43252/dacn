import { useEffect, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { certifyApi } from "../../api-client/agents";
import type { AgentDetail, Certification } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { CertificationBadge } from "../agents/AgentCard";
import { CertificationReportDialog, percent } from "./CertificationReport";

const POLL_MS = 2000;

/** Versions of an agent the author owns, with certification runs, reports and Hub visibility. */
export function VersionsPanel({ agent, onChanged }: { agent: AgentDetail; onChanged: () => void }) {
  const runs = useResource(() => certifyApi.forAgent(agent.id), [agent.id]);
  const [report, setReport] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = agent.versions.some((version) => version.certification_status === "pending") || (runs.data ?? []).some((run) => run.status === "running");

  // While a run is in progress, refresh its progress and, when it ends, the agent's version statuses.
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      runs.reload();
      onChanged();
    }, POLL_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);

  const latestRun = (versionId: string): Certification | undefined => (runs.data ?? []).find((run) => run.version_id === versionId);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      runs.reload();
      onChanged();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ea-card ea-page">
      <div className="ea-toolbar">
        <h3>Phiên bản và kiểm định</h3>
        <label className="ea-switch">
          <input type="checkbox" checked={agent.visibility === "public"} disabled={busy}
            onChange={(event) => void act(() => certifyApi.setVisibility(agent.id, event.target.checked ? "public" : "private"))} />
          <span>Chia sẻ lên Agent Hub</span>
        </label>
      </div>
      <p className="ea-muted">
        Kiểm định chạy agent qua khoảng 36 tình huống (tấn công red-team và câu hỏi hợp lệ) rồi để giám khảo chấm. Chỉ phiên bản
        đã kiểm định mới đến được học sinh, phụ huynh và hiện trên Hub khi bạn bật chia sẻ.
      </p>
      {error && <div className="form-error" role="alert">{error}</div>}
      <ul className="ea-versions">
        {agent.versions.map((version) => {
          const run = latestRun(version.id);
          const pending = version.certification_status === "pending";
          const certified = version.certification_status === "certified";
          return (
            <li key={version.id}>
              <strong>v{version.version}</strong>
              <CertificationBadge status={version.certification_status} />
              {pending && run?.progress.total ? <span className="ea-muted">{run.progress.done ?? 0}/{run.progress.total} tình huống</span> : null}
              {run && run.status !== "running" && <span className="ea-muted">Điểm {percent(run.score)}</span>}
              <span className="ea-muted">{new Date(version.created_at).toLocaleString("vi-VN")}</span>
              <span className="ea-row-actions">
                {run && <button className="button button--ghost" type="button" onClick={() => setReport(run.id)}><Icon name="eye" /> Báo cáo</button>}
                {!pending && !certified && (
                  <>
                    <button className="button button--secondary" type="button" disabled={busy} onClick={() => void act(() => certifyApi.start(agent.id, version.id, false))}>
                      <Icon name="shield" /> Kiểm định
                    </button>
                    <button className="button button--primary" type="button" disabled={busy} onClick={() => void act(() => certifyApi.start(agent.id, version.id, true))}>
                      <Icon name="globe" /> Kiểm định và đăng Hub
                    </button>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {report && <CertificationReportDialog certificationId={report} onClose={() => setReport(null)} />}
    </section>
  );
}
