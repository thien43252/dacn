import { useCallback, useEffect, useRef, useState } from "react";

import { hasNavigationGuard, navigate, useLocation } from "../app/router";
import type { User } from "../auth/api";
import { GUIDE_HOME, type GuideDef, type GuideRole, type GuideStep, contextGuidesFor, isGuideRole, overviewOf } from "./guideSteps";
import { OVERVIEW_ID, readGuide, writeGuide } from "./guideStorage";
import { useWelcomeBlocking } from "../welcome/WelcomeGate";

export interface GuideSession {
  role: GuideRole;
  userId: string;
  guide: GuideDef;
  steps: GuideStep[];
}

export function findTarget(name: string): HTMLElement | null {
  const element = document.querySelector<HTMLElement>(`[data-guide="${name}"]`);
  if (!element || element.getClientRects().length === 0) return null;
  return getComputedStyle(element).visibility === "hidden" ? null : element;
}

/** A modal-ish surface (account menu, confirm dialog) or the open assistant panel: the guide waits for them. */
export function isOtherSurfaceOpen(): boolean {
  const dialog = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]:not([data-guide-card])'))
    .some((element) => element.getClientRects().length > 0);
  return dialog || document.querySelector(".chat-panel--open") !== null;
}

const presentSteps = (guide: GuideDef) => guide.steps.filter((step) => findTarget(step.target));

/** Waits (bounded) for the targets to render, then keeps only the steps whose element exists. */
function resolveSteps(steps: GuideStep[], cancelled: () => boolean): Promise<GuideStep[]> {
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = () => {
      if (cancelled()) return resolve([]);
      const present = steps.filter((step) => findTarget(step.target));
      if (present.length === steps.length || Date.now() - started > 1500) return resolve(present);
      window.setTimeout(tick, 100);
    };
    tick();
  });
}

/**
 * Owns when a guide starts. The overview auto-starts once per account/role/version on the role's home route; a
 * contextual guide auto-starts once, the first time that area is open, but only after the overview was completed (a
 * skipped overview means "no tour", though every guide stays available from the help menu). Only one guide runs at a
 * time, never over an open dialog or an unsaved editor, and only once the screen's targets have settled. The guide
 * only ever reads the page.
 */
export function useGuide(user: User | null, pathname: string) {
  const [session, setSession] = useState<GuideSession | null>(null);
  const sessionRef = useRef<GuideSession | null>(null);
  sessionRef.current = session;
  // The query matters too: opening a submission on the approval screen is what makes the review guide's targets appear.
  const { search } = useLocation();
  const cancelRef = useRef<() => void>(() => undefined);
  const pendingRef = useRef<GuideDef | null>(null);
  const role = user && isGuideRole(user.role) ? user.role : null;
  const userId = user?.id ?? null;
  // No guide starts while the post-login welcome is pending or showing; it begins once the portal has ended.
  const welcomeActive = useWelcomeBlocking();

  const begin = useCallback((guide: GuideDef) => {
    if (!role || !userId) return;
    cancelRef.current();
    let cancelled = false;
    cancelRef.current = () => { cancelled = true; };
    void resolveSteps(guide.steps, () => cancelled).then((steps) => {
      if (!cancelled && steps.length > 0) setSession({ role, userId, guide, steps });
    });
  }, [role, userId]);

  useEffect(() => {
    // Leaving the page (or signing out) ends a guide and cancels one that is still resolving; nothing is stored.
    return () => { cancelRef.current(); setSession(null); };
  }, [pathname, userId]);

  useEffect(() => {
    if (!role || !userId || welcomeActive) return;
    const pending = pendingRef.current;
    if (pending && pending.route === pathname) {
      pendingRef.current = null;
      begin(pending);
      return;
    }
    const overview = readGuide(role, userId, OVERVIEW_ID);
    if (!overview.available) return;
    const candidates: GuideDef[] = [];
    if (pathname === GUIDE_HOME[role] && !overview.record) candidates.push(overviewOf(role));
    else if (overview.record?.status === "completed") {
      for (const guide of contextGuidesFor(role, pathname)) {
        const read = readGuide(role, userId, guide.id);
        if (read.available && !read.record) candidates.push(guide);
      }
    }
    if (candidates.length === 0) return;
    // Start once the screen has stopped changing: the same set of targets on two polls in a row.
    let tries = 0;
    let previous = "";
    const timer = window.setInterval(() => {
      tries += 1;
      if (tries > 60) return window.clearInterval(timer);
      if (sessionRef.current || isOtherSurfaceOpen() || hasNavigationGuard()) return;
      const ready = candidates.find((guide) => presentSteps(guide).length > 0);
      if (!ready) return;
      const key = `${ready.id}:${presentSteps(ready).map((step) => step.id).join(",")}`;
      if (key !== previous) { previous = key; return; }
      window.clearInterval(timer);
      begin(ready);
    }, 500);
    return () => window.clearInterval(timer);
  }, [role, userId, pathname, search, begin, welcomeActive]);

  /** Starts a guide on demand (help menu). The overview lives on the home route, so Replay may go there first. */
  const replay = useCallback((guide: GuideDef) => {
    if (!role) return;
    if (pathname === guide.route) begin(guide);
    else {
      pendingRef.current = guide;
      navigate(guide.route);
    }
  }, [role, pathname, begin]);

  const finish = useCallback((status: "completed" | "dismissed", step: number) => {
    const current = sessionRef.current;
    if (current) writeGuide(current.role, current.userId, current.guide.id, status, step);
    setSession(null);
  }, []);

  return {
    session,
    replay,
    finish,
    canReplay: role !== null,
    overview: role ? overviewOf(role) : null,
    areaGuides: role ? contextGuidesFor(role, pathname) : [],
  };
}
