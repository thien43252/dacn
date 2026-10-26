import { useState } from "react";

import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { installApi } from "../../api-client/agents";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { AgentCard, AgentDetailDialog } from "./AgentCard";

/** Agents a student or parent pulled from the Hub for themselves. */
export function MyAgentsPage() {
  const { user } = useAuth();
  const installs = useResource(() => installApi.mine(), []);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");
  const hubPath = user?.role === "parent" ? "/parent/hub" : "/student/hub";

  async function remove(id: string) {
    setError("");
    try {
      await installApi.uninstallPersonal(id);
      installs.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <p className="ea-muted">Agent cá nhân dùng được ở mọi nơi; trong lớp, chúng vẫn tuân theo chính sách của lớp đó.</p>
        <button className="button button--primary" type="button" onClick={() => navigate(hubPath)}><Icon name="layers" /> Tìm trên Hub</button>
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {installs.data && installs.data.length === 0 && (
        <div className="ea-empty"><Icon name="sparkles" /><p>Bạn chưa thêm agent nào.</p></div>
      )}
      <div className="ea-grid">
        {(installs.data ?? []).map((installation) => (
          <AgentCard key={installation.id} agent={installation.agent} onOpen={() => setOpen(installation.agent.id)} footer={
            <button className="button button--ghost" type="button" onClick={() => void remove(installation.id)}><Icon name="trash" /> Gỡ</button>
          } />
        ))}
      </div>
      {open && <AgentDetailDialog agentId={open} onClose={() => setOpen(null)} onChanged={installs.reload} />}
    </div>
  );
}
