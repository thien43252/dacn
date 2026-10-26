import { type ReactNode, useState } from "react";

import { Modal } from "../../agents/Modal";
import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { builderApi, hubApi, installApi } from "../../api-client/agents";
import { classesApi } from "../../api-client/classes";
import { CERTIFICATION_LABELS, type CertificationStatus, type HubAgent, ROLE_LABELS, subjectLabel } from "../../api-client/types";
import { useAuth } from "../../auth/AuthContext";
import { mascotOf } from "../../components/chat/ChatThread";
import { Icon } from "../../components/Icon";
import { Mascot } from "../../components/Mascot";

const TOOL_TITLES: Record<string, string> = {
  class_doc_search: "Tìm trong tài liệu lớp",
  quiz_generator: "Tạo câu hỏi",
  rubric_grader: "Chấm theo rubric",
  math_check: "Kiểm tra toán",
  progress_summary: "Tổng hợp tiến độ",
};

export function toolTitle(name: string): string {
  return TOOL_TITLES[name] ?? name;
}

export function CertificationBadge({ status }: { status: CertificationStatus }) {
  const tone = status === "certified" ? "ea-chip--ok" : status === "rejected" ? "ea-chip--danger" : "ea-chip--warn";
  return (
    <span className={`ea-chip ${tone}`}>
      <Icon name={status === "certified" ? "shield" : status === "rejected" ? "alert" : "clock"} /> {CERTIFICATION_LABELS[status]}
    </span>
  );
}

export function AgentCard({ agent, onOpen, footer }: { agent: HubAgent; onOpen?: () => void; footer?: ReactNode }) {
  const body = (
    <>
      <div className="ea-agent-card__head">
        <Mascot character={mascotOf(agent.avatar)} mood="still" size={48} />
        <div>
          <h3>{agent.name}</h3>
          <span className="ea-muted">@{agent.slug} · {agent.author}</span>
        </div>
      </div>
      <p className="ea-muted ea-clamp">{agent.description}</p>
      <div className="ea-card__meta">
        <CertificationBadge status={agent.certification_status} />
        {agent.subjects.filter((subject) => subject !== "chung").map((subject) => <span key={subject} className="ea-chip">{subjectLabel(subject)}</span>)}
        {agent.target_roles.map((role) => <span key={role} className="ea-chip">{ROLE_LABELS[role]}</span>)}
      </div>
    </>
  );
  return onOpen ? (
    <article className="ea-card ea-agent-card">
      <button type="button" className="ea-agent-card__open" onClick={onOpen} aria-label={`Xem ${agent.name}`}>{body}</button>
      {footer && <div className="ea-card__foot">{footer}</div>}
    </article>
  ) : (
    <article className="ea-card ea-agent-card">{body}{footer && <div className="ea-card__foot">{footer}</div>}</article>
  );
}

/** Full manifest of a Hub agent plus the install actions the viewer's role allows. */
export function AgentDetailDialog({ agentId, onClose, onChanged }: { agentId: string; onClose: () => void; onChanged?: () => void }) {
  const { user } = useAuth();
  const detail = useResource(() => hubApi.detail(agentId), [agentId]);
  const isTeacher = user?.role === "teacher" || user?.role === "admin";
  const classes = useResource(() => (isTeacher ? classesApi.list() : Promise.resolve([])), [isTeacher]);
  const [classId, setClassId] = useState("");
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const agent = detail.data;
  const teachable = (classes.data ?? []).filter((room) => room.my_role === "teacher" && !room.archived);

  async function act(action: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setStatus(null);
    try {
      await action();
      setStatus({ kind: "ok", text: ok });
      onChanged?.();
    } catch (reason) {
      setStatus({ kind: "error", text: errorMessage(reason) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={agent?.name ?? "Agent"} eyebrow={agent ? `@${agent.slug} · phiên bản ${agent.version || "nháp"}` : "AGENT"} onClose={onClose} wide busy={busy}>
      {detail.error && <div className="ea-error">{detail.error}</div>}
      {agent && (
        <div className="ea-detail">
          <div className="ea-detail__main">
            <div className="ea-agent-card__head">
              <Mascot character={mascotOf(agent.avatar)} mood="idle" size={72} interactive />
              <div>
                <p>{agent.description}</p>
                <div className="ea-card__meta">
                  <CertificationBadge status={agent.certification_status} />
                  <span>Tác giả: {agent.author}</span>
                  <span>· {agent.install_count} lượt cài</span>
                </div>
              </div>
            </div>
            {agent.certification && agent.certification.status !== "uncertified" && (
              <p className="ea-notice">
                <Icon name="shield" /> Kiểm định phiên bản này: {CERTIFICATION_LABELS[agent.certification.status]}
                {agent.certification.score !== null && <>, đạt <strong>{Math.round(agent.certification.score * 100)}%</strong></>} trên {agent.certification.cases} tình huống
                {" "}(red-team tiếng Việt và câu hỏi hợp lệ), ngày {new Date(agent.certification.finished_at).toLocaleDateString("vi-VN")}.
              </p>
            )}
            <h4>Agent làm được gì</h4>
            <ul>{agent.capabilities.map((item) => <li key={item}>{item}</li>)}</ul>
            <h4>Công cụ được cấp</h4>
            {agent.tools.length === 0 ? <p className="ea-muted">Không dùng công cụ.</p> : (
              <div className="ea-card__meta">{agent.tools.map((tool) => <span key={tool} className="ea-chip">{toolTitle(tool)}</span>)}</div>
            )}
            <h4>Hướng dẫn hệ thống (minh bạch cho người dùng)</h4>
            <pre className="ea-prompt">{agent.manifest.system_prompt}</pre>
          </div>
          <aside className="ea-detail__side">
            <dl className="ea-facts">
              <div><dt>Dành cho</dt><dd>{agent.target_roles.map((role) => ROLE_LABELS[role]).join(", ")}</dd></div>
              <div><dt>Môn</dt><dd>{agent.subjects.map(subjectLabel).join(", ")}</dd></div>
              <div><dt>Khối lớp</dt><dd>{agent.grades.length ? agent.grades.join(", ") : "Mọi khối"}</dd></div>
              <div><dt>Tài liệu lớp</dt><dd>{agent.knowledge === "class_documents" ? "Có đọc" : "Không"}</dd></div>
            </dl>
            {isTeacher && (
              <>
                <label className="field">
                  <span>Cài vào lớp</span>
                  <select value={classId} onChange={(event) => setClassId(event.target.value)}>
                    <option value="">Chọn lớp…</option>
                    {teachable.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
                  </select>
                </label>
                <button className="button button--primary button--full" type="button" disabled={!classId || busy || agent.slug === "tro-ly-lop"}
                  onClick={() => void act(() => installApi.installInClass(classId, agent.id), "Đã cài vào lớp. Thành viên lớp dùng được từ tin nhắn tiếp theo.")}>
                  <Icon name="plus" /> Cài vào lớp
                </button>
                {agent.slug === "tro-ly-lop" && <p className="ea-muted">Trợ lý lớp luôn có sẵn trong mọi lớp.</p>}
                {user?.role === "teacher" && (
                  <button className="button button--secondary button--full" type="button" disabled={busy}
                    onClick={() => void act(async () => {
                      const fork = await builderApi.fork(agent.id);
                      navigate(`/teacher/builder?agent=${fork.id}`);
                    }, "Đã tạo bản sao trong “Agent của tôi”.")}>
                    <Icon name="edit" /> Tạo bản sao để chỉnh
                  </button>
                )}
              </>
            )}
            {(user?.role === "student" || user?.role === "parent") && (
              <button className="button button--primary button--full" type="button" disabled={busy}
                onClick={() => void act(() => installApi.installPersonal(agent.id), "Đã thêm vào “Agent của tôi”.")}>
                <Icon name="plus" /> Thêm vào agent của tôi
              </button>
            )}
            {status && <p className={status.kind === "ok" ? "ea-notice" : "form-error"} role="status">{status.text}</p>}
          </aside>
        </div>
      )}
    </Modal>
  );
}
