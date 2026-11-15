import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnswerAutosave } from "./answerAutosave";

describe("answer autosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces each question and flushes the latest answers before submit", async () => {
    const save = vi.fn().mockResolvedValue({ saved_at: "now" });
    const status = vi.fn();
    const saver = new AnswerAutosave(save, status, vi.fn());
    saver.change("short", "draft");
    await vi.advanceTimersByTimeAsync(700);
    saver.change("short", "final");
    saver.change("boolean", false);
    saver.change("multi", ["a", "b"]);
    await vi.advanceTimersByTimeAsync(999);
    expect(save).not.toHaveBeenCalled();
    await saver.flush();
    expect(save.mock.calls).toEqual([["short", "final"], ["boolean", false], ["multi", ["a", "b"]]]);
    expect(status).toHaveBeenLastCalledWith(false);
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).toHaveBeenCalledTimes(3);
    saver.dispose();
  });

  it("waits for in-flight writes and preserves the newer value", async () => {
    let finish!: () => void;
    const first = new Promise<void>((resolve) => { finish = resolve; });
    const save = vi.fn().mockReturnValueOnce(first).mockResolvedValue(undefined);
    const saver = new AnswerAutosave(save, vi.fn(), vi.fn());
    saver.change("q", "old");
    await vi.advanceTimersByTimeAsync(1000);
    saver.change("q", "new");
    const flush = saver.flush();
    expect(save).toHaveBeenCalledTimes(1);
    finish();
    await flush;
    expect(save.mock.calls).toEqual([["q", "old"], ["q", "new"]]);
    saver.dispose();
  });

  it("reports failures, retries dirty answers on flush, and cancels timers on dispose", async () => {
    const failure = new Error("offline");
    const save = vi.fn().mockRejectedValueOnce(failure).mockResolvedValue(undefined);
    const onError = vi.fn();
    const saver = new AnswerAutosave(save, vi.fn(), onError);
    saver.change("q", "answer");
    await vi.advanceTimersByTimeAsync(1000);
    expect(onError).toHaveBeenCalledWith(failure);
    await saver.flush();
    expect(save).toHaveBeenCalledTimes(2);
    saver.change("other", "unsaved");
    saver.dispose();
    await vi.advanceTimersByTimeAsync(2000);
    expect(save).toHaveBeenCalledTimes(2);
  });
});
