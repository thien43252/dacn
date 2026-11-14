import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Assignment } from "../../api-client/types";
import { AnnouncementItem, AssignmentItem, practiceDraft, practiceLink } from "./ClassFeed";

const assignment: Assignment = {
  id: "a1",
  title: "Luyện Pytago",
  instructions: "Làm trong 20 phút.",
  questions: [{ question: "Cạnh huyền của tam giác 6-8?", options: ["10", "12"] }, { question: "Phát biểu định lý." }],
  due_at: null,
  author_name: "Cô Lan",
  source: "agent",
  created_at: "2026-11-11T08:00:00Z",
  answer_key: [{ index: 1, answer: "BI-MAT" }],
};

describe("class feed (feature 002)", () => {
  it("drafts a practice message with the questions and never the answers", () => {
    const draft = practiceDraft(assignment);
    expect(draft.split("\n")[0]).toBe("Mình muốn làm bài luyện “Luyện Pytago”");
    expect(draft).toContain("1. Cạnh huyền");
    expect(draft).toContain("A. 10");
    expect(draft).not.toContain("BI-MAT");
    const link = new URL(practiceLink("c1", assignment), "http://x");
    expect(link.pathname).toBe("/student/home");
    expect(link.searchParams.get("class")).toBe("c1");
    expect(link.searchParams.get("draft")).toBe(draft);
  });

  it("shows the answer key only when asked to (teachers)", () => {
    expect(renderToStaticMarkup(<AssignmentItem item={assignment} />)).not.toContain("BI-MAT");
    expect(renderToStaticMarkup(<AssignmentItem item={assignment} showAnswers />)).toContain("BI-MAT");
  });

  it("marks what an agent posted after the teacher confirmed", () => {
    const html = renderToStaticMarkup(
      <AnnouncementItem item={{ id: "n1", title: "Nghỉ học", body: "Thứ Hai nghỉ.", audience: "parents", author_name: null, source: "agent", created_at: "2026-11-11T08:00:00Z" }} />,
    );
    expect(html).toContain("Qua agent");
    expect(html).toContain("Phụ huynh");
  });
});
