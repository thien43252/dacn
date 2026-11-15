import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ApprovalCard as Card, HandoffNode, PersonRequest, StoredMessage } from "../../api-client/types";
import { ApprovalCard } from "./ApprovalCard";
import { fromStored } from "./ChatThread";
import { HandoffBar } from "./HandoffBar";
import { PersonRequestCard } from "./PersonRequestCard";

const agentOf = (slug: string) => ({ name: slug === "on-tap-tai-lieu" ? "Ôn tập tài liệu" : slug, avatar: "owl" as const });

const node = (overrides: Partial<HandoffNode> = {}): HandoffNode => ({
  id: "h1",
  from_agent: "gia-su-toan",
  to_agent: "on-tap-tai-lieu",
  status: "answered",
  task: "Tìm lý thuyết Pytago",
  bounds: "Tối đa 80 từ",
  good_answer: "Có trích nguồn",
  answer: "a² + b² = c² (Bài 3)",
  created_at: "2026-11-15T10:00:00Z",
  children: [],
  ...overrides,
});

describe("handoff bar (FR-020 to FR-022)", () => {
  it("shows who was asked and the status, collapsed by default", () => {
    const html = renderToStaticMarkup(<HandoffBar node={node()} agentOf={agentOf} />);
    expect(html).toContain("Đã hỏi <strong>Ôn tập tài liệu</strong>");
    expect(html).toContain("Đã trả lời");
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("a² + b² = c²");
  });

  it("opens to the request and the verbatim answer, with nested handoffs", () => {
    const child = node({ id: "h2", to_agent: "tao-de", status: "queued", answer: null });
    const html = renderToStaticMarkup(<HandoffBar node={node({ children: [child] })} agentOf={agentOf} defaultOpen />);
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("Tìm lý thuyết Pytago");
    expect(html).toContain("a² + b² = c²");
    expect(html).toContain("Đã hỏi <strong>tao-de</strong>");
    expect(html).toContain("Đang hỏi");
  });

  it("never shows a technical error, only a friendly status", () => {
    const html = renderToStaticMarkup(<HandoffBar node={node({ status: "no_answer", answer: null })} agentOf={agentOf} defaultOpen />);
    expect(html).toContain("Không nhận được câu trả lời");
    const hidden = renderToStaticMarkup(<HandoffBar node={node({ status: "hidden", answer: null })} agentOf={agentOf} defaultOpen />);
    expect(hidden).toContain("Nội dung đã được ẩn");
  });
});

describe("direct chat thread", () => {
  it("keeps handoff answers inside the bars in a direct chat and as messages in a group", () => {
    const stored: StoredMessage[] = [
      { id: "1", role: "user", content: "Hỏi", agent_slug: null, status: "ok", created_at: "", meta: {}, seq: 1 },
      { id: "2", role: "assistant", content: "Mình đang hỏi", agent_slug: "gia-su-toan", status: "ok", created_at: "", meta: {}, seq: 2, handoffs: [node()] },
      { id: "3", role: "assistant", content: "a² + b² = c²", agent_slug: "on-tap-tai-lieu", status: "ok", created_at: "", meta: {}, seq: 3, handoff_id: "h1", reply_to_agent: "gia-su-toan" },
    ];
    expect(fromStored(stored, [], "direct").map((m) => m.id)).toEqual(["1", "2"]);
    const group = fromStored(stored, [], "group");
    expect(group.map((m) => m.id)).toEqual(["1", "2", "3"]);
    expect(group[2].replyToAgent).toBe("gia-su-toan");
  });
});

const card: Card = {
  id: "c1",
  status: "open",
  user_id: "student-1",
  agent: { slug: "tro-ly-lop", name: "Trợ lý lớp", avatar: "owl" },
  tool: "ask_person",
  action_kind: "send",
  summary: "Gửi câu hỏi cho Cô Lan (GV Toán)",
  preview: { body: "Em xin nộp muộn", targets: [{ id: "t1", name: "Cô Lan", role_label: "GV Toán" }] },
  choices: [{ id: "once", label: "Cho phép lần này" }, { id: "deny", label: "Từ chối" }],
  answer: null,
  expires_at: "",
};

describe("approval card (FR-033)", () => {
  it("shows the preview, the recipient and the allowed choices to the origin user only", () => {
    const mine = renderToStaticMarkup(<ApprovalCard card={card} viewerId="student-1" />);
    expect(mine).toContain("Em xin nộp muộn");
    expect(mine).toContain("Cô Lan");
    expect(mine).toContain("Cho phép lần này");
    expect(mine).toContain("Từ chối");
    expect(mine).not.toContain("Luôn cho phép");
    const other = renderToStaticMarkup(<ApprovalCard card={card} viewerId="someone-else" />);
    expect(other).not.toContain("Cho phép lần này");
  });

  it("locks the card once answered", () => {
    const html = renderToStaticMarkup(<ApprovalCard card={{ ...card, status: "allowed", answer: "once" }} viewerId="student-1" />);
    expect(html).toContain("Đã cho phép");
    expect(html).not.toContain("<button");
  });
});

const request: PersonRequest = {
  id: "r1",
  kind: "approval",
  status: "open",
  conversation_id: "conv",
  requester: { id: "student-1", name: "An", class: "9A" },
  agent: { slug: "tro-ly-lop", name: "Trợ lý lớp", avatar: "owl" },
  recipient: { id: "t1", name: "Cô Lan", role_label: "GV Toán" },
  body: "Em An xin nộp bài muộn 2 ngày",
  options: ["Đồng ý", "Sửa", "Từ chối"],
  answer: null,
  answer_hidden: false,
  answered_by: null,
  expires_at: "",
  created_at: "",
  can_answer: true,
  can_cancel: false,
};

describe("question card (FR-027 to FR-030)", () => {
  it("lets only the recipient answer, with the agent's options and a free answer", () => {
    const teacher = renderToStaticMarkup(<PersonRequestCard request={request} viewerId="t1" />);
    expect(teacher).toContain("Đồng ý");
    expect(teacher).toContain("Sửa");
    expect(teacher).toContain("Hoặc viết câu trả lời");
    const student = renderToStaticMarkup(<PersonRequestCard request={request} viewerId="student-1" />);
    expect(student).not.toContain("Hoặc viết câu trả lời");
    expect(student).toContain("Huỷ câu hỏi");
  });

  it("shows the answer and no buttons once answered", () => {
    const html = renderToStaticMarkup(<PersonRequestCard request={{ ...request, status: "answered", answer: "Sửa: muộn 1 ngày", answered_by: "Cô Lan" }} viewerId="t1" />);
    expect(html).toContain("Sửa: muộn 1 ngày");
    expect(html).not.toContain("Hoặc viết câu trả lời");
  });
});
