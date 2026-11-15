/**
 * Countdown timer utility for LMS quizzes.
 * Calculates remaining time based on deadline_at and the clock skew between server_now and client Date.now() at fetch time.
 * Fires the callback exactly once when the remaining time reaches 0.
 */

import { useEffect, useRef, useState } from "react";

/**
 * Calculates remaining milliseconds until deadline based on server time synchronization.
 * Returns null if there is no deadline.
 */
export function calculateRemainingMs(
  deadlineAt?: string | Date | null,
  serverNow?: string | Date | null,
  fetchTimeMs?: number,
  nowMs?: number,
): number | null {
  if (!deadlineAt) return null;

  const deadlineMs = new Date(deadlineAt).getTime();
  if (Number.isNaN(deadlineMs)) return null;

  const currentNow = nowMs ?? Date.now();
  const fetchedAt = fetchTimeMs ?? currentNow;

  let offset = 0;
  if (serverNow) {
    const sNow = new Date(serverNow).getTime();
    if (!Number.isNaN(sNow)) {
      offset = sNow - fetchedAt;
    }
  }

  const estimatedServerNow = currentNow + offset;
  return Math.max(0, deadlineMs - estimatedServerNow);
}

/**
 * Formats milliseconds into HH:MM:SS or MM:SS.
 */
export function formatRemainingTime(ms: number | null): string {
  if (ms === null) return "Không giới hạn";
  if (ms <= 0) return "00:00";

  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const pad = (n: number) => n.toString().padStart(2, "0");

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

export interface CountdownTimerOptions {
  deadlineAt?: string | Date | null;
  serverNow?: string | Date | null;
  fetchTimeMs?: number;
  onTimeout?: () => void;
  onTick?: (remainingMs: number | null) => void;
}

export class CountdownTimer {
  private timer: ReturnType<typeof setInterval> | null = null;
  private fired = false;
  private deadlineAt?: string | Date | null;
  private serverNow?: string | Date | null;
  private fetchTimeMs: number;
  private onTimeout?: () => void;
  private onTick?: (remainingMs: number | null) => void;

  constructor(options: CountdownTimerOptions) {
    this.deadlineAt = options.deadlineAt;
    this.serverNow = options.serverNow;
    this.fetchTimeMs = options.fetchTimeMs ?? Date.now();
    this.onTimeout = options.onTimeout;
    this.onTick = options.onTick;
  }

  getRemainingMs(nowMs = Date.now()): number | null {
    return calculateRemainingMs(this.deadlineAt, this.serverNow, this.fetchTimeMs, nowMs);
  }

  start(intervalMs = 1000): void {
    this.stop();
    this.check();
    if (!this.fired && this.getRemainingMs() !== null) {
      this.timer = setInterval(() => this.check(), intervalMs);
    }
  }

  stop(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  check(nowMs = Date.now()): number | null {
    const remaining = this.getRemainingMs(nowMs);
    this.onTick?.(remaining);
    if (remaining !== null && remaining <= 0 && !this.fired) {
      this.fired = true;
      this.stop();
      this.onTimeout?.();
    }
    return remaining;
  }

  isFired(): boolean {
    return this.fired;
  }
}

export interface UseCountdownProps {
  deadlineAt?: string | Date | null;
  serverNow?: string | Date | null;
  fetchTimeMs?: number;
  onTimeout?: () => void;
  intervalMs?: number;
}

export function useCountdown({
  deadlineAt,
  serverNow,
  fetchTimeMs,
  onTimeout,
  intervalMs = 1000,
}: UseCountdownProps) {
  const firedDeadline = useRef<string | null>(null);
  const onTimeoutRef = useRef(onTimeout);
  onTimeoutRef.current = onTimeout;

  const [remainingMs, setRemainingMs] = useState<number | null>(() =>
    calculateRemainingMs(deadlineAt, serverNow, fetchTimeMs, Date.now()),
  );

  useEffect(() => {
    if (!deadlineAt) {
      setRemainingMs(null);
      return;
    }

    const timer = new CountdownTimer({
      deadlineAt,
      serverNow,
      fetchTimeMs: fetchTimeMs ?? Date.now(),
      onTick: (ms) => setRemainingMs(ms),
      onTimeout: () => {
        const key = String(new Date(deadlineAt).getTime());
        if (firedDeadline.current !== key) {
          firedDeadline.current = key;
          onTimeoutRef.current?.();
        }
      },
    });

    timer.start(intervalMs);
    return () => timer.stop();
  }, [deadlineAt, serverNow, fetchTimeMs, intervalMs]);

  return {
    remainingMs,
    formatted: formatRemainingTime(remainingMs),
    isExpired: remainingMs !== null && remainingMs <= 0,
  };
}
