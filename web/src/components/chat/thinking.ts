/** General wording makes no claim about tools, sources or completion. */
export const THINKING_LINES: Record<string, string[]> = {
  orchestrator: ["Đang xử lý yêu cầu của bạn"],
  default: ["Đang soạn câu trả lời"],
};

export function thinkingLines(_agent: string | undefined, thinking: boolean): string[] {
  return thinking ? THINKING_LINES.orchestrator : THINKING_LINES.default;
}
