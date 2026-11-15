import { useEffect, useRef, useState } from "react";
import {
  type AnswerValue,
  type AttemptView,
  type QuizStudentView,
  lmsApi,
} from "../../api-client/lms";
import { navigate } from "../../app/router";
import { ApiError } from "../../api-client/http";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { AnswerAutosave } from "./answerAutosave";
import { useCountdown } from "./countdown";
import "./lms.css";

export function QuizTake({ classId, quizId }: { classId: string; quizId: string }) {
  const quizResource = useResource(
    () => lmsApi.quizzes.get(classId, quizId) as Promise<QuizStudentView>,
    [classId, quizId],
  );

  const quiz = quizResource.data;

  const [attempt, setAttempt] = useState<AttemptView | null>(null);
  const [starting, setStarting] = useState(false);
  const [errorNotice, setErrorNotice] = useState("");

  // Answers state
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const saverRef = useRef<AnswerAutosave | null>(null);
  const startingRef = useRef(false);
  const submittingRef = useRef(false);
  const [fetchedAt, setFetchedAt] = useState<number>();

  // Confirm submit dialog
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Resume or start check on initial load
  useEffect(() => {
    if (!quiz || attempt || startingRef.current) return;
    const inProgress = quiz.attempts?.find((a) => a.status === "in_progress");
    if (inProgress) {
      // Auto resume
      void handleStartOrResume();
    }
  }, [quiz]);

  async function handleStartOrResume() {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setErrorNotice("");
    try {
      const res = await lmsApi.quizzes.startAttempt(classId, quizId);
      setFetchedAt(Date.now());
      setAttempt(res);
      setAnswers(res.answers ?? {});
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409 && err.message.includes("attempt_closed")) {
        navigate(`/student/classes/${classId}/quizzes/${quizId}/result`);
        return;
      }
      setErrorNotice(errorMessage(err));
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }

  // Countdown timer hook
  const { formatted, remainingMs, isExpired } = useCountdown({
    deadlineAt: attempt?.deadline_at,
    serverNow: attempt?.server_now,
    fetchTimeMs: fetchedAt,
    onTimeout: () => {
      // Auto submit when time expires
      void handleSubmit();
    },
  });

  useEffect(() => {
    if (!attempt) return;
    const saver = new AnswerAutosave(
      (questionId, value) => lmsApi.attempts.saveAnswer(classId, attempt.id, questionId, value),
      (pending) => setSaveStatus(pending ? "saving" : "saved"),
      (error) => {
        if (error instanceof ApiError && error.status === 409 && error.message === "attempt_closed") {
          navigate(`/student/classes/${classId}/quizzes/${quizId}/result`);
        } else {
          setSaveStatus("idle");
          setErrorNotice(errorMessage(error));
        }
      },
    );
    saverRef.current = saver;
    return () => { saver.dispose(); saverRef.current = null; };
  }, [classId, quizId, attempt?.id]);

  function handleAnswerChange(questionId: string, value: AnswerValue) {
    if (!attempt || submittingRef.current || isExpired) return;
    setAnswers((previous) => ({ ...previous, [questionId]: value }));
    setErrorNotice("");
    saverRef.current?.change(questionId, value);
  }

  async function handleSubmit() {
    if (!attempt || submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setErrorNotice("");
    try {
      await saverRef.current?.flush();
      await lmsApi.attempts.submit(classId, attempt.id);
      navigate(`/student/classes/${classId}/quizzes/${quizId}/result`);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 409 && error.message === "attempt_closed") {
        navigate(`/student/classes/${classId}/quizzes/${quizId}/result`);
        return;
      }
      setErrorNotice(errorMessage(error));
      submittingRef.current = false;
      setSubmitting(false);
      setShowConfirm(false);
    }
  }

  if (quizResource.loading && !quiz) {
    return (
      <div className="ea-page">
        <p className="ea-muted">Đang tải bài kiểm tra…</p>
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
          onClick={() => navigate(`/student/classes/${classId}`)}
        >
          <Icon name="chevron-left" /> Về lớp học
        </button>
      </div>
    );
  }

  // Pre-start screen
  if (!attempt) {
    const attemptsUsed = quiz.attempts?.length ?? 0;
    const maxAttempts = quiz.max_attempts;
    const hasAttemptsLeft = maxAttempts === 0 || attemptsUsed < maxAttempts;
    const resumable = quiz.attempts.some((entry) => entry.status === "in_progress");
    const canStart = resumable || (quiz.state === "open" && hasAttemptsLeft);

    return (
      <div className="ea-page lms-quiz-take">
        <button
          className="ea-back"
          type="button"
          onClick={() => navigate(`/student/classes/${classId}`)}
        >
          <Icon name="chevron-left" /> Về lớp học
        </button>

        <div className="ea-card" style={{ maxWidth: "700px", margin: "0 auto" }}>
          <h2>{quiz.title || "Bài kiểm tra"}</h2>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "var(--space-3)",
              margin: "var(--space-4) 0",
            }}
          >
            <div>
              <span className="ea-muted">Trạng thái:</span>
              <p style={{ fontWeight: 600 }}>
                {(quiz.state === "open") ? (
                  <span className="ea-chip ea-chip--ok">Đang mở</span>
                ) : (
                  <span className="ea-chip ea-chip--warn">{quiz.state === "upcoming" ? "Sắp mở" : "Đã đóng"}</span>
                )}
              </p>
            </div>

            <div>
              <span className="ea-muted">Thời lượng:</span>
              <p style={{ fontWeight: 600 }}>
                {quiz.duration_minutes ? `${quiz.duration_minutes} phút` : "Không giới hạn"}
              </p>
            </div>

            <div>
              <span className="ea-muted">Số câu hỏi:</span>
              <p style={{ fontWeight: 600 }}>{quiz.question_count} câu</p>
            </div>

            <div>
              <span className="ea-muted">Số lượt làm bài:</span>
              <p style={{ fontWeight: 600 }}>
                {attemptsUsed} / {maxAttempts === 0 ? "Không giới hạn" : `${maxAttempts} lượt`}
              </p>
            </div>
          </div>

          {errorNotice && <div className="ea-error" style={{ marginBottom: "var(--space-3)" }}>{errorNotice}</div>}

          {attemptsUsed > 0 && (
            <div style={{ marginBottom: "var(--space-4)" }}>
              <h4>Lịch sử các lượt làm bài</h4>
              <ul style={{ paddingLeft: "20px" }}>
                {quiz.attempts.map((att) => (
                  <li key={att.id} style={{ margin: "4px 0" }}>
                    Lần {att.attempt_no}:{" "}
                    <strong>
                      {att.status === "in_progress" ? "Đang làm" : "Đã nộp"}
                    </strong>{" "}
                    ({att.submitted_at ? new Date(att.submitted_at).toLocaleString("vi-VN") : "Đang làm"})
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="button button--secondary"
                style={{ marginTop: "8px" }}
                onClick={() => navigate(`/student/classes/${classId}/quizzes/${quizId}/result`)}
              >
                Xem chi tiết kết quả lượt đã làm
              </button>
            </div>
          )}

          <div style={{ marginTop: "var(--space-4)" }}>
            <button
              type="button"
              className="button button--primary"
              disabled={!canStart || starting}
              onClick={handleStartOrResume}
            >
              {starting
                ? "Đang khởi tạo bài làm…"
                : resumable ? "Tiếp tục làm bài" : attemptsUsed > 0
                  ? "Bắt đầu lượt làm mới"
                  : "Bắt đầu làm bài"}
            </button>
            {!canStart && (
              <p className="ea-muted" style={{ marginTop: "8px" }}>
                {!hasAttemptsLeft
                  ? "Bạn đã hết số lượt làm bài kiểm tra này."
                  : "Bài kiểm tra hiện chưa mở hoặc đã kết thúc."}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Active quiz taking screen
  const questions = attempt.questions ?? [];
  const unansweredCount = questions.filter((q) => {
    const ans = answers[q.question_id];
    if (ans === undefined || ans === null || ans === "") return true;
    if (Array.isArray(ans) && ans.length === 0) return true;
    return false;
  }).length;

  return (
    <div className="ea-page lms-quiz-take">
      {/* Sticky Top Header with Timer and Status */}
      <div
        className="ea-card lms-quiz-take-header"
        style={{
          position: "sticky",
          top: "var(--space-2)",
          zIndex: 100,
          boxShadow: "var(--shadow-md, 0 4px 12px rgba(0,0,0,0.08))",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          padding: "var(--space-3) var(--space-4)",
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>{quiz.title || "Bài kiểm tra"}</h3>
          <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
            Lần làm {attempt.attempt_no} · {questions.length} câu hỏi
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          {attempt.deadline_at && (
            <div
              className={`lms-countdown-badge ${isExpired ? "is-expired" : ""}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                fontWeight: 700,
                fontSize: "1.1rem",
                color: remainingMs !== null && remainingMs < 60000 ? "var(--danger, #ef4444)" : "var(--primary)",
                background: "var(--surface-subtle, rgba(0,0,0,0.04))",
                padding: "6px 12px",
                borderRadius: "var(--radius-pill)",
              }}
            >
              <Icon name="history" /> {formatted}
            </div>
          )}

          <span
            style={{
              fontSize: "0.85rem",
              color: saveStatus === "saving" ? "var(--warning)" : "var(--muted)",
              minWidth: "70px",
            }}
          >
            {saveStatus === "saving" ? "Đang lưu…" : saveStatus === "saved" ? "Đã lưu" : ""}
          </span>

          <button
            type="button"
            className="button button--primary"
            disabled={submitting}
            onClick={() => setShowConfirm(true)}
          >
            {submitting ? "Đang nộp…" : "Nộp bài"}
          </button>
        </div>
      </div>

      {errorNotice && <div className="ea-error" style={{ margin: "var(--space-3) 0" }}>{errorNotice}</div>}

      {/* Question List */}
      <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
        {questions.map((q, idx) => {
          const currentVal = answers[q.question_id];

          return (
            <div
              key={q.question_id}
              className="ea-card"
              style={{ padding: "var(--space-4)", borderRadius: "var(--radius-md)" }}
            >
              <div className="ea-toolbar" style={{ marginBottom: "var(--space-2)" }}>
                <span style={{ fontWeight: 700, fontSize: "1.05rem" }}>
                  Câu {idx + 1}
                </span>
                <span className="ea-chip">{q.points} điểm</span>
              </div>

              <p style={{ margin: "var(--space-2) 0 var(--space-4)", fontSize: "1rem", whiteSpace: "pre-wrap" }}>
                {q.prompt}
              </p>

              {/* Single choice */}
              {q.kind === "single" && q.options && (
                <div style={{ display: "grid", gap: "var(--space-2)" }}>
                  {q.options.map((opt) => (
                    <label
                      key={opt.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        padding: "8px 12px",
                        borderRadius: "var(--radius-sm)",
                        border: "1px solid var(--line)",
                        cursor: "pointer",
                        background: currentVal === opt.id ? "var(--primary-subtle, rgba(59,130,246,0.08))" : "transparent",
                      }}
                    >
                      <input
                        type="radio"
                        name={`q_${q.question_id}`}
                        checked={currentVal === opt.id}
                        onChange={() => handleAnswerChange(q.question_id, opt.id)}
                      />
                      <span>{opt.text}</span>
                    </label>
                  ))}
                </div>
              )}

              {/* Multi choice */}
              {q.kind === "multi" && q.options && (
                <div style={{ display: "grid", gap: "var(--space-2)" }}>
                  {q.options.map((opt) => {
                    const selectedList = Array.isArray(currentVal) ? (currentVal as string[]) : [];
                    const isChecked = selectedList.includes(opt.id);

                    return (
                      <label
                        key={opt.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                          padding: "8px 12px",
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--line)",
                          cursor: "pointer",
                          background: isChecked ? "var(--primary-subtle, rgba(59,130,246,0.08))" : "transparent",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              handleAnswerChange(q.question_id, [...selectedList, opt.id]);
                            } else {
                              handleAnswerChange(
                                q.question_id,
                                selectedList.filter((k) => k !== opt.id),
                              );
                            }
                          }}
                        />
                        <span>{opt.text}</span>
                      </label>
                    );
                  })}
                </div>
              )}

              {/* True / False */}
              {q.kind === "true_false" && (
                <div style={{ display: "flex", gap: "var(--space-4)" }}>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "8px 16px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--line)",
                      cursor: "pointer",
                      background: currentVal === true ? "var(--primary-subtle, rgba(59,130,246,0.08))" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name={`tf_${q.question_id}`}
                      checked={currentVal === true}
                      onChange={() => handleAnswerChange(q.question_id, true)}
                    />
                    Đúng
                  </label>

                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "8px 16px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--line)",
                      cursor: "pointer",
                      background: currentVal === false ? "var(--primary-subtle, rgba(59,130,246,0.08))" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name={`tf_${q.question_id}`}
                      checked={currentVal === false}
                      onChange={() => handleAnswerChange(q.question_id, false)}
                    />
                    Sai
                  </label>
                </div>
              )}

              {/* Short Answer */}
              {q.kind === "short" && (
                <label className="field">
                  <span>Câu trả lời của bạn:</span>
                  <input
                    type="text"
                    value={(currentVal as string) ?? ""}
                    onChange={(e) => handleAnswerChange(q.question_id, e.target.value)}
                    placeholder="Nhập câu trả lời ngắn…"
                  />
                </label>
              )}

              {/* Essay */}
              {q.kind === "essay" && (
                <label className="field">
                  <span>Bài làm tự luận của bạn:</span>
                  <textarea
                    rows={6}
                    value={(currentVal as string) ?? ""}
                    onChange={(e) => handleAnswerChange(q.question_id, e.target.value)}
                    placeholder="Trình bày bài làm chi tiết tại đây…"
                  />
                </label>
              )}
            </div>
          );
        })}
      </div>

      {/* Bottom Submit Button */}
      <div style={{ marginTop: "var(--space-6)", textAlign: "center" }}>
        <button
          type="button"
          className="button button--primary"
          style={{ minWidth: "200px" }}
          disabled={submitting}
          onClick={() => setShowConfirm(true)}
        >
          {submitting ? "Đang nộp bài…" : "Nộp bài kiểm tra"}
        </button>
      </div>

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={showConfirm}
        title="Xác nhận nộp bài kiểm tra"
        description={
          unansweredCount > 0
            ? `Bạn vẫn còn ${unansweredCount} câu chưa trả lời. Bạn có chắc chắn muốn nộp bài ngay bây giờ?`
            : "Bạn đã trả lời tất cả các câu hỏi. Bạn có chắc chắn muốn nộp bài? Sau khi nộp, bạn không thể thay đổi đáp án."
        }
        confirmLabel="Nộp bài ngay"
        onConfirm={() => handleSubmit()}
        onCancel={() => setShowConfirm(false)}
        busy={submitting}
      />
    </div>
  );
}
