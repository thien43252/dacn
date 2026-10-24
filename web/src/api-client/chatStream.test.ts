import { afterEach, describe, expect, it, vi } from "vitest";

import { type ChatStreamEvent, consumeChatStream } from "./chatStream";

const operation = { type: "operation", operation_id: "job-1", resume_supported: true };
const text = (delta: string, text_offset = 0, generation = 0): ChatStreamEvent => ({
  type: "text_delta", agent: "planner", message_id: "1", delta, text_offset, generation,
});
const done = { type: "done", conversation_id: "thread" };

function stream(events: (object | Error)[]) {
  const encoder = new TextEncoder();
  const items = [...events];
  return new Response(new ReadableStream<Uint8Array>({
    pull(controller) {
      const item = items.shift();
      if (item instanceof Error) controller.error(item);
      else if (item) controller.enqueue(encoder.encode(`data: ${JSON.stringify(item)}\n\n`));
      else controller.close();
    },
  }, { highWaterMark: 0 }));
}

afterEach(() => vi.unstubAllGlobals());

describe("chat reconnect", () => {
  it("reattaches the exact request and skips replayed Unicode text", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(stream([operation, text("Xin 👋"), new TypeError("lost")]))
      .mockResolvedValueOnce(stream([operation, text("Xin 👋, sếp"), done]));
    vi.stubGlobal("fetch", fetch);
    const received: ChatStreamEvent[] = [];
    const body = JSON.stringify({ message: "Chào", idempotency_key: "same-key", conversation_id: "thread" });
    await consumeChatStream(body, new AbortController().signal, event => received.push(event), 0);
    expect(received.filter(item => item.type === "text_delta").map(item => item.delta).join("")).toBe("Xin 👋, sếp");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls.map(call => call[1].body)).toEqual([body, body]);
  });

  it("recovers a closed stream before completion", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(stream([operation, text("A")]))
      .mockResolvedValueOnce(stream([operation, text("AB"), done]));
    vi.stubGlobal("fetch", fetch);
    const received: string[] = [];
    await consumeChatStream("body", new AbortController().signal, event => { if (event.delta) received.push(event.delta); }, 0);
    expect(received).toEqual(["A", "B"]);
  });

  it("resets only a changed generation and ignores a duplicate reset", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(stream([operation, text("cũ")]))
      .mockResolvedValueOnce(stream([operation, text("mới", 0, 1), new TypeError("lost")]))
      .mockResolvedValueOnce(stream([operation, { type: "text_reset", message_id: "1", generation: 1 }, text("mới!", 0, 1), done]));
    vi.stubGlobal("fetch", fetch);
    const received: ChatStreamEvent[] = [];
    await consumeChatStream("body", new AbortController().signal, event => received.push(event), 0);
    expect(received.filter(item => item.type.startsWith("text_")).map(item => [item.type, item.delta])).toEqual([
      ["text_delta", "cũ"], ["text_reset", undefined], ["text_delta", "mới"], ["text_delta", "!"],
    ]);
  });

  it.each([
    [text("B", 4), "thiếu một đoạn"],
    [text("khác"), "không khớp"],
    [{ type: "operation", operation_id: "other", resume_supported: true }, "Lượt chat thay đổi"],
  ])("rejects gaps, changed text and a different operation", async (bad, expected) => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(stream([operation, text("A")]))
      .mockResolvedValueOnce(stream([operation, bad]));
    vi.stubGlobal("fetch", fetch);
    await expect(consumeChatStream("body", new AbortController().signal, () => {}, 0)).rejects.toThrow(expected as string);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("does not repeat non-resumable Teacher chat or server errors", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(stream([{ type: "speaker", agent: "progress" }]));
    vi.stubGlobal("fetch", fetch);
    await expect(consumeChatStream("body", new AbortController().signal, () => {}, 0)).rejects.toThrow("gián đoạn");
    expect(fetch).toHaveBeenCalledTimes(1);
    fetch.mockClear().mockResolvedValueOnce(stream([operation, { type: "error", message: "DENIED" }]));
    await expect(consumeChatStream("body", new AbortController().signal, event => {
      if (event.type === "error") throw new Error("DENIED");
    }, 0)).rejects.toThrow("DENIED");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("stops retrying after two reconnects", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(stream([operation])));
    vi.stubGlobal("fetch", fetch);
    await expect(consumeChatStream("body", new AbortController().signal, () => {}, 0)).rejects.toThrow("gián đoạn");
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("ignores a transport failure after response_ready", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(stream([operation, text("A"), { type: "response_ready" }, new TypeError("lost")]));
    vi.stubGlobal("fetch", fetch);
    await consumeChatStream("body", new AbortController().signal, () => {}, 0);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("Pause/Reset cancellation prevents reconnect", async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockResolvedValueOnce(stream([operation]));
    vi.stubGlobal("fetch", fetch);
    await expect(consumeChatStream("body", controller.signal, event => {
      if (event.type === "operation") controller.abort();
    }, 0)).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
