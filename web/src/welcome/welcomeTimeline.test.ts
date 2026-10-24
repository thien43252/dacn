import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WELCOME_FADE_MS, createWelcomeTimeline } from "./welcomeTimeline";

// Fake timers also drive Date, so the clock moves together with each timer that fires.
const now = () => Date.now();
function advance(ms: number) { vi.advanceTimersByTime(ms); }

function setup(reduced = false) {
  const changes: Array<{ phase: string; slow: boolean }> = [];
  const finish = vi.fn();
  const timeline = createWelcomeTimeline({ now, reducedMotion: () => reduced, onChange: (s) => changes.push(s), onFinish: finish });
  timeline.begin(Date.now());
  return { timeline, changes, finish, phase: () => changes.at(-1)?.phase };
}

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(0); });
afterEach(() => vi.useRealTimers());

describe("welcome timeline", () => {
  it("skips the portal when the destination is ready within 300 ms", () => {
    const { timeline, changes, finish } = setup();
    advance(250);
    timeline.setReadiness("ready");
    expect(finish).toHaveBeenCalledTimes(1);
    advance(1000);
    expect(changes).toEqual([]);
  });

  it("shows the portal after 300 ms while pending", () => {
    const { changes } = setup();
    advance(299);
    expect(changes).toEqual([]);
    advance(1);
    expect(changes.at(-1)).toEqual({ phase: "visible", slow: false });
  });

  it("holds 400 ms from when the portal appeared, then fades, then finishes", () => {
    const { timeline, phase, finish } = setup();
    advance(300); // portal appears at 300
    advance(200); // destination becomes ready 200 ms after it appeared
    timeline.setReadiness("ready");
    advance(199);
    expect(phase()).toBe("visible");
    advance(1); // 400 ms after it appeared
    expect(phase()).toBe("leaving");
    advance(WELCOME_FADE_MS - 1);
    expect(finish).not.toHaveBeenCalled();
    advance(1);
    expect(finish).toHaveBeenCalledTimes(1);
  });

  it("adds no extra wait when ready long after the minimum has passed", () => {
    const { timeline, phase } = setup();
    advance(2000);
    timeline.setReadiness("ready");
    advance(1);
    expect(phase()).toBe("leaving");
  });

  it("adds the slow notice 5 s after the start", () => {
    const { changes } = setup();
    advance(4999);
    expect(changes.at(-1)?.slow).toBe(false);
    advance(1);
    expect(changes.at(-1)).toEqual({ phase: "visible", slow: true });
  });

  it("ends immediately on error, inside the minimum duration", () => {
    const { timeline, finish } = setup();
    advance(350);
    timeline.setReadiness("error");
    expect(finish).toHaveBeenCalledTimes(1);
  });

  it("ends immediately on error while a pending leave is scheduled", () => {
    const { timeline, finish } = setup();
    advance(300);
    timeline.setReadiness("ready");
    advance(100);
    timeline.setReadiness("error");
    expect(finish).toHaveBeenCalledTimes(1);
    advance(10_000);
    expect(finish).toHaveBeenCalledTimes(1);
  });

  it("keeps waiting if readiness is lost before the portal starts leaving", () => {
    const { timeline, phase } = setup();
    advance(300);
    timeline.setReadiness("ready");
    advance(100);
    timeline.setReadiness("pending");
    advance(1000);
    expect(phase()).toBe("visible");
  });

  it("drops the fade under reduced motion", () => {
    const { timeline, finish } = setup(true);
    advance(300);
    advance(400);
    timeline.setReadiness("ready");
    advance(2);
    expect(finish).toHaveBeenCalledTimes(1);
  });

  it("emits nothing and finishes nothing after dispose", () => {
    const { timeline, changes, finish } = setup();
    timeline.dispose();
    timeline.setReadiness("ready");
    advance(10_000);
    expect(changes).toEqual([]);
    expect(finish).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("a disposed visible timeline cannot fade or finish later", () => {
    const { timeline, finish } = setup();
    advance(300);
    timeline.setReadiness("ready");
    timeline.dispose();
    advance(10_000);
    expect(finish).not.toHaveBeenCalled();
  });
});
