import { renderToStaticMarkup } from "react-dom/server";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { AskCard, type AskCardData, clarifyReply, confirmReply, sentState, SKIP_ALL_MESSAGE } from "./AskCard";
import { activeAskId, fromStored, type ThreadMessage } from "./ChatThread";
import { applyPlan, applyStep, applyStepTool, finishProcess, ProcessPanel, processFromStored, processSummary, StepNoteBody } from "./ProcessPanel";
import { MAX_MESSAGES, removeSession, sessionGroup, sessionTime, sessionTitle, type StoredSession, upsertSession } from "./chatHistory";
import { MessageBody, MessageCitations, MessageContributors, MessageSuggestions, messageBlocks, replyExtras } from "./MessageBody";
import { THINKING_LINES, thinkingLines } from "./thinking";

const LONG = [
  "Kế hoạch khả thi một phần: khối lượng vượt giờ rảnh của nhóm khoảng 12 giờ, còn lại các tiêu chí đều có căn cứ.",
  "- **Khối lượng:** tổng 96 giờ so với 84 giờ rảnh của cả nhóm trong 10 tuần, vượt 12 giờ.",
  "- **Thiết bị:** camera IP còn 4/6 chiếc, cần đăng ký trước 3 ngày và được giáo viên duyệt.",
  "- **Chi phí:** dự kiến 0 đồng, ngân sách 0 đồng, nằm trong ngân sách.",
  "- **Mentor:** giáo viên hỗ trợ khoảng 1 giờ mỗi tuần, chưa có lịch chính thức.",
  "- **Kỹ năng:** chưa ai trong nhóm có kinh nghiệm gán nhãn video y tế, cần thêm thời gian học.",
].join("\n");

describe("long agent replies", () => {
  it("splits a reply into its opening sentence and a bullet list", () => {
    const blocks = messageBlocks(LONG);
    expect(blocks[0]).toEqual({ kind: "text", lines: [expect.stringContaining("Kế hoạch khả thi một phần")] });
    expect(blocks[1].kind).toBe("list");
    expect(blocks[1].kind === "list" && blocks[1].items).toHaveLength(5);
  });

  it("shows a short reply whole, with no arrow", () => {
    const html = renderToStaticMarkup(<MessageBody text={"Đã lưu bản nháp.\n- **Mốc:** 3 mốc."} />);
    expect(html).not.toContain("message__expand");
    expect(html).toContain("<strong>Mốc:</strong>");
  });

  it("keeps every point of an unstructured reply visible, including warnings at the end", () => {
    const html = renderToStaticMarkup(<MessageBody text={LONG} />);
    expect(html).not.toContain('is-collapsed');
    expect(html).toContain("Kỹ năng:");
    expect(html).toContain("chưa ai trong nhóm");
    expect(html.match(/<li>/g)).toHaveLength(5);
  });
});

describe("waiting lines", () => {
  it("starts on the plain default and never repeats the line on screen", () => {
    expect(thinkingLines(undefined, true)[0]).toBe("Đang xử lý yêu cầu của bạn");
    expect(thinkingLines("safety", false)).toBe(THINKING_LINES.default);
    expect(thinkingLines("feasibility", false)).toEqual(["Đang soạn câu trả lời"]);
  });
});

describe("chat history in the browser", () => {
  const session = (id: string, updatedAt: number, messages: number[] = [1]): StoredSession<number> => ({
    id, title: id, createdAt: updatedAt, updatedAt, messages,
  });

  it("names a session after the first question and shortens a long one", () => {
    expect(sessionTitle(undefined)).toBe("Cuộc trò chuyện mới");
    expect(sessionTitle("  Lập kế hoạch\n cho đề tài đột quỵ ")).toBe("Lập kế hoạch cho đề tài đột quỵ");
    expect(sessionTitle("x".repeat(100)).length).toBeLessThanOrEqual(60);
  });

  it("keeps the newest first, replaces an old copy and caps the transcript", () => {
    const list = upsertSession([session("a", 1), session("b", 2)], session("a", 3, Array.from({ length: MAX_MESSAGES + 5 }, (_, i) => i)));
    expect(list.map((item) => item.id)).toEqual(["a", "b"]);
    expect(list[0].messages).toHaveLength(MAX_MESSAGES);
    expect(list[0].messages[0]).toBe(5);
    expect(removeSession(list, "a").map((item) => item.id)).toEqual(["b"]);
  });

  it("groups sessions by day", () => {
    const now = new Date(2026, 9, 16, 12).getTime();
    expect(sessionGroup(now - 60_000, now)).toBe("Hôm nay");
    expect(sessionGroup(new Date(2026, 9, 15, 9).getTime(), now)).toBe("Hôm qua");
    expect(sessionGroup(new Date(2026, 9, 12).getTime(), now)).toBe("7 ngày qua");
    expect(sessionGroup(new Date(2026, 8, 1).getTime(), now)).toBe("Cũ hơn");
  });
});


it("dates every saved session in full, not just its time", () => {
  expect(sessionTime(new Date(2026, 9, 17, 7, 5).getTime())).toBe("07:05 17/10/2026");
  expect(sessionTime(new Date(2026, 0, 3, 23, 40).getTime())).toBe("23:40 03/01/2026");
});

describe("citations and follow-up questions", () => {
  const citation = { document_id: "d1", title: "Phân số.pdf", location: "trang 2", excerpt: "Phân số là ".repeat(30) };

  it("shows the document title, its place and a shortened excerpt", () => {
    const html = renderToStaticMarkup(<MessageCitations items={[citation]} />);
    expect(html).toContain("Phân số.pdf");
    expect(html).toContain("trang 2");
    expect(html).toContain("…");
    expect(renderToStaticMarkup(<MessageCitations items={[]} />)).toBe("");
  });

  it("sends the picked question", () => {
    const onPick = vi.fn();
    const html = renderToStaticMarkup(<MessageSuggestions items={["Câu một?", "Câu hai?"]} onPick={onPick} />);
    expect(html.match(/<button/g)).toHaveLength(2);
    const list = MessageSuggestions({ items: ["Câu một?", "Câu hai?"], onPick }) as ReactElement<{ children: ReactElement[] }>;
    const second = list.props.children[1] as ReactElement<{ children: ReactElement<{ onClick: () => void }> }>;
    second.props.children.props.onClick();
    expect(onPick).toHaveBeenCalledWith("Câu hai?");
  });

  it("hides both on a blocked reply and keeps follow-ups to the latest answer", () => {
    const message = { status: "ok", citations: [citation], suggestions: ["Câu một?"] };
    expect(replyExtras({ ...message, status: "blocked" }, true)).toEqual({ citations: [], suggestions: [] });
    expect(replyExtras(message, false)).toEqual({ citations: [citation], suggestions: [] });
    expect(replyExtras(message, true).suggestions).toEqual(["Câu một?"]);
  });
});

describe("ask card (feature 002)", () => {
  const questions = [
    { id: "q1", question: "Em muốn ôn môn nào?", options: ["Toán", "Tiếng Anh"] },
    { id: "q2", question: "Đề gồm bao nhiêu câu?", options: [] },
  ];
  const ask: AskCardData = { run_id: "run-1", kind: "clarify", intro: "Cần thêm thông tin", questions, skippable: true, state: "open" };

  it("sends the picked and typed answers with the questions as the message", () => {
    const { reply, message } = clarifyReply("run-1", questions, { q1: "Toán", q2: " 10 " });
    expect(reply).toEqual({ run_id: "run-1", answers: { q1: "Toán", q2: "10" }, skip_all: false });
    expect(message).toBe("Em muốn ôn môn nào?\nToán\n\nĐề gồm bao nhiêu câu?\n10");
    expect(sentState(reply)).toBe("answered");
  });

  it("sends skip_all for “Cứ làm luôn” and when nothing was answered", () => {
    for (const sent of [clarifyReply("run-1", questions, { q1: "Toán" }, true), clarifyReply("run-1", questions, {})]) {
      expect(sent.reply.skip_all).toBe(true);
      expect(sent.reply.answers).toEqual({});
      expect(sent.message).toBe(SKIP_ALL_MESSAGE);
      expect(sentState(sent.reply)).toBe("skipped");
    }
  });

  it("sends the decision of a confirmation", () => {
    expect(confirmReply("run-1", true)).toEqual({ reply: { run_id: "run-1", decision: "approve" }, message: "Đồng ý" });
    expect(sentState(confirmReply("run-1", false).reply)).toBe("rejected");
  });

  it("can be used only while open, newest and active", () => {
    const open = renderToStaticMarkup(<AskCard ask={ask} active mascot="owl" onReply={() => {}} />);
    expect(open).toContain("Cứ làm luôn");
    expect(open).toContain("<textarea");
    expect(open).not.toMatch(/question-card__submit"[^>]*disabled/);
    const answered = renderToStaticMarkup(<AskCard ask={{ ...ask, state: "answered", answers: { q1: "Toán" } }} active mascot="owl" onReply={() => {}} />);
    expect(answered).toContain("Đã trả lời");
    expect(answered).not.toContain("<textarea");
    expect(answered).toMatch(/question-card__skip"[^>]*disabled/);
    const stale = renderToStaticMarkup(<AskCard ask={ask} active={false} mascot="owl" onReply={() => {}} />);
    expect(stale).toMatch(/question-card__skip"[^>]*disabled/);
  });

  it("shows a confirmation with its preview and two buttons", () => {
    const html = renderToStaticMarkup(
      <AskCard
        ask={{ run_id: "r", kind: "confirm", state: "open", confirm: { tool: "post_class_announcement", summary: "Đăng thông báo", impact: "Cả lớp sẽ thấy", audience_count: 30, preview: { title: "Lịch kiểm tra", body: "Thứ 6" } } }}
        active mascot="owl" onReply={() => {}}
      />,
    );
    expect(html).toContain("Đăng thông báo");
    expect(html).toContain("Lịch kiểm tra");
    expect(html).toContain("30");
    expect(html).toContain("Đồng ý");
    expect(html).toContain("Không");
  });

  it("rebuilds the card from the stored history and only the newest open one is active", () => {
    const stored = fromStored([
      { id: "a1", role: "assistant", content: "Cần thêm thông tin", agent_slug: "tro-ly-lop", status: "awaiting_user", created_at: "", meta: { path: "full", run_id: "run-1", ask: { run_id: "run-1", kind: "clarify", questions, state: "open" } } },
    ], [{ slug: "tro-ly-lop", name: "Trợ lý lớp", description: "", avatar: "owl", source: "class", certification_status: "certified", starter_prompts: [] }]);
    expect(stored[0].ask?.run_id).toBe("run-1");
    expect(stored[0].ask?.agent?.name).toBe("Trợ lý lớp");
    expect(stored[0].status).toBe("ok");
    expect(activeAskId(stored)).toBe("a1");
    const later: ThreadMessage[] = [...stored, { id: "u2", role: "user", content: "Câu khác", tools: [], status: "ok" }];
    expect(activeAskId(later)).toBeNull();
    expect(activeAskId([{ ...stored[0], ask: { ...stored[0].ask!, state: "expired" } }])).toBeNull();
  });
});

describe("contributors (feature 002)", () => {
  it("lists the agents that helped, and nothing when there are none", () => {
    const html = renderToStaticMarkup(<MessageContributors items={[{ slug: "on-tap-tai-lieu", name: "Ôn tập tài liệu", avatar: "owl" }]} />);
    expect(html).toContain("Ôn tập tài liệu");
    expect(html).toContain("Cùng làm");
    expect(renderToStaticMarkup(<MessageContributors items={[]} />)).toBe("");
  });
});

describe("progress panel (feature 002)", () => {
  const tutor = { slug: "gia-su-toan", name: "Gia sư Toán", avatar: "owl" };
  const docs = { slug: "on-tap-tai-lieu", name: "Ôn tập tài liệu", avatar: "fox" };
  const planEvent = {
    type: "plan" as const, message_id: "m1", run_id: "r1", goal: "g", lead: tutor, resumed: false,
    steps: [
      { key: "s1", title: "Tìm lý thuyết", agent: docs, depends_on: [], status: "pending" as const },
      { key: "s2", title: "Soạn bài", agent: tutor, depends_on: ["s1"], status: "pending" as const },
    ],
  };

  it("follows plan, step and step tool events, then collapses into one line", () => {
    let process = applyPlan(undefined, planEvent, 1000);
    process = applyStep(process, { type: "step", message_id: "m1", key: "s1", status: "running" })!;
    process = applyStepTool(process, "s1", "class_doc_search", "start")!;
    process = applyStepTool(process, "s1", "class_doc_search", "done")!;
    process = applyStep(process, { type: "step", message_id: "m1", key: "s1", status: "done", duration_ms: 2100 })!;
    process = applyStep(process, { type: "step", message_id: "m1", key: "synthesis", status: "running" })!;
    expect(process.steps.map((step) => step.status)).toEqual(["done", "pending"]);
    expect(process.steps[0].tools).toEqual([{ name: "class_doc_search", status: "done" }]);
    expect(processSummary(process)).toBe("Đang làm việc…");
    const live = renderToStaticMarkup(<ProcessPanel process={process} />);
    expect(live).toContain("<details class=\"ea-process\" open=\"\"");
    expect(live).toContain("Tìm lý thuyết");
    expect(live).toContain("class_doc_search");

    const done = finishProcess(process, 6000)!;
    expect(processSummary(done)).toBe("Đã làm việc · 2 agent · 5 giây");
    const collapsed = renderToStaticMarkup(<ProcessPanel process={done} messageId="m1" />);
    expect(collapsed).not.toContain("open=\"\"");
    expect(collapsed).toContain("Đã làm việc · 2 agent · 5 giây");
  });

  it("a new plan replaces the steps but keeps the tools already seen", () => {
    let process = applyPlan(undefined, planEvent, 0);
    process = applyStepTool(process, "s1", "class_doc_search", "done")!;
    process = applyPlan(process, { ...planEvent, resumed: true, steps: [{ ...planEvent.steps[0], status: "done" }] });
    expect(process.steps).toHaveLength(1);
    expect(process.steps[0].tools).toHaveLength(1);
  });

  it("is rebuilt from meta.process after a reload", () => {
    const process = processFromStored(
      { duration_ms: 12400, agents: 2, steps: [{ key: "s1", title: "Tìm lý thuyết", agent: "gia-su-toan", status: "done" }, { key: "s2", title: "Soạn bài", agent: "gone", status: "error" }] },
      [{ slug: "gia-su-toan", name: "Gia sư Toán", description: "", avatar: "owl", source: "class", certification_status: "certified", starter_prompts: [] }],
    )!;
    expect(process.done).toBe(true);
    expect(process.steps[0].agent.name).toBe("Gia sư Toán");
    expect(process.steps[1].agent.name).toBe("gone");
    expect(processSummary(process)).toBe("Đã làm việc · 2 agent · 12 giây");
    const html = renderToStaticMarkup(<ProcessPanel process={process} messageId="m1" />);
    // Only a finished step of a stored answer opens a note.
    expect(html.match(/<details/g)).toHaveLength(2);
    expect(html).toContain("Lỗi");
    expect(processFromStored(undefined, [])).toBeUndefined();
  });

  it("restores the panel from the stored history", () => {
    const [message] = fromStored([
      { id: "m1", role: "assistant", content: "Kết quả", agent_slug: "gia-su-toan", status: "ok", created_at: "",
        meta: { path: "full", run_id: "r1", process: { duration_ms: 3000, agents: 1, steps: [{ key: "s1", title: "Soạn", agent: "gia-su-toan", status: "done" }] } } },
    ], []);
    expect(message.process?.steps[0].key).toBe("s1");
  });
});

describe("working notes (feature 002)", () => {
  const base = { key: "s1", title: "Tìm lý thuyết", agent: "on-tap-tai-lieu", status: "done" as const, citations: [] };
  it("shows a reviewed note and hides the rest", () => {
    expect(renderToStaticMarkup(<StepNoteBody note={{ ...base, visibility: "visible", note: "Pytago: a² + b² = c²" }} />)).toContain("a² + b² = c²");
    const hidden = renderToStaticMarkup(<StepNoteBody note={{ ...base, visibility: "hidden", note: null, reason_text: "Nội dung này đã được ẩn" }} />);
    expect(hidden).toContain("Nội dung này đã được ẩn");
    expect(renderToStaticMarkup(<StepNoteBody note={{ ...base, visibility: "unavailable", note: null }} />)).toContain("không có ghi chú");
  });
});
