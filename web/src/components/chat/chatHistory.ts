/**
 * Chat sessions kept in this browser, one list per signed-in identity (like the session list of Claude).
 *
 * The Platform holds a conversation only in its process memory, so this is what lets a reader come back to an old
 * chat after closing the tab or after a deploy: the transcript is shown again from here. A conversation the
 * Platform no longer knows is still readable, but a new message there is refused (the agents could not read the
 * turns above), and the reader opens a new chat instead.
 * Storage may be missing, full or blocked (private window, cleared site data), so every access is guarded and the
 * chat keeps working in memory when it fails.
 */

export interface StoredSession<M> {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  /** The Platform conversation this transcript belongs to, when a turn was sent. */
  conversationId?: string;
  messages: M[];
}

const PREFIX = "eduagent.chat.v1:";
export const MAX_SESSIONS = 30;
export const MAX_MESSAGES = 160;
const TITLE_CHARS = 60;

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : null;
  } catch {
    return null;
  }
}

export function storageKey(owner: string): string {
  return `${PREFIX}${owner}`;
}

/** Saved sessions of one identity, newest first; an unreadable entry reads as no history, never as an error. */
export function loadSessions<M>(owner: string): StoredSession<M>[] {
  const store = storage();
  if (!store) return [];
  try {
    const raw = store.getItem(storageKey(owner));
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is StoredSession<M> => Boolean(item && typeof item.id === "string" && Array.isArray(item.messages)))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

/** Write the list, dropping the oldest sessions when the browser runs out of room. Returns false if nothing fit. */
export function saveSessions<M>(owner: string, sessions: StoredSession<M>[]): boolean {
  const store = storage();
  if (!store) return false;
  let kept = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_SESSIONS);
  while (kept.length > 0) {
    try {
      store.setItem(storageKey(owner), JSON.stringify(kept));
      return true;
    } catch {
      kept = kept.slice(0, -1);
    }
  }
  try {
    store.removeItem(storageKey(owner));
  } catch {
    // Nothing else to do: the chat keeps working in memory.
  }
  return false;
}

/** A session's name: the start of the first thing the reader asked. */
export function sessionTitle(firstUserText: string | undefined): string {
  const text = (firstUserText || "").replace(/\s+/g, " ").trim();
  if (!text) return "Cuộc trò chuyện mới";
  return text.length > TITLE_CHARS ? `${text.slice(0, TITLE_CHARS - 1).trimEnd()}…` : text;
}

/** Put one session into the list (replacing its old copy) and keep only the newest messages of it. */
export function upsertSession<M>(sessions: StoredSession<M>[], session: StoredSession<M>): StoredSession<M>[] {
  const trimmed = { ...session, messages: session.messages.slice(-MAX_MESSAGES) };
  return [trimmed, ...sessions.filter((item) => item.id !== session.id)].sort((a, b) => b.updatedAt - a.updatedAt);
}

export function removeSession<M>(sessions: StoredSession<M>[], id: string): StoredSession<M>[] {
  return sessions.filter((item) => item.id !== id);
}

/** "Hôm nay", "Hôm qua", "7 ngày qua" or "Cũ hơn", for grouping the list the way chat apps do. */
export function sessionGroup(updatedAt: number, now: number = Date.now()): string {
  const day = (value: number) => {
    const date = new Date(value);
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  };
  const days = Math.round((day(now) - day(updatedAt)) / 86_400_000);
  if (days <= 0) return "Hôm nay";
  if (days === 1) return "Hôm qua";
  if (days < 7) return "7 ngày qua";
  return "Cũ hơn";
}

/** Time and full date, e.g. "07:37 17/10/2026": a bare time reads like a duration or another day's session. */
export function sessionTime(updatedAt: number): string {
  const date = new Date(updatedAt);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())} ${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}
