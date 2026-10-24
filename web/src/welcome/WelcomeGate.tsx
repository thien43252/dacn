import { type ReactNode, createContext, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { useLocation } from "../app/router";
import { useAuth } from "../auth/AuthContext";
import { createPortal } from "react-dom";

import { WelcomeCover, WelcomePortal } from "./WelcomePortal";
import { portalForRole } from "./portalAssets";
import { type EssentialStatus, ReadinessContext, type ReadinessReporter } from "./readiness";
import { endWelcome, getWelcomeSession, subscribeWelcome } from "./welcomeStore";
import { type WelcomeTimelineState, createWelcomeTimeline } from "./welcomeTimeline";

const BlockingContext = createContext(false);

/** True while a post-login welcome is still pending or showing; onboarding guides wait for it to end. */
export function useWelcomeBlocking(): boolean {
  return useContext(BlockingContext);
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function aggregate(settled: boolean, entries: Iterable<EssentialStatus>): EssentialStatus {
  if (!settled) return "pending";
  let pending = false;
  for (const status of entries) {
    if (status === "error") return "error";
    if (status === "pending") pending = true;
  }
  return pending ? "pending" : "ready";
}

/**
 * Wraps the routed app. It never delays mounting: the destination renders and loads immediately underneath, and the
 * portal is only an overlay that appears if essential data is still pending after 300 ms. Readiness is the real
 * state reported by the screen (`useEssentialData`), not a timer.
 */
export function WelcomeGate({ children }: { children: ReactNode }) {
  const session = useSyncExternalStore(subscribeWelcome, getWelcomeSession, getWelcomeSession);
  const { status: authStatus, user } = useAuth();
  const { pathname } = useLocation();

  const entries = useRef(new Map<string, EssentialStatus>());
  const [tick, setTick] = useState(0);
  const reporter = useMemo<ReadinessReporter>(() => ({
    report: (id, status) => {
      if (entries.current.get(id) === status) return;
      entries.current.set(id, status);
      setTick((value) => value + 1);
    },
    remove: (id) => {
      if (entries.current.delete(id)) setTick((value) => value + 1);
    },
  }), []);

  const [view, setView] = useState<{ id: number; state: WelcomeTimelineState } | null>(null);
  const current = view && session && view.id === session.id ? view.state : null;
  const phase = current?.phase ?? "waiting";

  // Destination settled = authenticated as the session's user and no longer on the auth form, so the target (or its
  // forbidden/not-found screen) is the committed route. Pages then report their own essential data.
  const settled = Boolean(session) && authStatus === "authenticated" && user?.id === session?.userId
    && pathname !== "/login" && pathname !== "/register";

  const sessionId = session?.id ?? null;
  const startedAt = session?.startedAt ?? 0;
  const role = session?.role ?? null;
  const sessionUserId = session?.userId ?? null;
  const seenAuthenticated = useRef<number | null>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const timeline = useRef<ReturnType<typeof createWelcomeTimeline> | null>(null);

  // Per sign-in: load only this role's artwork and run one timeline. Cleanup disposes it, so unmount, logout or a
  // replacing sign-in can never leave a stale timer that shows the portal or ends the new welcome.
  useEffect(() => {
    if (sessionId === null) return;
    const id = sessionId;
    const theme = portalForRole(role);
    if (theme) { const image = new Image(); image.decoding = "async"; image.src = theme.src; }
    const instance = createWelcomeTimeline({
      reducedMotion: prefersReducedMotion,
      onChange: (state) => {
        if (state.phase === "visible") restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setView({ id, state });
      },
      onFinish: endWelcome,
    });
    timeline.current = instance;
    instance.begin(startedAt);
    instance.setReadiness(aggregate(settledRef.current, entries.current.values()));
    return () => { instance.dispose(); if (timeline.current === instance) timeline.current = null; };
  }, [sessionId, startedAt, role]);

  // Read in effects, never in render: a screen registers in a layout effect, so only after commit is the registry
  // complete. Evaluating during the render that first mounts the destination would see an empty registry as "ready".
  const settledRef = useRef(settled);
  settledRef.current = settled;
  useEffect(() => {
    timeline.current?.setReadiness(aggregate(settled, entries.current.values()));
  }, [sessionId, settled, tick]);

  // Signing out (or an expired session) while the welcome is open ends it; nothing may resurface afterwards.
  useEffect(() => {
    if (sessionId === null) return;
    if (authStatus === "authenticated" && user?.id === sessionUserId) seenAuthenticated.current = sessionId;
    else if (authStatus === "guest" && seenAuthenticated.current === sessionId) endWelcome();
  }, [sessionId, sessionUserId, authStatus, user?.id]);

  // From the sign-in frame on, the destination is covered: an opaque neutral cover while deciding (first 300 ms),
  // then the portal. It mounts and loads underneath, inert, and is revealed only when the welcome ends.
  const overlayShown = session !== null;
  const portalShown = session !== null && (phase === "visible" || phase === "leaving");
  const wasShown = useRef(false);
  useEffect(() => {
    if (overlayShown) { wasShown.current = true; return; }
    if (!wasShown.current) return;
    wasShown.current = false;
    // Interaction is back: return focus to where it was, or to the main landmark when that element is gone.
    const previous = restoreFocus.current;
    restoreFocus.current = null;
    if (previous && previous.isConnected && previous !== document.body) { previous.focus({ preventScroll: true }); return; }
    const main = document.querySelector<HTMLElement>("main");
    if (main) { if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1"); main.focus({ preventScroll: true }); }
  }, [overlayShown]);

  return (
    <ReadinessContext.Provider value={reporter}>
      <BlockingContext.Provider value={session !== null}>
        <div className="welcome-content" inert={overlayShown}>{children}</div>
        {overlayShown && session && createPortal(
          portalShown
            ? <WelcomePortal theme={portalForRole(session.role)} name={session.name} leaving={phase === "leaving"} slow={Boolean(current?.slow)} />
            : <WelcomeCover />,
          document.body,
        )}
      </BlockingContext.Provider>
    </ReadinessContext.Provider>
  );
}
