import { Icon } from "./Icon";
import { Mascot } from "./Mascot";

/**
 * Slide-out assistant panel. Week 1 only renders the frame; the message list, @mention composer and SSE stream
 * (via `api-client/chatStream.ts`) arrive in week 4.
 */
export function ChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <aside className="chat-panel chat-panel--open" aria-labelledby="chat-panel-title">
      <div className="chat-panel__inner">
        <header className="chat-panel__header">
          <div className="agent-avatar agent-avatar--mascot"><Mascot character="fox" mood="idle" interactive /></div>
          <div>
            <strong id="chat-panel-title">Trợ lý lớp học</strong>
            <span>Các agent đã cài trong lớp</span>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Đóng trợ lý">
            <Icon name="x" />
          </button>
        </header>
        <div className="placeholder-page">
          <Icon name="message" />
          <p>Trò chuyện với agent sẽ có ở tuần 4 của kế hoạch.</p>
        </div>
      </div>
    </aside>
  );
}
