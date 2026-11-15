import { useResource } from "../../app/useResource";
import { navigate } from "../../app/router";
import { auditApi } from "../../api-client/agents";
import { Icon } from "../../components/Icon";
import { ActivityList } from "../audit/ActivityList";

/** An agent's activity page for its owner (FR-057): what it ran, handed over and was refused, with the results.
 * Metadata only: no conversation text of other people. */
export function AgentActivityPage({ agentId, backTo }: { agentId: string; backTo: string }) {
  const activity = useResource(() => auditApi.agent(agentId), [agentId]);
  return (
    <div className="ea-page">
      <div className="ea-toolbar">
        <button type="button" className="button button--ghost" onClick={() => navigate(backTo)}>← Quay lại trình tạo agent</button>
        <button type="button" className="button button--ghost" onClick={activity.reload}><Icon name="history" /> Tải lại</button>
      </div>
      <div className="ea-notice">
        Các lần agent chạy công cụ, giao việc cho agent khác, hỏi người và bị từ chối, kèm kết quả. Tệp đã lưu chỉ ghi tên và
        kích thước. Nội dung hội thoại của người khác không hiện ở đây.
      </div>
      {activity.error && <div className="ea-error">{activity.error}</div>}
      {activity.data && <ActivityList rows={activity.data} empty="Agent này chưa có hoạt động nào." />}
    </div>
  );
}

/** A student's or parent's own activity: only their own conversations (FR-057). */
export function MyActivityPage() {
  const activity = useResource(() => auditApi.mine(), []);
  return (
    <div className="ea-page">
      <div className="ea-notice">Chỉ gồm hoạt động trong các cuộc trò chuyện của chính bạn.</div>
      {activity.error && <div className="ea-error">{activity.error}</div>}
      {activity.data && (
        <ActivityList rows={activity.data} empty="Chưa có lần giao việc, câu hỏi gửi người hay quyết định duyệt nào." />
      )}
    </div>
  );
}
