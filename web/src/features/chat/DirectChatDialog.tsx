import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { chatApi } from "../../api-client/agents";
import { conversationsApi } from "../../api-client/chat";
import type { ClassRoom, ConversationListItem } from "../../api-client/types";
import { mascotOf } from "../../components/chat/ChatThread";
import { Mascot } from "../../components/Mascot";

const PERSONAL = "__personal__";

/** Pick a class (or the personal space) and an agent; opens the one direct chat with it (FR-048). */
export function DirectChatDialog({ classes, onClose, onOpened }: { classes: ClassRoom[]; onClose: () => void; onOpened: (c: ConversationListItem) => void }) {
  const active = classes.filter((room) => !room.archived);
  const [scope, setScope] = useState(active[0]?.id ?? PERSONAL);
  const touched = useRef(false);
  // The class list may arrive after the dialog opens: default to the first class unless the user already chose.
  useEffect(() => {
    if (!touched.current && scope === PERSONAL && active[0]) setScope(active[0].id);
  }, [active, scope]);
  const classId = scope === PERSONAL ? null : scope;
  const agents = useResource(() => chatApi.agents(classId), [classId]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function pick(slug: string) {
    setBusy(true);
    setError(null);
    try {
      onOpened(await conversationsApi.openDirect(classId, slug));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return createPortal(

    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div className="dialog frosted messenger__dialog" role="dialog" aria-modal="true" aria-labelledby="direct-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="direct-title">Chat riêng với một agent</h2>
        <p className="ea-muted">Chỉ bạn xem được cuộc trò chuyện này.</p>
        <label className="field">
          <span>Trong lớp</span>
          <select value={scope} onChange={(event) => { touched.current = true; setScope(event.target.value); }}>
            {active.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
            <option value={PERSONAL}>Không thuộc lớp (agent cá nhân)</option>
          </select>
        </label>
        {agents.loading && <p className="ea-muted">Đang tải agent…</p>}
        {agents.error && <p className="form-error">{agents.error}</p>}
        <ul className="messenger__agent-pick">
          {(agents.data ?? []).map((agent) => (
            <li key={agent.slug}>
              <button type="button" disabled={busy} onClick={() => void pick(agent.slug)}>
                <Mascot character={mascotOf(agent.avatar)} mood="still" size={32} />
                <span><strong>{agent.name}</strong><small>{agent.description}</small></span>
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog__actions"><button className="button" type="button" onClick={onClose}>Đóng</button></div>
      </div>
    </div>,
    document.body,
  );
}
