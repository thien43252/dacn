/** Timing, measured from the moment authentication succeeded unless stated otherwise. */
export const WELCOME_SHOW_AFTER_MS = 300;
export const WELCOME_MIN_VISIBLE_MS = 400; // from the moment the portal actually appeared
export const WELCOME_SLOW_AFTER_MS = 5000;
export const WELCOME_FADE_MS = 180;

export type WelcomePhase = "idle" | "waiting" | "visible" | "leaving";
export type WelcomeReadiness = "pending" | "ready" | "error";

export interface WelcomeTimelineState {
  phase: WelcomePhase;
  slow: boolean;
}

export interface WelcomeTimelineOptions {
  now?: () => number;
  reducedMotion?: () => boolean;
  /** Phase or slow-notice changed. */
  onChange: (state: WelcomeTimelineState) => void;
  /** The welcome is over (ready, error). Never called after `dispose`. */
  onFinish: () => void;
}

/**
 * The welcome's lifecycle without React: waiting (<300 ms, nothing shown) -> visible -> leaving (fade) -> finished.
 * The only inputs are the start time, the real readiness of the destination and disposal; no timer ever stands in
 * for readiness. A disposed timeline owns no timers and emits nothing, so a stale one cannot show or navigate.
 */
export function createWelcomeTimeline({ now = () => performance.now(), reducedMotion = () => false, onChange, onFinish }: WelcomeTimelineOptions) {
  let phase: WelcomePhase = "idle";
  let slow = false;
  let readiness: WelcomeReadiness = "pending";
  let shownAt = 0;
  let showTimer: ReturnType<typeof setTimeout> | undefined;
  let slowTimer: ReturnType<typeof setTimeout> | undefined;
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;
  let fadeTimer: ReturnType<typeof setTimeout> | undefined;

  const emit = () => onChange({ phase, slow });
  const clearLeave = () => { clearTimeout(leaveTimer); leaveTimer = undefined; };

  function clearAll() {
    clearTimeout(showTimer); clearTimeout(slowTimer); clearTimeout(fadeTimer); clearLeave();
    showTimer = slowTimer = fadeTimer = undefined;
  }

  function finish() {
    clearAll();
    phase = "idle";
    onFinish();
  }

  function leave() {
    leaveTimer = undefined;
    phase = "leaving";
    emit();
    fadeTimer = setTimeout(finish, reducedMotion() ? 0 : WELCOME_FADE_MS);
  }

  function evaluate() {
    if (phase === "idle" || phase === "leaving") return;
    if (readiness === "error") return finish(); // the error UI must never wait on the minimum duration or a fade
    if (readiness === "pending") return clearLeave();
    if (phase === "waiting") return finish(); // ready within 300 ms: straight to the destination
    if (leaveTimer === undefined) leaveTimer = setTimeout(leave, Math.max(0, shownAt + WELCOME_MIN_VISIBLE_MS - now()));
  }

  return {
    begin(startedAt: number) {
      clearAll();
      phase = "waiting";
      slow = false;
      showTimer = setTimeout(() => {
        showTimer = undefined;
        if (phase !== "waiting" || readiness !== "pending") return;
        phase = "visible";
        shownAt = now();
        emit();
      }, Math.max(0, startedAt + WELCOME_SHOW_AFTER_MS - now()));
      slowTimer = setTimeout(() => {
        slowTimer = undefined;
        if (phase === "idle") return;
        slow = true;
        emit();
      }, Math.max(0, startedAt + WELCOME_SLOW_AFTER_MS - now()));
      evaluate();
    },
    setReadiness(next: WelcomeReadiness) {
      readiness = next;
      evaluate();
    },
    dispose() {
      clearAll();
      phase = "idle";
    },
  };
}
