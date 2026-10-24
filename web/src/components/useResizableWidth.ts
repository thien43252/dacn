import { type KeyboardEvent, type PointerEvent, useRef, useState } from "react";

export const MIN_PANEL_WIDTH = 340;
export const MAX_PANEL_WIDTH = 1100;
const KEYBOARD_STEP = 24;

function clamp(value: number): number {
  return Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, Math.round(value)));
}

function readStored(key: string): number | null {
  try {
    const raw = Number(window.localStorage.getItem(key));
    return Number.isFinite(raw) && raw > 0 ? clamp(raw) : null;
  } catch {
    return null;
  }
}

function store(key: string, value: number | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, String(value));
  } catch {
    // Storage can be blocked (private window); the width then only lasts for this page view.
  }
}

/**
 * Width of a right-docked panel that the user drags by its left edge. `width` stays null until the user
 * resizes, so the stylesheet default applies; the choice is remembered per browser under `storageKey`.
 */
export function useResizableWidth(storageKey: string) {
  const [width, setWidth] = useState<number | null>(() => readStored(storageKey));
  const [resizing, setResizing] = useState(false);
  const drag = useRef<{ startX: number; startWidth: number; latest: number } | null>(null);

  function commit(next: number | null) {
    setWidth(next);
    store(storageKey, next);
  }

  const separatorProps = {
    role: "separator" as const,
    "aria-orientation": "vertical" as const,
    "aria-label": "Kéo để đổi độ rộng trợ lý",
    "aria-valuemin": MIN_PANEL_WIDTH,
    "aria-valuemax": MAX_PANEL_WIDTH,
    "aria-valuenow": width ?? undefined,
    title: "Kéo để đổi độ rộng · bấm đúp để đặt lại",
    tabIndex: 0,
    onPointerDown(event: PointerEvent<HTMLDivElement>) {
      const panel = event.currentTarget.parentElement;
      if (!panel) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      const startWidth = panel.getBoundingClientRect().width;
      drag.current = { startX: event.clientX, startWidth, latest: startWidth };
      setResizing(true);
    },
    onPointerMove(event: PointerEvent<HTMLDivElement>) {
      if (!drag.current) return;
      // The panel is docked on the right, so dragging its left edge towards the left widens it.
      drag.current.latest = clamp(drag.current.startWidth + (drag.current.startX - event.clientX));
      setWidth(drag.current.latest);
    },
    onPointerUp() {
      if (!drag.current) return;
      // A click without a drag keeps the stylesheet default instead of freezing it as a chosen width.
      if (drag.current.latest !== drag.current.startWidth) store(storageKey, drag.current.latest);
      drag.current = null;
      setResizing(false);
    },
    onPointerCancel() {
      drag.current = null;
      setResizing(false);
    },
    onDoubleClick() {
      commit(null);
    },
    onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const current = width ?? event.currentTarget.parentElement?.getBoundingClientRect().width ?? MIN_PANEL_WIDTH;
      commit(clamp(current + (event.key === "ArrowLeft" ? KEYBOARD_STEP : -KEYBOARD_STEP)));
    },
  };

  return { width, resizing, separatorProps };
}
