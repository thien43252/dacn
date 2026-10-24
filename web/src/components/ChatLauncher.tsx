import { type Ref, useEffect, useRef, useState } from "react";

import { Mascot, type MascotMood } from "./Mascot";

type LauncherState = "idle" | "working" | "unread";

const HINTS: Record<LauncherState, string> = {
  idle: "Hỏi trợ lý",
  working: "Đang trả lời…",
  unread: "Có trả lời mới",
};

const MOODS: Record<LauncherState, MascotMood> = {
  idle: "idle",
  working: "writing",
  unread: "happy",
};

/**
 * Floating round assistant launcher: the fox peeks out of the circle and follows the cursor while idle, looks down
 * writing with a typing bubble while a reply is still running with the panel closed, and hops happily when a reply
 * finished while it was closed.
 */
export function ChatLauncher({ open, busy, onOpen, buttonRef }: {
  open: boolean;
  busy: boolean;
  onOpen: () => void;
  buttonRef?: Ref<HTMLButtonElement>;
}) {
  const [unread, setUnread] = useState(false);
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy && !open) setUnread(true);
    wasBusy.current = busy;
  }, [busy, open]);
  useEffect(() => {
    if (open) setUnread(false);
  }, [open]);

  const state: LauncherState = busy ? "working" : unread ? "unread" : "idle";
  return (
    <button
      ref={buttonRef}
      className={`chat-fab ${open ? "chat-fab--open" : ""}`}
      data-state={state}
      data-guide="chat-launcher"
      type="button"
      onClick={onOpen}
      aria-expanded={open}
      aria-label={state === "idle" ? "Mở trợ lý" : `Mở trợ lý, ${HINTS[state].replace("…", "").toLowerCase()}`}
    >
      <span className="chat-fab__hint" aria-hidden="true">{HINTS[state]}</span>
      <span className="chat-fab__bot">
        <Mascot character="fox" mood={MOODS[state]} track={!open} />
        {state === "working" && <span className="chat-fab__typing" aria-hidden="true"><i /><i /><i /></span>}
        {state === "unread" && <span className="chat-fab__badge" aria-hidden="true" />}
      </span>
    </button>
  );
}
