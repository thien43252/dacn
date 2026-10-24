/**
 * Small confirmation dialog for actions that cannot be undone.
 *
 * Confirming a plan version freezes it against a hash, so the student sees exactly what is being frozen
 * before they commit to it.
 */

import { type ReactNode, useEffect, useRef } from "react";

import { Icon } from "../../components/Icon";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  confirmDisabled?: boolean;
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Huỷ",
  busy = false,
  confirmDisabled = false,
  children,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    confirmRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, open]);

  if (!open) return null;

  return (
    <div className="dialog-backdrop" onClick={onCancel} role="presentation">
      <div
        aria-labelledby="dialog-title"
        aria-modal="true"
        className="dialog frosted"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="dialog__head">
          <span className="soft-icon">
            <Icon name="lock" />
          </span>
          <div>
            <h2 id="dialog-title">{title}</h2>
            {description && <p>{description}</p>}
          </div>
        </div>

        {children && <div className="dialog__body">{children}</div>}

        <div className="dialog__actions">
          <button className="button button--ghost" disabled={busy} onClick={onCancel} type="button">
            {cancelLabel}
          </button>
          <button
            className="button button--primary"
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
            ref={confirmRef}
            type="button"
          >
            {busy ? <span className="button-spinner" /> : <Icon name="check" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
