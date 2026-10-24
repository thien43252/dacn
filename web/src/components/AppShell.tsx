import { type ReactNode, useCallback, useRef, useState } from "react";

import { navigate, roleLabels } from "../app/router";
import { navigation } from "../app/routes";
import { useAuth } from "../auth/AuthContext";
import { GuideOverlay } from "../guide/GuideOverlay";
import { useGuide } from "../guide/useGuide";
import { AccountPopover } from "./AccountPopover";
import { ChatLauncher } from "./ChatLauncher";
import { ChatPanel } from "./ChatPanel";
import { Icon } from "./Icon";
import { Logo } from "./Logo";
import { ScreenBanner, toneOf } from "./ScreenBanner";
import "../styles/workspace-readability.css";
import "../styles/studio-screens.css";

interface AppShellProps {
  pathname: string;
  /** Route pattern the pathname matched; screen art and tone are keyed by it so `/classes/:id` shares one look. */
  pattern: string;
  title: string;
  eyebrow?: string;
  description?: string;
  children: ReactNode;
  /** Fits the page to the viewport height so a canvas-style route never needs page scrolling. */
  fillHeight?: boolean;
}

export function AppShell({ pathname, pattern, title, eyebrow, description, children, fillHeight = false }: AppShellProps) {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(() => sessionStorage.getItem("sidebar-collapsed") === "true");
  const [chatOpen, setChatOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);
  const chatTriggerRef = useRef<HTMLButtonElement>(null);
  const closeAccount = useCallback(() => setAccountOpen(false), []);
  const guide = useGuide(user, pathname);

  if (!user) return null;

  function toggleSidebar() {
    setCollapsed((current) => {
      const next = !current;
      sessionStorage.setItem("sidebar-collapsed", String(next));
      return next;
    });
  }

  async function signOut() {
    await logout();
    navigate("/login", true);
  }

  return (
    <div className={`workspace-shell workspace-shell--${user.role}`}>
      <aside className={`sidebar frosted ${collapsed ? "sidebar--collapsed" : ""}`}>
        <div className="sidebar__top">
          <Logo compact={collapsed} />
          <button
            className="icon-button sidebar__toggle"
            onClick={toggleSidebar}
            type="button"
            aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            aria-expanded={!collapsed}
            title={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
          >
            <Icon name="panel" />
          </button>
        </div>
        <nav className="sidebar__nav" aria-label="Điều hướng chính">
          {navigation[user.role].map((item) => {
            // Sub-pages (e.g. /teacher/classes/:id) keep their section highlighted.
            const active = pathname === item.path || pathname.startsWith(`${item.path}/`);
            return (
              <button
                key={item.path}
                data-guide={`nav-${item.path.split("/").pop()}`}
                className={active ? "is-active" : ""}
                type="button"
                onClick={() => navigate(item.path)}
                aria-current={pathname === item.path ? "page" : active ? "location" : undefined}
                aria-label={item.label}
                title={collapsed ? item.label : undefined}
              >
                <Icon name={item.icon} />
                {!collapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar__profile">
          <button
            ref={accountTriggerRef}
            className={`sidebar__account ${accountOpen ? "is-open" : ""}`}
            type="button"
            onClick={() => setAccountOpen((current) => !current)}
            aria-haspopup="dialog"
            aria-expanded={accountOpen}
            aria-controls={accountOpen ? "account-popover" : undefined}
            aria-label="Mở thông tin tài khoản"
            title={collapsed ? user.name : undefined}
          >
            <span className="profile-avatar" aria-hidden="true">{user.name.charAt(0).toUpperCase()}</span>
            {!collapsed && <div><strong>{user.name}</strong><small>{roleLabels[user.role]}</small></div>}
          </button>
          <button className="icon-button" type="button" onClick={signOut} aria-label="Đăng xuất"><Icon name="logout" /></button>
        </div>
      </aside>

      {accountOpen && (
        <AccountPopover
          user={user}
          triggerRef={accountTriggerRef}
          onClose={closeAccount}
          onLogout={signOut}
          guides={guide.canReplay && guide.overview ? [guide.overview, ...guide.areaGuides] : []}
          onReplayGuide={(item) => { closeAccount(); guide.replay(item); }}
        />
      )}

      <main className={`workspace-main ${fillHeight ? "workspace-main--fill" : ""}`} data-tone={toneOf(pattern)} data-screen={pattern}>
        <ScreenBanner pathname={pattern} title={title} eyebrow={eyebrow} description={description} compact={fillHeight} />
        <div className="workspace-content">{children}</div>
      </main>

      {user.role !== "admin" && (
        <>
          <ChatPanel
            open={chatOpen}
            onClose={() => {
              setChatOpen(false);
              requestAnimationFrame(() => chatTriggerRef.current?.focus());
            }}
          />
          <ChatLauncher buttonRef={chatTriggerRef} open={chatOpen} busy={false} onOpen={() => setChatOpen(true)} />
        </>
      )}
      <GuideOverlay session={guide.session} pathname={pathname} onFinish={guide.finish} />
    </div>
  );
}
