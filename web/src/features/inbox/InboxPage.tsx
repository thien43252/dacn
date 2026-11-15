import { useState } from "react";

import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { inboxApi } from "../../api-client/chat";
import { useAuth } from "../../auth/AuthContext";
import { PersonRequestCard } from "../../components/chat/PersonRequestCard";
import "../chat/messenger.css";

const FILTERS = [
  { id: "open", label: "Đang chờ" },
  { id: "answered", label: "Đã trả lời" },
  { id: "all", label: "Tất cả" },
];

/** Hộp yêu cầu: questions and approval requests agents sent to this person on someone's behalf (FR-028). */
export function InboxPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState("open");
  const items = useResource(() => inboxApi.list(status), [status]);
  if (!user) return null;
  return (
    <div className="ea-inbox" data-testid="inbox">
      <div className="ea-inbox__head">
        <div className="sub-tabs" role="tablist" aria-label="Lọc yêu cầu">
          {FILTERS.map((filter) => (
            <button key={filter.id} role="tab" type="button" aria-selected={status === filter.id} className={status === filter.id ? "is-active" : ""} onClick={() => setStatus(filter.id)}>
              {filter.label}
            </button>
          ))}
        </div>
        <button type="button" className="button button--ghost" onClick={() => navigate(`/${user.role}/settings/approvals`)}>Cài đặt duyệt</button>
      </div>
      {items.error && <p className="form-error">{items.error}</p>}
      {items.loading && !items.data && <p className="ea-muted">Đang tải…</p>}
      {items.data && items.data.length === 0 && <p className="ea-muted">Không có yêu cầu nào.</p>}
      <div className="ea-inbox__list">
        {(items.data ?? []).map((request) => (
          <PersonRequestCard key={request.id} request={request} viewerId={user.id} onChanged={() => items.reload()} />
        ))}
      </div>
    </div>
  );
}
