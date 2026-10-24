import { type RefObject, useEffect, useRef } from "react";

import type { User } from "../auth/api";
import { roleLabels } from "../app/router";
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
}

const upcomingActions: { label: string; icon: IconName }[] = [
  { label: "Đổi mật khẩu", icon: "lock" },
  { label: "Báo lỗi / Góp ý", icon: "message" },
  { label: "Báo cáo của tôi", icon: "book" },
];

export function AccountPopover({ user, triggerRef, onClose, onLogout, guides = [], onReplayGuide }: AccountPopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

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
