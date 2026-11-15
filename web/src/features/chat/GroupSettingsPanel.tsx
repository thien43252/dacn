import { useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { groupsApi } from "../../api-client/chat";
import type { ConversationListItem } from "../../api-client/types";
import { Icon } from "../../components/Icon";

/** Members of a group: add people or agents (with or without history), remove them, or leave (FR-041, FR-047). */
export function GroupSettingsPanel({ group, viewerId, onChanged, onLeft }: { group: ConversationListItem; viewerId: string; onChanged: () => void; onLeft: () => void }) {
  const members = useResource(() => groupsApi.members(group.id), [group.id]);
  const [adding, setAdding] = useState(false);
  const candidates = useResource(() => (adding ? groupsApi.groupCandidates(group.id) : Promise.resolve(null)), [adding, group.id]);
  const [history, setHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const me = members.data?.find((member) => member.user_id === viewerId);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      members.reload();
      onChanged();
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  return (
    <div className="messenger__settings">
      <ul>
        {(members.data ?? []).map((member) => (
          <li key={member.id}>
            <Icon name={member.kind === "agent" ? "sparkles" : "user"} />
            <span>{member.name} <small className="ea-muted">{member.role_label}{member.is_admin ? " · quản lý" : ""}</small></span>
            {me?.is_admin && member.user_id !== viewerId && (
              <button type="button" className="button button--ghost" onClick={() => void run(() => groupsApi.removeMember(group.id, member.id))}>Bớt</button>
            )}
          </li>
        ))}
      </ul>
      <div className="messenger__settings-actions">
        {me?.is_admin && <button type="button" className="button" onClick={() => setAdding((value) => !value)}>{adding ? "Đóng" : "Thêm thành viên"}</button>}
        {me && <button type="button" className="button button--ghost" onClick={() => void run(async () => { await groupsApi.removeMember(group.id, me.id); onLeft(); })}>Rời nhóm</button>}
      </div>
      {adding && candidates.data && (
        <div className="messenger__add">
          <label className="ea-check"><input type="checkbox" checked={history} onChange={(event) => setHistory(event.target.checked)} /> <span>Cho xem tin nhắn cũ</span></label>
          <ul>
            {candidates.data.people.map((person) => (
              <li key={person.id}>
                <span>{person.name} <small className="ea-muted">{person.role_label}</small></span>
                <button type="button" className="button" onClick={() => void run(() => groupsApi.addMembers(group.id, { users: [person.id], can_see_history: history }))}>Thêm</button>
              </li>
            ))}
            {candidates.data.agents.map((agent) => (
              <li key={agent.slug}>
                <span>{agent.name} <small className="ea-muted">Agent</small></span>
                <button type="button" className="button" onClick={() => void run(() => groupsApi.addMembers(group.id, { agents: [agent.slug] }))}>Thêm</button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
