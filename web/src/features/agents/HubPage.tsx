import { useState } from "react";

import { useResource } from "../../app/useResource";
import { hubApi } from "../../api-client/agents";
import { SUBJECT_LABELS } from "../../api-client/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { AgentCard, AgentDetailDialog } from "./AgentCard";

/** Agent Hub: certified agents from the platform and the community. */
export function HubPage() {
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [subject, setSubject] = useState("");
  const [grade, setGrade] = useState("");
  const [role, setRole] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const filters = { q: q.trim(), subject, grade: grade ? Number(grade) : null, role };
  const agents = useResource(() => hubApi.list(filters), [filters.q, subject, grade, role]);
  const canFilterRole = user?.role === "teacher" || user?.role === "admin";

  return (
    <div className="ea-page">
      <div className="ea-card ea-filters">
        <label className="field">
          <span>Tìm agent</span>
          <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Ví dụ: phương trình, luyện nói, chấm văn" />
        </label>
        <label className="field">
          <span>Môn</span>
          <select value={subject} onChange={(event) => setSubject(event.target.value)}>
            <option value="">Tất cả</option>
            {Object.entries(SUBJECT_LABELS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Khối</span>
          <select value={grade} onChange={(event) => setGrade(event.target.value)}>
            <option value="">Tất cả</option>
            {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>Lớp {value}</option>)}
          </select>
        </label>
        {canFilterRole && (
          <label className="field">
            <span>Dành cho</span>
            <select value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="">Mọi vai trò</option>
              <option value="teacher">Giáo viên</option>
              <option value="student">Học sinh</option>
              <option value="parent">Phụ huynh</option>
            </select>
          </label>
        )}
      </div>

      <div className="ea-notice">
        <Icon name="shield" /> Mọi agent trên Hub đã qua kiểm định tự động về an toàn, đúng vai và không làm hộ bài trước khi được chia sẻ.
      </div>

      {agents.error && <div className="ea-error">{agents.error}</div>}
      {agents.data && agents.data.length === 0 && <div className="ea-empty"><Icon name="search" /><p>Không tìm thấy agent phù hợp.</p></div>}
      <div className="ea-grid">
        {(agents.data ?? []).map((agent) => (
          <AgentCard key={agent.id} agent={agent} onOpen={() => setOpen(agent.id)}
            footer={<span className="ea-muted"><Icon name="team" /> {agent.install_count} lượt cài</span>} />
        ))}
      </div>
      {open && <AgentDetailDialog agentId={open} onClose={() => setOpen(null)} onChanged={agents.reload} />}
    </div>
  );
}
