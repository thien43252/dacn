import { useCallback, useEffect, useRef, useState } from "react";
import { lmsApi, type NotificationItem } from "../../api-client/lms";
import { navigate } from "../../app/router";

function formatNotificationTime(dateStr: string | null): string {
  if (!dateStr) return "";
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Vừa xong";
    if (diffMins < 60) return `${diffMins} phút trước`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} giờ trước`;
    return date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return dateStr;
  }
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await lmsApi.notifications.list(false);
      setItems(data.items ?? []);
      setUnreadCount(data.unread_count ?? 0);
    } catch {
      // Background poll failure should stay silent
    }
  }, []);

  // Initial load + poll every 60 seconds
  useEffect(() => {
    void fetchNotifications();
    const interval = window.setInterval(() => {
      void fetchNotifications();
    }, 60000);
    return () => window.clearInterval(interval);
  }, [fetchNotifications]);

  // Click outside and escape handler
  useEffect(() => {
    if (!open) return;

    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  async function handleMarkAllRead() {
    try {
      await lmsApi.notifications.markRead();
      setUnreadCount(0);
      setItems((prev) =>
        prev.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })),
      );
    } catch {
      // ignore
    }
  }

  async function handleItemClick(item: NotificationItem) {
    if (!item.read_at) {
      try {
        await lmsApi.notifications.markRead([item.id]);
        setUnreadCount((c) => Math.max(0, c - 1));
        setItems((prev) =>
          prev.map((it) => (it.id === item.id ? { ...it, read_at: new Date().toISOString() } : it)),
        );
      } catch {
        // ignore
      }
    }
    setOpen(false);
    if (item.link) {
      navigate(item.link);
    }
  }

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        className="icon-button notification-bell__trigger"
        type="button"
        aria-label={`Thông báo${unreadCount > 0 ? ` (${unreadCount} chưa đọc)` : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Thông báo"
        onClick={() => setOpen((prev) => !prev)}
      >
        <svg
          aria-hidden="true"
          fill="none"
          height="20"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
          viewBox="0 0 24 24"
          width="20"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>

        {unreadCount > 0 && (
          <span className="sidebar__badge notification-bell__badge" aria-hidden="true">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="notification-bell__dropdown frosted" role="dialog" aria-label="Danh sách thông báo">
          <div className="notification-bell__header">
            <h4>Thông báo</h4>
            {unreadCount > 0 && (
              <button
                className="button button--ghost button--sm"
                type="button"
                onClick={handleMarkAllRead}
              >
                Đánh dấu đã đọc tất cả
              </button>
            )}
          </div>

          <div className="notification-bell__body">
            {items.length === 0 ? (
              <p className="ea-muted notification-bell__empty">Không có thông báo mới.</p>
            ) : (
              <ul className="notification-bell__list">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      className={`notification-bell__item ${!item.read_at ? "notification-bell__item--unread" : ""}`}
                      type="button"
                      onClick={() => void handleItemClick(item)}
                    >
                      <div className="notification-bell__item-content">
                        <span className="notification-bell__item-title">{item.title}</span>
                        <time className="notification-bell__item-time ea-muted">
                          {formatNotificationTime(item.created_at)}
                        </time>
                      </div>
                      {!item.read_at && <span className="notification-bell__dot" aria-hidden="true" />}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
