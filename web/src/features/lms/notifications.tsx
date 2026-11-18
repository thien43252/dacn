import { useCallback, useEffect, useState } from "react";
import { lmsApi, type NotificationItem } from "../../api-client/lms";

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

export interface NotificationsState {
  items: NotificationItem[];
  unreadCount: number;
  markAllRead: () => Promise<void>;
  markRead: (item: NotificationItem) => Promise<void>;
}

/** Polls the user's notifications every 60s; lives in the shell so the avatar badge stays current while the menu is closed. */
export function useNotifications(enabled: boolean): NotificationsState {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await lmsApi.notifications.list(false);
      setItems(data.items ?? []);
      setUnreadCount(data.unread_count ?? 0);
    } catch {
      // Background poll failure should stay silent
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void fetchNotifications();
    const interval = window.setInterval(() => void fetchNotifications(), 60000);
    return () => window.clearInterval(interval);
  }, [enabled, fetchNotifications]);

  const markAllRead = useCallback(async () => {
    try {
      await lmsApi.notifications.markRead();
      setUnreadCount(0);
      setItems((prev) => prev.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })));
    } catch {
      // ignore
    }
  }, []);

  const markRead = useCallback(async (item: NotificationItem) => {
    if (item.read_at) return;
    try {
      await lmsApi.notifications.markRead([item.id]);
      setUnreadCount((c) => Math.max(0, c - 1));
      setItems((prev) => prev.map((it) => (it.id === item.id ? { ...it, read_at: new Date().toISOString() } : it)));
    } catch {
      // ignore
    }
  }, []);

  return { items, unreadCount, markAllRead, markRead };
}

interface NotificationListProps {
  items: NotificationItem[];
  onSelect: (item: NotificationItem) => void;
}

export function NotificationList({ items, onSelect }: NotificationListProps) {
  if (items.length === 0) {
    return <p className="notification-list__empty">Không có thông báo mới.</p>;
  }
  return (
    <ul className="notification-list">
      {items.map((item) => (
        <li key={item.id}>
          <button
            className={`notification-list__item ${!item.read_at ? "is-unread" : ""}`}
            type="button"
            onClick={() => onSelect(item)}
          >
            <span className="notification-list__content">
              <span className="notification-list__title">{item.title}</span>
              <time className="notification-list__time">{formatNotificationTime(item.created_at)}</time>
            </span>
            {!item.read_at && <span className="notification-list__dot" aria-label="Chưa đọc" />}
          </button>
        </li>
      ))}
    </ul>
  );
}
