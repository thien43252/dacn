import { createPortal } from "react-dom";
import { type FormEvent, useEffect, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { groupsApi } from "../../api-client/chat";
import type { ClassRoom, ConversationListItem } from "../../api-client/types";

/** Create a group in a class: people the platform lets this user add, agents of the class (FR-039, FR-040). */
export function NewGroupDialog({ classes, onClose, onCreated }: { classes: ClassRoom[]; onClose: () => void; onCreated: (c: ConversationListItem) => void }) {
  const active = classes.filter((room) => !room.archived);
  const [classId, setClassId] = useState(active[0]?.id ?? "");
  useEffect(() => {
    if (!classId && active[0]) setClassId(active[0].id);
  }, [active, classId]);
  const candidates = useResource(() => (classId ? groupsApi.candidates(classId) : Promise.resolve(null)), [classId]);
  const [title, setTitle] = useState("");
  const [people, setPeople] = useState<Set<string>>(new Set());
  const [agents, setAgents] = useState<Set<string>>(new Set(["tro-ly-lop"]));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(set: Set<string>, value: string, update: (next: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    update(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await groupsApi.create({ class_id: classId, title: title.trim(), members: [...people], agents: [...agents] }));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const data = candidates.data;
  return createPortal(

    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <form className="dialog frosted messenger__dialog" role="dialog" aria-modal="true" aria-labelledby="group-title" onClick={(event) => event.stopPropagation()} onSubmit={submit}>
        <h2 id="group-title">Tạo nhóm chat</h2>
        <p className="ea-muted">Nhóm riêng tư: chỉ thành viên biết nhóm tồn tại và đọc được tin.</p>
        <label className="field">
          <span>Lớp</span>
          <select value={classId} onChange={(event) => { setClassId(event.target.value); setPeople(new Set()); }}>
            {active.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Tên nhóm</span>
          <input required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ví dụ: Ôn thi HK1" />
        </label>
        {candidates.loading && <p className="ea-muted">Đang tải danh sách…</p>}
        {data && !data.can_create && <p className="form-error">Giáo viên chưa cho học sinh, phụ huynh tạo nhóm trong lớp này.</p>}
        {data && (
          <div className="messenger__pick-grid">
            <fieldset>
              <legend>Người</legend>
              {data.people.length === 0 && <p className="ea-muted">Không có ai để thêm.</p>}
              {data.people.map((person) => (
                <label key={person.id} className="ea-check">
                  <input type="checkbox" checked={people.has(person.id)} onChange={() => toggle(people, person.id, setPeople)} />
                  <span>{person.name} <small className="ea-muted">{person.role_label}</small></span>
                </label>
              ))}
            </fieldset>
            <fieldset>
              <legend>Agent</legend>
              {data.agents.map((agent) => (
                <label key={agent.slug} className="ea-check">
                  <input type="checkbox" checked={agents.has(agent.slug)} onChange={() => toggle(agents, agent.slug, setAgents)} />
                  <span>{agent.name}</span>
                </label>
              ))}
            </fieldset>
          </div>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog__actions">
          <button className="button" type="button" onClick={onClose}>Huỷ</button>
          <button className="button button--primary" type="submit" disabled={busy || !title.trim() || !classId || data?.can_create === false}>Tạo nhóm</button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
