import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MAX_MESSAGES, removeSession, sessionGroup, sessionTime, sessionTitle, type StoredSession, upsertSession } from "./chatHistory";
import { MessageBody, messageBlocks } from "./MessageBody";
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
