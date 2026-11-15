import { useEffect, useState } from "react";
import {
  type AttemptDetailView,
  type QuizStudentView,
  lmsApi,
} from "../../api-client/lms";
import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import "./lms.css";

export interface QuizResultProps {
  classId: string;
  quizId: string;
  role?: "student" | "parent";
  studentId?: string;
  overview?: boolean;
}

export function QuizResult({ classId, quizId, role = "student", studentId, overview = false }: QuizResultProps) {
  const quizResource = useResource(
    () => lmsApi.quizzes.get(classId, quizId, studentId) as Promise<QuizStudentView>,
    [classId, quizId, studentId],
  );

  const quiz = quizResource.data;
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);

  // Set default selected attempt to latest submitted
  useEffect(() => {
    if (quiz?.attempts && quiz.attempts.length > 0 && !selectedAttemptId) {
      const sorted = quiz.attempts.filter((attempt) => attempt.status !== "in_progress").sort((a, b) => b.attempt_no - a.attempt_no);
      setSelectedAttemptId(sorted[0]?.id ?? null);
    }
  }, [quiz, selectedAttemptId]);

  const attemptResource = useResource(
    () => (selectedAttemptId ? lmsApi.attempts.get(classId, selectedAttemptId) : Promise.resolve(null)),
    [classId, selectedAttemptId],
  );

  const attempt: AttemptDetailView | null = attemptResource.data;

  if (quizResource.loading && !quiz) {
    return (
      <div className="ea-page">
        <p className="ea-muted">Đang tải kết quả bài kiểm tra…</p>
      </div>
    );
  }

  if (quizResource.error || !quiz) {
    return (
      <div className="ea-page">
        <div className="ea-error">{quizResource.error || "Không tìm thấy bài kiểm tra."}</div>
        <button
          className="button button--secondary"
          type="button"
          onClick={() =>
            navigate(role === "parent" ? `/parent/classes/${classId}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}` : `/student/classes/${classId}`)
          }
        >
          <Icon name="chevron-left" /> Về lớp học
        </button>
      </div>
    );
  }

  const attempts = quiz.attempts ?? [];
  const attemptsUsed = attempts.length;
  const completedAttempts = attempts.filter((entry) => entry.status !== "in_progress");
  const maxAttempts = quiz.max_attempts;
  const activeAttempt = attempts.find((attempt) => attempt.status === "in_progress");
  const canRetake = role === "student" && (Boolean(activeAttempt) || (quiz.state === "open" && (maxAttempts === 0 || attemptsUsed < maxAttempts)));

  return (
    <div className="ea-page lms-quiz-result">
      <button
        className="ea-back"
        type="button"
        onClick={() =>
          navigate(role === "parent" ? `/parent/classes/${classId}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}` : `/student/classes/${classId}`)
        }
      >
        <Icon name="chevron-left" /> Về lớp học
      </button>

      <div className="ea-toolbar">
        <div>
          <h2>{quiz.title || "Kết quả bài kiểm tra"}</h2>
          <span className="ea-muted">
            {quiz.state === "upcoming" ? "Sắp mở" : quiz.state === "open" ? "Đang mở" : "Đã đóng"} · Đã làm {attemptsUsed} / {maxAttempts === 0 ? "Không giới hạn" : `${maxAttempts} lượt`}
          </span>
        </div>

        {canRetake && (
          <div className="ea-toolbar__actions">
            <button
              type="button"
              className="button button--primary"
              onClick={() => navigate(`/student/classes/${classId}/quizzes/${quizId}/take`)}
            >
              {activeAttempt ? "Tiếp tục làm bài" : attemptsUsed ? "Làm lại bài kiểm tra" : "Bắt đầu làm bài"}
            </button>
          </div>
        )}
      </div>

      {overview && <div className="ea-card">
        <p>{quiz.question_count} câu · {quiz.max_points} điểm · {quiz.duration_minutes ? `${quiz.duration_minutes} phút` : "Không giới hạn thời lượng"}</p>
        {quiz.open_at && <p>Mở: {new Date(quiz.open_at).toLocaleString("vi-VN")}</p>}
        {quiz.close_at && <p>Đóng: {new Date(quiz.close_at).toLocaleString("vi-VN")}</p>}
      </div>}
      {attemptResource.error && <div className="ea-error">{attemptResource.error}</div>}
      {/* Attempt Selector if multiple attempts */}
      {completedAttempts.length > 1 && (
        <div className="ea-card" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <span style={{ fontWeight: 600 }}>Xem bài làm:</span>
          <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
            {completedAttempts.map((att) => (
              <button
                key={att.id}
                type="button"
                className={`button ${selectedAttemptId === att.id ? "button--primary" : "button--secondary"}`}
                style={{ fontSize: "0.85rem", padding: "4px 10px" }}
                onClick={() => setSelectedAttemptId(att.id)}
              >
                Lần {att.attempt_no}{" "}
                {att.status === "in_progress" ? "(Đang làm)" : "(Đã nộp)"}
              </button>
            ))}
          </div>
        </div>
      )}

      {attemptResource.loading ? (
        <p className="ea-muted">Đang tải chi tiết bài làm…</p>
      ) : !attempt ? (
        <div className="ea-card">
          <p className="ea-muted">Chưa có bài làm nào được nộp cho bài kiểm tra này.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {/* Score Banner */}
          <div
            className="ea-card"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "var(--space-3)",
              background:
                attempt.score !== null && attempt.score !== undefined
                  ? "var(--surface, #fff)"
                  : "var(--surface-subtle, #f9f9f9)",
              borderLeft: "6px solid var(--primary)",
            }}
          >
            <div>
              <span className="ea-muted" style={{ fontSize: "0.9rem" }}>
                Điểm số bài làm (Lần {attempt.attempt_no}):
              </span>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--primary)" }}>
                {attempt.score !== null && attempt.score !== undefined
                  ? `${attempt.score} / ${attempt.max_score}`
                  : attempt.score === null ? "Chờ chấm" : "Chưa công bố điểm"}
              </div>
              {attempt.score === null && (
                <p className="ea-muted" style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                  Bài làm có câu tự luận đang chờ giáo viên chấm điểm.
                </p>
              )}
            </div>

            <div style={{ fontSize: "0.9rem", color: "var(--muted)", textAlign: "right" }}>
              {attempt.submitted_at && (
                <p style={{ margin: 0 }}>
                  Nộp lúc: {new Date(attempt.submitted_at).toLocaleString("vi-VN")}
                </p>
              )}
              <span
                className={`ea-chip ${attempt.status === "graded" ? "ea-chip--ok" : "ea-chip--warn"}`}
                style={{ marginTop: "4px" }}
              >
                {attempt.status === "graded" ? "Đã chấm hoàn tất" : "Chờ hoàn thành"}
              </span>
            </div>
          </div>

          {/* Question Review List */}
          <div style={{ display: "grid", gap: "var(--space-4)" }}>
            <h3>Chi tiết các câu hỏi</h3>

            {attempt.questions.map((q, idx) => {
              const studentAnswer = attempt.answers[q.question_id];
              const revealedCorrect = q.correct;
              const revealedExplanation = q.explanation;
              const itemScore = attempt.item_scores?.[q.question_id];

              const hasRevealedAnswer = revealedCorrect !== undefined && revealedCorrect !== null;

              return (
                <div key={q.question_id} className="ea-card" style={{ padding: "var(--space-4)" }}>
                  <div className="ea-toolbar" style={{ marginBottom: "var(--space-2)" }}>
                    <span style={{ fontWeight: 700 }}>
                      Câu {idx + 1}. {q.prompt}
                    </span>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                      <span className="ea-chip">Tối đa {q.points} điểm</span>
                      {itemScore && (
                        <span className="ea-chip ea-chip--ok">
                          Đạt: {itemScore.points}/{q.points} điểm
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Options display */}
                  {q.options && q.options.length > 0 && (
                    <div style={{ display: "grid", gap: "6px", margin: "var(--space-3) 0" }}>
                      {q.options.map((opt) => {
                        const isSelected =
                          studentAnswer === opt.id ||
                          (Array.isArray(studentAnswer) && studentAnswer.includes(opt.id));
                        const isCorrectOption =
                          revealedCorrect === opt.id ||
                          (Array.isArray(revealedCorrect) && revealedCorrect.includes(opt.id));

                        let bg = "transparent";
                        let border = "1px solid var(--line)";
                        if (hasRevealedAnswer) {
                          if (isCorrectOption) {
                            bg = "rgba(34, 197, 94, 0.12)";
                            border = "1px solid var(--success, #22c55e)";
                          } else if (isSelected && !isCorrectOption) {
                            bg = "rgba(239, 68, 68, 0.12)";
                            border = "1px solid var(--danger, #ef4444)";
                          }
                        } else if (isSelected) {
                          bg = "var(--primary-subtle, rgba(59,130,246,0.08))";
                          border = "1px solid var(--primary)";
                        }

                        return (
                          <div
                            key={opt.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              padding: "8px 12px",
                              borderRadius: "var(--radius-sm)",
                              border,
                              background: bg,
                              fontSize: "0.95rem",
                            }}
                          >
                            <span>
                              {isSelected ? "● " : "○ "}
                              {opt.text}
                            </span>
                            <div style={{ display: "flex", gap: "6px" }}>
                              {isSelected && <span className="ea-chip">Đã chọn</span>}
                              {hasRevealedAnswer && isCorrectOption && (
                                <span className="ea-chip ea-chip--ok">Đáp án đúng</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* True / False display */}
                  {q.kind === "true_false" && (
                    <div style={{ margin: "var(--space-2) 0" }}>
                      <p>
                        <strong>Bạn đã chọn:</strong> {studentAnswer === true ? "Đúng" : studentAnswer === false ? "Sai" : "Chưa chọn"}
                      </p>
                      {hasRevealedAnswer && (
                        <p style={{ color: "var(--success, #16a34a)" }}>
                          <strong>Đáp án đúng:</strong> {revealedCorrect === true ? "Đúng" : "Sai"}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Short Answer display */}
                  {q.kind === "short" && (
                    <div style={{ margin: "var(--space-2) 0" }}>
                      <p>
                        <strong>Câu trả lời của bạn:</strong> {String(studentAnswer ?? "—")}
                      </p>
                      {hasRevealedAnswer && (
                        <p style={{ color: "var(--success, #16a34a)" }}>
                          <strong>Đáp án đúng:</strong>{" "}
                          {Array.isArray(revealedCorrect) ? revealedCorrect.join(" | ") : String(revealedCorrect)}
                        </p>
                      )}
                    </div>
                  )}

                  {/* Essay display */}
                  {q.kind === "essay" && (
                    <div style={{ margin: "var(--space-2) 0" }}>
                      <div
                        style={{
                          background: "var(--surface-subtle, #f9f9f9)",
                          padding: "10px",
                          borderRadius: "4px",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        <strong>Bài làm của bạn:</strong>
                        <p style={{ margin: "4px 0 0" }}>{String(studentAnswer || "Chưa làm")}</p>
                      </div>

                      {itemScore && (
                        <div
                          style={{
                            marginTop: "8px",
                            padding: "8px 12px",
                            background: "rgba(59, 130, 246, 0.08)",
                            borderRadius: "4px",
                          }}
                        >
                          <strong>Điểm: {itemScore.points}/{q.points}</strong>
                          {itemScore.feedback && <p style={{ margin: "4px 0 0" }}>Nhận xét: {itemScore.feedback}</p>}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Explanation if revealed */}
                  {revealedExplanation && (
                    <div
                      style={{
                        marginTop: "var(--space-2)",
                        padding: "8px 12px",
                        background: "var(--surface-subtle, #f4f4f5)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.9rem",
                      }}
                    >
                      <strong>Lời giải chi tiết:</strong>
                      <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{revealedExplanation}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
