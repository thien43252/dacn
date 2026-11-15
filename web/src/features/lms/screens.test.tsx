import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useResource } from "../../app/useResource";
import { matchRoute } from "../../app/routes";
import { AssignmentView } from "./AssignmentView";
import { QuizResult } from "./QuizResult";
import { QuizResults } from "./QuizResults";
import { QuizTake } from "./QuizTake";

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
