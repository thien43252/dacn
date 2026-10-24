import { GUIDE_VERSION, type GuideRole } from "./guideSteps";

/**
 * Per-account, per-role, per-version record that this browser has seen a guide. It is a demo fallback: it cannot tell
 * a returning account from a first visit on a new or cleared browser, so it is "first visit here", not "new account".
 * The overview keeps the bare key; every contextual guide has its own record under `:ctx:{id}`.
 */
export interface GuideRecord {
  status: "completed" | "dismissed";
  version: number;
  at: string;
  /** Index of the step reached when the guide ended. */
  step: number;
}

export type GuideRead = { available: true; record: GuideRecord | null } | { available: false };

export const OVERVIEW_ID = "overview";

export function guideKey(role: GuideRole, userId: string, guideId: string = OVERVIEW_ID): string {
  const base = `eduagent.guide.v${GUIDE_VERSION}:${role}:${userId}`;
  return guideId === OVERVIEW_ID ? base : `${base}:ctx:${guideId}`;
}

export function readGuide(role: GuideRole, userId: string, guideId: string = OVERVIEW_ID): GuideRead {
  try {
    const raw = window.localStorage.getItem(guideKey(role, userId, guideId));
    if (raw === null) return { available: true, record: null };
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && (parsed as GuideRecord).version === GUIDE_VERSION) {
      return { available: true, record: parsed as GuideRecord };
    }
    return { available: true, record: null };
  } catch {
    // Storage blocked or unreadable: never auto-start, since the guide could not be remembered.
    return { available: false };
  }
}

export function writeGuide(role: GuideRole, userId: string, guideId: string, status: GuideRecord["status"], step: number): void {
  try {
    const record: GuideRecord = { status, version: GUIDE_VERSION, at: new Date().toISOString(), step };
    window.localStorage.setItem(guideKey(role, userId, guideId), JSON.stringify(record));
  } catch {
    // Not persisted; the guide simply may show again.
  }
}
