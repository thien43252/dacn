/** Public chat text carries UTF-16 offsets so snapshot replay cannot duplicate Unicode text. */
export interface ChatStreamEvent {
  type: string;
  operation_id?: string;
  resume_supported?: boolean;
  message_id?: string;
  agent?: string;
  delta?: string;
  generation?: number;
  text_offset?: number;
}

class Disconnected extends Error {}

class ReplayText {
  private messages = new Map<string, { generation: number; text: string }>();

  events<T extends ChatStreamEvent>(event: T): T[] {
    if (event.type !== "text_delta" && event.type !== "text_reset") return [event];
    const key = event.message_id;
    const generation = event.generation;
    if (!key || !Number.isInteger(generation) || generation! < 0) throw new Error("Không xác định được vị trí tiếp tục phản hồi. Hãy tải lại cuộc trò chuyện.");
    const old = this.messages.get(key);
    if (old && generation! < old.generation) return [];
    if (event.type === "text_reset") {
      if (old && generation === old.generation) return [];
      this.messages.set(key, { generation: generation!, text: "" });
      return [event];
    }
    const offset = event.text_offset;
    if (!Number.isInteger(offset) || offset! < 0 || typeof event.delta !== "string") {
      throw new Error("Vị trí phản hồi không hợp lệ.");
    }
    const previous = old && old.generation === generation ? old.text : "";
    if (offset! > previous.length) throw new Error("Phản hồi thiếu một đoạn; hãy kiểm tra lại lượt chat.");
    const overlap = Math.min(previous.length - offset!, event.delta.length);
    if (previous.slice(offset!, offset! + overlap) !== event.delta.slice(0, overlap)) {
      throw new Error("Nội dung phát lại không khớp lượt chat.");
    }
    const delta = event.delta.slice(overlap);
    this.messages.set(key, { generation: generation!, text: previous + delta });
    const events: T[] = [];
    if (old && old.generation !== generation) events.push({ ...event, type: "text_reset", delta: undefined });
    if (delta) events.push({ ...event, delta });
    return events;
  }
}

function waitRetry(signal: AbortSignal, delay: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason || new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, delay);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

/** Reattach with the exact idempotent request only after the server advertises replay support. */
export async function consumeChatStream<T extends ChatStreamEvent>(
  body: string,
  signal: AbortSignal,
  apply: (event: T) => void,
  retryDelayMs = 250,
  path = "/api/chat/stream",
): Promise<void> {
  const cursor = new ReplayText();
  let operation: string | undefined;
  let resumable = false;
  let completed = false;
  for (let attempt = 0; ; attempt += 1) {
    try {
      const response = await fetch(path, {
        signal, method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body,
      }).catch(() => { throw new Disconnected("Kết nối phản hồi bị gián đoạn."); });
      if (!response.ok || !response.body) {
        const detail = await response.json().then((data: { detail?: string }) => data.detail).catch(() => undefined);
        throw new Error(detail || "Không nhận được luồng phản hồi.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read().catch(() => { throw new Disconnected("Kết nối phản hồi bị gián đoạn."); });
          buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
          buffer = buffer.replace(/\r\n/g, "\n");
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() || "";
          for (const block of blocks) {
            const data = block.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trim()).join("\n");
            if (!data) continue;
            const event = JSON.parse(data) as T;
            if (signal.aborted) throw signal.reason || new DOMException("Aborted", "AbortError");
            if (event.type === "operation") {
              if (operation && event.operation_id !== operation) throw new Error("Lượt chat thay đổi khi nối lại.");
              if (resumable && event.resume_supported !== true) throw new Error("Chưa thể tiếp tục phản hồi bị gián đoạn. Hãy gửi lại câu hỏi.");
              operation = event.operation_id;
              resumable = event.resume_supported === true && !!operation;
            }
            for (const item of resumable ? cursor.events(event) : [event]) apply(item);
            if (event.type === "response_ready" || event.type === "done") completed = true;
          }
          if (done) break;
        }
      } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
      if (!completed) throw new Disconnected("Phản hồi bị gián đoạn.");
      return;
    } catch (error) {
      if (signal.aborted) throw error;
      if (completed && error instanceof Disconnected) return;
      if (!(error instanceof Disconnected) || !resumable || attempt >= 2) throw error;
      await waitRetry(signal, retryDelayMs * (attempt + 1));
    }
  }
}
