import { useState } from "react";

import { errorMessage, useResource } from "../../app/useResource";
import { conversationsApi, type DirectSession } from "../../api-client/chat";

function stamp(at: string): string {
  return new Date(at).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Past sessions with the agent of a direct chat; picking one loads it back as the open session. */
export function SessionHistoryPanel({ currentId, onPick }: { currentId: string; onPick: (session: DirectSession) => Promise<void> }) {
  const sessions = useResource(() => conversationsApi.sessions(currentId), [currentId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(session: DirectSession) {
    setBusy(session.id);
    setError(null);
    try {
      await onPick(session);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="messenger__history" aria-label="Lịch sử phiên chat">
      <strong>Lịch sử phiên chat</strong>
      {sessions.loading && <p className="ea-muted">Đang tải…</p>}
      {sessions.error && <p className="form-error">{sessions.error}</p>}
      {!sessions.loading && (sessions.data ?? []).length === 0 && <p className="ea-muted">Chưa có phiên nào.</p>}
      <ul>
        {(sessions.data ?? []).map((session) => {
          const current = session.id === currentId;
          const summary = session.last_message
            ? `${session.last_message.sender ? `${session.last_message.sender}: ` : ""}${session.last_message.text}`
            : "Chưa có tin nhắn";
          // Auto-routed chats are titled by their first question; chats with one agent are titled by the agent.
          const heading = session.agent?.slug ? summary : session.title || summary;
          return (
            <li key={session.id}>
              <button type="button" className={`messenger__session${current ? " is-active" : ""}`} disabled={current || busy !== null}
                onClick={() => void pick(session)} aria-current={current ? "true" : undefined}>
                <span className="messenger__session-top">
                  <strong>{heading}</strong>
                  {current ? <em>Đang mở</em> : busy === session.id ? <em>Đang mở lại…</em> : null}
                </span>
                <small>{stamp(session.last_message?.at ?? session.updated_at)}</small>
              </button>
            </li>
          );
        })}
      </ul>
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
