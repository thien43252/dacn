import { useEffect, useRef } from "react";

import { conversationsApi } from "../../api-client/chat";

const QUIET_EVENTS = new Set(["ping", "ready"]);

/**
 * Follows a conversation's event stream (`GET /api/chat/conversations/{id}/events?after=<seq>`) and calls `onChange`
 * when something arrives: a handoff answer, the asking agent's conclusion, a card, another member's message.
 * Reconnects with `after` = the highest seq seen, so a dropped connection loses nothing and replays nothing twice.
 */
export function useConversationEvents(conversationId: string | null, onChange: () => void): void {
  const changeRef = useRef(onChange);
  changeRef.current = onChange;

  useEffect(() => {
    if (!conversationId || typeof EventSource === "undefined") return;
    let source: EventSource | null = null;
    let lastSeq = 0;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let pending: ReturnType<typeof setTimeout> | null = null;
    let ready = false;

    const notify = () => {
      // Several events usually arrive together (status, answer, message): one reload is enough.
      if (pending) clearTimeout(pending);
      pending = setTimeout(() => changeRef.current(), 150);
    };

    const connect = () => {
      if (closed) return;
      ready = false;
      source = new EventSource(conversationsApi.eventsUrl(conversationId, lastSeq), { withCredentials: true });
      source.onmessage = (message) => {
        let event: { type?: string; seq?: number };
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        if (typeof event.seq === "number" && event.seq > lastSeq) lastSeq = event.seq;
        if (event.type === "ready") {
          ready = true;
          return;
        }
        if (!event.type || QUIET_EVENTS.has(event.type)) return;
        // The replay before "ready" is history the thread already has unless it was missed while disconnected.
        if (ready || lastSeq > 0) notify();
      };
      source.onerror = () => {
        source?.close();
        if (!closed) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      source?.close();
      if (retry) clearTimeout(retry);
      if (pending) clearTimeout(pending);
    };
  }, [conversationId]);
}
