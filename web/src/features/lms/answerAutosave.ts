import type { AnswerValue } from "../../api-client/lms";

/** Serial writes keep an older answer from overtaking a newer one. */
export class AnswerAutosave {
  private pending = new Map<string, { value: AnswerValue }>();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private queue: Promise<void> = Promise.resolve();
  private disposed = false;

  constructor(
    private save: (questionId: string, value: AnswerValue) => Promise<unknown>,
    private onStatus: (pending: boolean) => void,
    private onError: (error: unknown) => void,
  ) {}

  change(questionId: string, value: AnswerValue): void {
    this.pending.set(questionId, { value });
    clearTimeout(this.timers.get(questionId));
    this.onStatus(true);
    this.timers.set(questionId, setTimeout(() => {
      this.timers.delete(questionId);
      void this.enqueue(questionId).catch((error) => {
        if (!this.disposed) this.onError(error);
      });
    }, 1000));
  }

  private enqueue(questionId: string): Promise<void> {
    const entry = this.pending.get(questionId);
    if (!entry) return this.queue;
    const operation = this.queue.catch(() => {}).then(async () => {
      if (this.disposed) return;
      await this.save(questionId, entry.value);
      if (this.pending.get(questionId) === entry) this.pending.delete(questionId);
      if (!this.disposed) this.onStatus(this.pending.size > 0);
    });
    this.queue = operation;
    return operation;
  }

  async flush(): Promise<void> {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
    // Include in-flight writes before retrying any answers that failed to save.
    await this.queue.catch(() => {});
    for (const questionId of this.pending.keys()) await this.enqueue(questionId);
  }

  dispose(): void {
    this.disposed = true;
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
  }
}
