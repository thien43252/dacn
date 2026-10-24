const REVEAL_WINDOW_MS = 160;

/** Spread provider bursts across a few paints; never keep text queued after completion. */
export class SmoothTextPresenter {
  private pending: string[] = [];
  private frameId: number | null = null;
  private deadline = 0;
  private closed = false;

  constructor(
    private readonly onAppend: (text: string) => void,
    private readonly onReplace: (text: string) => void,
  ) {}

  append(delta: string) {
    if (this.closed || !delta) return;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      this.onAppend(delta);
      return;
    }
    this.pending.push(...Array.from(delta));
    this.deadline = Math.max(this.deadline, performance.now() + REVEAL_WINDOW_MS);
    if (this.frameId === null) this.frameId = requestAnimationFrame(this.paint);
  }

  replace(content: string) {
    if (this.closed) return;
    this.cancelFrame();
    this.pending = [];
    this.deadline = 0;
    this.onReplace(content);
  }

  flush() {
    if (this.closed) return;
    this.cancelFrame();
    if (this.pending.length) this.onAppend(this.pending.join(""));
    this.pending = [];
    this.deadline = 0;
  }

  dispose() {
    this.cancelFrame();
    this.pending = [];
    this.closed = true;
  }

  private cancelFrame() {
    if (this.frameId !== null) cancelAnimationFrame(this.frameId);
    this.frameId = null;
  }

  private paint = (now: number) => {
    this.frameId = null;
    if (this.closed || !this.pending.length) return;
    const remainingMs = Math.max(16, this.deadline - now);
    const count = Math.min(this.pending.length, Math.max(1, Math.ceil(this.pending.length * 16 / remainingMs)));
    this.onAppend(this.pending.splice(0, count).join(""));
    if (this.pending.length) this.frameId = requestAnimationFrame(this.paint);
    else this.deadline = 0;
  };
}
