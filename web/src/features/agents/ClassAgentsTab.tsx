import { useState } from "react";

import { Modal } from "../../agents/Modal";
import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { builderApi, hubApi, installApi } from "../../api-client/agents";
import type { ClassRoom, HubAgent, Installation } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { AgentCard, AgentDetailDialog } from "./AgentCard";

/** Agents installed in one class. The class assistant is always on and is not listed. */
export function ClassAgentsTab({ room }: { room: ClassRoom }) {
  const installs = useResource(() => installApi.classAgents(room.id), [room.id]);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      installs.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <p className="ea-muted">Trợ lý lớp luôn có sẵn. Agent chưa kiểm định chỉ giáo viên dùng thử được; học sinh và phụ huynh chỉ thấy agent đã kiểm định.</p>
        <div className="ea-toolbar__actions">
          <button className="button button--secondary" type="button" onClick={() => navigate("/teacher/hub")}><Icon name="layers" /> Mở Agent Hub</button>
          <button className="button button--primary" type="button" onClick={() => setAdding(true)}><Icon name="plus" /> Thêm agent</button>
        </div>
      </div>
      {error && <div className="form-error" role="alert">{error}</div>}
      {installs.error && <div className="ea-error">{installs.error}</div>}
      {installs.data && installs.data.length === 0 && (
        <div className="ea-empty"><Icon name="sparkles" /><p>Lớp chưa cài agent nào ngoài Trợ lý lớp.</p></div>
      )}
      <div className="ea-grid">
        {(installs.data ?? []).map((installation: Installation) => (
          <AgentCard
            key={installation.id}
            agent={installation.agent}
            onOpen={() => setOpen(installation.agent.id)}
            footer={
              <>
                <label className="ea-switch">
                  <input type="checkbox" checked={installation.enabled}
                    onChange={(event) => void run(() => installApi.toggle(room.id, installation.id, event.target.checked))} />
                  <span>{installation.enabled ? "Đang bật" : "Đang tắt"}</span>
                </label>
                <button className="icon-button icon-button--danger" type="button" aria-label={`Gỡ ${installation.agent.name}`}
                  onClick={() => void run(() => installApi.uninstall(room.id, installation.id))}>
                  <Icon name="trash" />
                </button>
              </>
            }
          />
        ))}
      </div>
      {adding && <AddAgentDialog room={room} installed={(installs.data ?? []).map((item) => item.agent.id)} onClose={() => setAdding(false)} onAdded={installs.reload} />}
      {open && <AgentDetailDialog agentId={open} onClose={() => setOpen(null)} onChanged={installs.reload} />}
    </div>
  );
}

function AddAgentDialog({ room, installed, onClose, onAdded }: { room: ClassRoom; installed: string[]; onClose: () => void; onAdded: () => void }) {
  const hub = useResource(() => hubApi.list({ subject: "" }), []);
  const mine = useResource(() => builderApi.mine(), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const candidates: HubAgent[] = [
    ...(mine.data ?? []).filter((agent) => agent.version > 0),
    ...(hub.data ?? []).filter((agent) => !(mine.data ?? []).some((own) => own.id === agent.id)),
  ].filter((agent) => agent.slug !== "tro-ly-lop");

  async function add(agent: HubAgent) {
    setBusy(agent.id);
    setError("");
    try {
      await installApi.installInClass(room.id, agent.id);
      onAdded();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal title={`Thêm agent vào ${room.name}`} eyebrow="AGENT CỦA LỚP" onClose={onClose} wide>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="ea-grid">
        {candidates.map((agent) => {
          const done = installed.includes(agent.id);
          return (
            <AgentCard key={agent.id} agent={agent} footer={
              <button className="button button--primary" type="button" disabled={done || busy === agent.id} onClick={() => void add(agent)}>
                {done ? <><Icon name="check" /> Đã cài</> : <><Icon name="plus" /> Cài</>}
              </button>
            } />
          );
        })}
      </div>
    </Modal>
  );
}
