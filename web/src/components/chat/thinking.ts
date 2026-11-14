/** General wording makes no claim about tools, sources or completion. */
export const THINKING_LINES: Record<string, string[]> = {
  orchestrator: ["Đang xử lý yêu cầu của bạn"],
  default: ["Đang soạn câu trả lời"],
  /** Full path (feature 002): the planner reads the request, then the lead writes the one answer. */
  analyze: ["Đang phân tích yêu cầu"],
  synthesis: ["Đang tổng hợp kết quả"],
};

/** The waiting line of a full-path phase (`step` events with the keys `analyze` and `synthesis`). */
export function phaseLine(key: string): string | undefined {
  return THINKING_LINES[key]?.[0];
}

export function thinkingLines(_agent: string | undefined, thinking: boolean): string[] {
  return thinking ? THINKING_LINES.orchestrator : THINKING_LINES.default;
}
