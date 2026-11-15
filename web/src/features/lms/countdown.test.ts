import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  calculateRemainingMs,
  formatRemainingTime,
  CountdownTimer,
} from "./countdown";

describe("countdown utility", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("calculateRemainingMs", () => {
    it("returns null when deadlineAt is null or undefined", () => {
      expect(calculateRemainingMs(null, "2026-11-16T10:00:00Z")).toBeNull();
      expect(calculateRemainingMs(undefined, "2026-11-16T10:00:00Z")).toBeNull();
    });

    it("calculates remaining ms correctly when client and server clocks match", () => {
      const fetchTime = new Date("2026-11-16T10:00:00Z").getTime();
      const serverNow = "2026-11-16T10:00:00Z";
      const deadline = "2026-11-16T10:30:00Z"; // 30 minutes later = 1,800,000 ms

      // At fetch time
      const remaining = calculateRemainingMs(deadline, serverNow, fetchTime, fetchTime);
      expect(remaining).toBe(30 * 60 * 1000);

      // 10 minutes later on client
      const later = fetchTime + 10 * 60 * 1000;
      const remainingLater = calculateRemainingMs(deadline, serverNow, fetchTime, later);
      expect(remainingLater).toBe(20 * 60 * 1000);
    });

    it("adjusts for clock skew when client clock is ahead of server", () => {
      // Server is at 10:00:00, but client clock was set to 10:05:00 (+5 mins ahead)
      const fetchTime = new Date("2026-11-16T10:05:00Z").getTime();
      const serverNow = "2026-11-16T10:00:00Z";
      const deadline = "2026-11-16T10:30:00Z";

      // Even though client clock says 10:05, server time is 10:00, so remaining should be 30 mins
      const remaining = calculateRemainingMs(deadline, serverNow, fetchTime, fetchTime);
      expect(remaining).toBe(30 * 60 * 1000);
    });

    it("adjusts for clock skew when client clock is behind server", () => {
      // Server is at 10:00:00, but client clock was set to 09:50:00 (-10 mins behind)
      const fetchTime = new Date("2026-11-16T09:50:00Z").getTime();
      const serverNow = "2026-11-16T10:00:00Z";
      const deadline = "2026-11-16T10:30:00Z";

      // Server time is 10:00, so remaining should be 30 mins
      const remaining = calculateRemainingMs(deadline, serverNow, fetchTime, fetchTime);
      expect(remaining).toBe(30 * 60 * 1000);
    });

    it("clamps to 0 when deadline has already passed", () => {
      const fetchTime = new Date("2026-11-16T10:35:00Z").getTime();
      const serverNow = "2026-11-16T10:35:00Z";
      const deadline = "2026-11-16T10:30:00Z";

      expect(calculateRemainingMs(deadline, serverNow, fetchTime, fetchTime)).toBe(0);
    });
  });

  describe("formatRemainingTime", () => {
    it("handles null", () => {
      expect(formatRemainingTime(null)).toBe("Không giới hạn");
    });

    it("handles 0 or negative values", () => {
      expect(formatRemainingTime(0)).toBe("00:00");
      expect(formatRemainingTime(-500)).toBe("00:00");
    });

    it("formats minutes and seconds", () => {
      expect(formatRemainingTime(65 * 1000)).toBe("01:05");
      expect(formatRemainingTime(5 * 60 * 1000 + 30 * 1000)).toBe("05:30");
    });

    it("formats hours, minutes and seconds", () => {
      expect(formatRemainingTime((3600 + 120 + 5) * 1000)).toBe("01:02:05");
      expect(formatRemainingTime(2 * 3600 * 1000)).toBe("02:00:00");
    });
  });

  describe("CountdownTimer", () => {
    it("fires timeout callback exactly once when reaching 0", () => {
      const startMs = new Date("2026-11-16T10:00:00Z").getTime();
      vi.setSystemTime(startMs);

      const serverNow = "2026-11-16T10:00:00Z";
      const deadlineAt = "2026-11-16T10:00:05Z"; // 5 seconds
      const onTimeout = vi.fn();
      const onTick = vi.fn();

      const timer = new CountdownTimer({
        deadlineAt,
        serverNow,
        fetchTimeMs: startMs,
        onTimeout,
        onTick,
      });

      timer.start(1000);

      // Initially
      expect(onTimeout).not.toHaveBeenCalled();
      expect(timer.isFired()).toBe(false);

      // Advance 2 seconds
      vi.advanceTimersByTime(2000);
      expect(onTimeout).not.toHaveBeenCalled();
      expect(timer.isFired()).toBe(false);

      // Advance another 3 seconds (reaches 5s, 0 remaining)
      vi.advanceTimersByTime(3000);
      expect(onTimeout).toHaveBeenCalledTimes(1);
      expect(timer.isFired()).toBe(true);

      // Advance further — callback must NOT be called again
      vi.advanceTimersByTime(5000);
      expect(onTimeout).toHaveBeenCalledTimes(1);

      timer.stop();
    });

    it("fires immediately if deadline is already 0 at start", () => {
      const startMs = new Date("2026-11-16T10:00:00Z").getTime();
      vi.setSystemTime(startMs);

      const onTimeout = vi.fn();
      const timer = new CountdownTimer({
        deadlineAt: "2026-11-16T09:59:00Z", // 1 minute in the past
        serverNow: "2026-11-16T10:00:00Z",
        fetchTimeMs: startMs,
        onTimeout,
      });

      timer.start(1000);
      expect(onTimeout).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);

      vi.advanceTimersByTime(2000);
      expect(onTimeout).toHaveBeenCalledTimes(1);
      timer.stop();
    });

    it("uses the server offset after fetch and submits only once across restarts", () => {
      const fetchedAt = new Date("2026-11-16T09:55:00Z").getTime();
      vi.setSystemTime(fetchedAt + 2000);
      const submit = vi.fn();
      const timer = new CountdownTimer({
        deadlineAt: "2026-11-16T10:00:05Z",
        serverNow: "2026-11-16T10:00:00Z",
        fetchTimeMs: fetchedAt,
        onTimeout: submit,
      });
      expect(timer.getRemainingMs()).toBe(3000);
      timer.start();
      vi.advanceTimersByTime(3000);
      expect(submit).toHaveBeenCalledTimes(1);
      timer.start();
      timer.check();
      vi.advanceTimersByTime(10000);
      expect(submit).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    });
  });
});
