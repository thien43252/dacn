import { type ReactNode, useEffect, useRef } from "react";

import { AgentIcon } from "./AgentIcon";

interface ModalProps {
  title: string;
  eyebrow: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  busy?: boolean;
  /** Buttons shown in the header, before the close button. */
  actions?: ReactNode;
  className?: string;
}

export function Modal({ title, eyebrow, onClose, children, footer, wide = false, busy = false, actions, className = "" }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.querySelector<HTMLElement>("input, textarea, select, button:not(.ca-modal__close)")?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  return (
    <div className="ca-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <div
        className={`ca-modal ${wide ? "ca-modal--wide" : ""} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ca-modal-title"
        aria-busy={busy}
        ref={panelRef}
      >
        <header className="ca-modal__header">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h2 id="ca-modal-title">{title}</h2>
          </div>
          {actions && <div className="ca-modal__actions">{actions}</div>}
          <button className="icon-button ca-modal__close" type="button" onClick={onClose} disabled={busy} aria-label="Đóng">
            <AgentIcon name="x" />
          </button>
        </header>
        <div className="ca-modal__body">{children}</div>
        {footer && <footer className="ca-modal__footer">{footer}</footer>}
      </div>
    </div>
  );
}
