import { type RefObject, useEffect, useRef, useState } from "react";

import type { NotificationItem } from "../api-client/lms";
import type { User } from "../auth/api";
import { navigate, roleLabels } from "../app/router";
import { NotificationList, type NotificationsState } from "../features/lms/notifications";
import type { GuideDef } from "../guide/guideSteps";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";

interface AccountPopoverProps {
  user: User;
  triggerRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onLogout: () => void;
  /** Student/teacher only: the overview plus the guides of the open screen, offered as "view again" entries. */
  guides?: GuideDef[];
  onReplayGuide?: (guide: GuideDef) => void;
  /** Absent for roles without LMS notifications (admin). */
  notifications?: NotificationsState;
}

const upcomingActions: { label: string; icon: IconName }[] = [
  { label: "Đổi mật khẩu", icon: "lock" },
  { label: "Báo lỗi / Góp ý", icon: "message" },
  { label: "Báo cáo của tôi", icon: "book" },
];

export function AccountPopover({ user, triggerRef, onClose, onLogout, guides = [], onReplayGuide, notifications }: AccountPopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<"menu" | "notifications">("menu");

  useEffect(() => {
    panelRef.current?.focus();
  }, [view]);

  function openNotification(item: NotificationItem) {
    void notifications?.markRead(item);
    onClose();
    if (item.link) navigate(item.link);
  }

  if (view === "notifications" && notifications) {
    return (
      <div
        ref={panelRef}
        className="account-popover account-popover--wide"
        role="dialog"
        aria-label="Thông báo"
        tabIndex={-1}
        id="account-popover"
      >
        <header className="account-popover__subheader">
          <button className="icon-button" type="button" onClick={() => setView("menu")} aria-label="Quay lại">
            <Icon name="chevron-left" />
          </button>
          <strong>Thông báo</strong>
          {notifications.unreadCount > 0 && (
            <button className="account-popover__link" type="button" onClick={() => void notifications.markAllRead()}>
              Đánh dấu đã đọc tất cả
            </button>
          )}
        </header>
        <div className="account-popover__scroll">
          <NotificationList items={notifications.items} onSelect={openNotification} />
        </div>
      </div>
    );
  }

  useEffect(() => {
    function handlePointer(event: MouseEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      onClose();
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      onClose();
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose, triggerRef]);

  return (
    <div
      ref={panelRef}
      className="account-popover"
      role="dialog"
      aria-label="Thông tin tài khoản"
      tabIndex={-1}
      id="account-popover"
    >
      <header className="account-popover__header">
        <span className="profile-avatar" aria-hidden="true">{user.name.charAt(0).toUpperCase()}</span>
        <div>
          <strong>{user.name}</strong>
          <small>{user.email}</small>
        </div>
      </header>

      <dl className="account-popover__details">
        <div>
          <dt>Vai trò</dt>
          <dd><Icon name="user" /> {roleLabels[user.role]}</dd>
        </div>
      </dl>

      <ul className="account-popover__menu">
        {notifications && (
          <li>
            <button type="button" onClick={() => setView("notifications")}>
              <Icon name="bell" /> Thông báo
              {notifications.unreadCount > 0 && (
                <span className="account-popover__count" aria-label={`${notifications.unreadCount} chưa đọc`}>
                  {notifications.unreadCount > 99 ? "99+" : notifications.unreadCount}
                </span>
              )}
              <Icon name="chevron-right" className="account-popover__chevron" />
            </button>
          </li>
        )}
        {upcomingActions.map((action) => (
          <li key={action.label}>
            <button type="button" disabled title="Chưa khả dụng">
              <Icon name={action.icon} /> {action.label}
              <span className="account-popover__soon">Chưa khả dụng</span>
            </button>
          </li>
        ))}
        {onReplayGuide && guides.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => onReplayGuide(item)}>
              <Icon name="sparkles" /> {item.kind === "overview" ? "Xem lại hướng dẫn tổng quan" : `Hướng dẫn: ${item.label}`}
            </button>
          </li>
        ))}
        <li>
          <button type="button" className="account-popover__logout" onClick={onLogout}>
            <Icon name="logout" /> Đăng xuất
          </button>
        </li>
      </ul>
    </div>
  );
}
