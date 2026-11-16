import { type ReactElement, type ReactNode, isValidElement } from "react";
import { lmsApi } from "../../api-client/lms";
import { QuizEditor } from "./QuizEditor";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useResource } from "../../app/useResource";
import { navigate } from "../../app/router";
import { matchRoute } from "../../app/routes";
import { AssignmentView } from "./AssignmentView";
import { QuizResult } from "./QuizResult";
import { QuizResults } from "./QuizResults";
import { QuizTake } from "./QuizTake";

vi.mock("../../app/router", async (importOriginal) => ({ ...(await importOriginal<object>()), navigate: vi.fn() }));
vi.mock("../../app/useResource", () => ({ useResource: vi.fn(), errorMessage: String }));
const mockedResource = vi.mocked(useResource);
const resource = (data: unknown) => ({ data, error: null, loading: false, reload: vi.fn(), setData: vi.fn() });
const quiz = {
  item_id: "quiz", title: "Kiểm tra", state: "open", max_attempts: 1,
  question_count: 1, max_points: 10, attempts: [],
};
const attempt = {
  id: "attempt", quiz_id: "quiz", student_id: "child", status: "graded", attempt_no: 1,
  max_score: 10, submitted_at: "2026-11-16T10:00:00Z", answers: { q: false },
  questions: [{ question_id: "q", kind: "true_false", prompt: "Mệnh đề", options: [], points: 10 }],
};

beforeEach(() => mockedResource.mockReset());

describe("LMS backend response rendering", () => {
  it("reads returned assignment results and prompt file IDs while parents have no write controls", () => {
    mockedResource.mockReturnValue(resource({
      item_id: "assignment", prompt: "Đề bài", prompt_file_ids: ["prompt-file"],
      max_points: 10, allow_late: true, effective_due: "2026-11-17T10:00:00Z",
      submission: { id: "s", status: "returned", versions: [], result: { raw_score: 8, penalty: 1, final_score: 7, feedback: "Làm tốt" } },
    }));
    const html = renderToStaticMarkup(<AssignmentView classId="class" assignmentId="assignment" role="parent" studentId="child" />);
    expect(html).toContain("8 / 10");
    expect(html).toContain("7 / 10");
    expect(html).toContain("Làm tốt");
    expect(html).toContain("/api/classes/class/files/prompt-file?download=1");
    expect(html).not.toContain("Xác nhận nộp bài");
    expect(html).not.toContain('type="file"');
  });

  it("does not show assignment grading data until result is returned", () => {
    mockedResource.mockReturnValue(resource({
      item_id: "assignment", prompt: "Đề", max_points: 10, allow_late: false,
      effective_due: "2000-01-01T00:00:00Z", submission: null,
    }));
    const html = renderToStaticMarkup(<AssignmentView classId="class" assignmentId="assignment" />);
    expect(html).toContain("Quá hạn");
    expect(html).not.toContain("Xác nhận nộp bài");
    expect(html).not.toContain("Kết quả đánh giá");
  });

  it("shows upcoming quiz state and disables starting", () => {
    mockedResource.mockReturnValue(resource({ ...quiz, state: "upcoming" }));
    const html = renderToStaticMarkup(<QuizTake classId="class" quizId="quiz" />);
    expect(html).toContain("Sắp mở");
    expect(html).toMatch(/disabled=""[^>]*>Bắt đầu làm bài/);
  });

  it("opens notification quiz URLs and offers resume even when the attempt limit is used", () => {
    expect(matchRoute("/student/classes/class/quizzes/quiz")?.meta.pattern).toBe("/student/classes/:classId/quizzes/:quizId");
    mockedResource.mockReturnValueOnce(resource({ ...quiz, attempts: [{ ...attempt, status: "in_progress" }] })).mockReturnValueOnce(resource(null));
    const html = renderToStaticMarkup(<QuizResult classId="class" quizId="quiz" overview />);
    expect(html).toContain("Tiếp tục làm bài");
  });

  it("allows retrying resume from the take screen when all attempts are used", () => {
    mockedResource.mockReturnValue(resource({ ...quiz, attempts: [{ ...attempt, status: "in_progress" }] }));
    const html = renderToStaticMarkup(<QuizTake classId="class" quizId="quiz" />);
    expect(html).toContain("Tiếp tục làm bài");
    expect(html).not.toMatch(/disabled=""[^>]*>Tiếp tục làm bài/);
  });

  it("honors omitted score and answers instead of inventing reveal data", () => {
    mockedResource.mockReturnValueOnce(resource({ ...quiz, attempts: [attempt] })).mockReturnValueOnce(resource(attempt));
    const html = renderToStaticMarkup(<QuizResult classId="class" quizId="quiz" role="parent" />);
    expect(html).toContain("Chưa công bố điểm");
    expect(html).not.toContain("Đáp án đúng:");
    expect(html).not.toContain("Lời giải chi tiết:");
    expect(html).not.toContain("Bắt đầu làm bài");
  });

  it("renders revealed false answers and explanations from each question", () => {
    mockedResource.mockReturnValueOnce(resource({ ...quiz, attempts: [attempt] })).mockReturnValueOnce(resource({
      ...attempt, score: 10, questions: [{ ...attempt.questions[0], correct: false, explanation: "Lời giải được công bố" }],
    }));
    const html = renderToStaticMarkup(<QuizResult classId="class" quizId="quiz" role="parent" />);
    expect(html).toContain("10 / 10");
    expect(html).toContain("Đáp án đúng:</strong> Sai");
    expect(html).toContain("Lời giải được công bố");
  });

  it("renders teacher statistics from stats and essay attempts from the result list", () => {
    mockedResource.mockReturnValue(resource({
      attempts: [{ ...attempt, student_name: "Học sinh A", score: 8 }],
      stats: { attempted_students: 1, average: 8.25, distribution: { "8": 1 }, per_question: [{ question_id: "q", correct_rate: 0.75 }] },
    }));
    const html = renderToStaticMarkup(<QuizResults classId="class" quizId="quiz" aiGrading={false} />);
    expect(html).toContain("8.3");
    expect(html).toContain("75%");
    expect(html).toContain("Học sinh A");
    expect(html).toContain("8/10");
  });
});

// The suite uses server rendering; this small hook harness also exercises event handlers
// without adding a browser environment dependency.
const hookHarness = vi.hoisted(() => ({ active: false, values: [] as unknown[], cursor: 0 }));
vi.mock("react", async (importOriginal) => {
  const original = await importOriginal<typeof import("react")>();
  return { ...original, useState: (initial: unknown) => {
    if (!hookHarness.active) return original.useState(initial);
    const index = hookHarness.cursor++;
    if (!(index in hookHarness.values)) hookHarness.values[index] = initial;
    return [hookHarness.values[index], (value: unknown) => { hookHarness.values[index] = value; }];
  } };
});

type TestElement = ReactElement<{ children?: ReactNode; onClick?: () => unknown; onChange?: (event: { target: { value: string } }) => void; value?: string; disabled?: boolean; href?: string }>;
function expand(node: ReactNode): ReactNode {
  if (Array.isArray(node)) return node.map((child, index) => {
    const expanded = expand(child);
    return isValidElement(expanded) ? { ...expanded, key: expanded.key ?? String(index) } : expanded;
  });
  if (!isValidElement(node)) return node;
  const element = node as TestElement;
  if (typeof element.type === "function") {
    // ConfirmDialog is closed in these tests and owns unrelated effect/ref hooks.
    if (element.type.name === "ConfirmDialog") return null;
    return expand((element.type as (props: unknown) => ReactNode)(element.props));
  }
  return { ...element, props: { ...element.props, children: expand(element.props.children) } };
}
function elements(node: ReactNode): TestElement[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement(node)) return [];
  const element = node as TestElement;
  return [element, ...elements(element.props.children)];
}

describe("Quiz editor copying", () => {
  it.each(["class", "other-class"])("copies to a selected lesson in %s and links to the new editor", async (targetClassId) => {
    hookHarness.active = true;
    hookHarness.values = [];
    const copy = vi.spyOn(lmsApi.quizzes, "copy").mockResolvedValue({ item_id: "new-quiz" } as never);
    mockedResource.mockImplementation(((_loader: unknown, deps: readonly unknown[] = []) => {
      if (deps[1] === "quiz") return resource({ ...quiz, questions: [] });
      if (deps.length === 0) return resource([
        { id: "class", name: "Lớp hiện tại", my_role: "teacher", archived: false },
        { id: "other-class", name: "Lớp khác", my_role: "teacher", archived: false },
        { id: "archived-class", name: "Lớp lưu trữ", my_role: "teacher", archived: true },
        { id: "student-class", name: "Lớp học sinh", my_role: "student", archived: false },
      ]);
      return resource([
        { id: "lesson", title: "Buổi học đích", status: "published" },
        { id: "archived-lesson", title: "Bài lưu trữ", status: "archived" },
      ]);
    }) as unknown as typeof useResource);
    const draw = () => {
      hookHarness.cursor = 0;
      return expand(<QuizEditor classId="class" quizId="quiz" />);
    };
    const button = (tree: ReactNode, text: string) => elements(tree).find((el) => el.type === "button" && renderToStaticMarkup(el).includes(text))!;
    try {
      let tree = draw();
      button(tree, "Sao chép quiz").props.onClick!();
      tree = draw();
      expect(renderToStaticMarkup(<>{tree}</>)).toContain('role="dialog"');
      expect(renderToStaticMarkup(<>{tree}</>)).not.toContain("Lớp lưu trữ");
      expect(renderToStaticMarkup(<>{tree}</>)).not.toContain("Lớp học sinh");
      expect(renderToStaticMarkup(<>{tree}</>)).not.toContain("Bài lưu trữ");
      const selects = elements(tree).filter((el) => el.type === "select");
      expect(selects.find((el) => el.props.value === "class")).toBeDefined();
      selects.find((el) => el.props.value === "class")!.props.onChange!({ target: { value: targetClassId } });
      tree = draw();
      expect(button(tree, ">Sao chép<").props.disabled).toBe(true);
      elements(tree).filter((el) => el.type === "select")[1].props.onChange!({ target: { value: "lesson" } });
      tree = draw();
      await button(tree, ">Sao chép<").props.onClick!();
      expect(copy).toHaveBeenCalledWith("class", "quiz", "lesson");
      const html = renderToStaticMarkup(<>{draw()}</>);
      expect(html).toContain("Đã sao chép quiz sang Buổi học đích");
      button(draw(), "Mở quiz đã sao chép").props.onClick!();
      expect(navigate).toHaveBeenLastCalledWith(`/teacher/classes/${targetClassId}/quizzes/new-quiz`);
    } finally {
      hookHarness.active = false;
      copy.mockRestore();
    }
  });
});

describe("Quiz editor question source", () => {
  it("labels approved AI questions (FR-032)", () => {
    hookHarness.active = true;
    hookHarness.values = [];
    const question = { kind: "single", prompt: "Câu", options: [], points: 1, explanation: "", rubric: null, answer_key: "a", position: 0, affects_submitted: 0 };
    mockedResource.mockImplementation(((_loader: unknown, deps: readonly unknown[] = []) => {
      if (deps[1] === "quiz") return resource({ ...quiz, questions: [{ ...question, id: "ai", source: "ai" }, { ...question, id: "manual", source: "teacher" }] });
      return resource([]);
    }) as unknown as typeof useResource);
    try {
      hookHarness.cursor = 0;
      const html = renderToStaticMarkup(<>{expand(<QuizEditor classId="class" quizId="quiz" />)}</>);
      expect(html.split("Nguồn: AI gợi ý, giáo viên duyệt").length - 1).toBe(1);
    } finally {
      hookHarness.active = false;
    }
  });
});
