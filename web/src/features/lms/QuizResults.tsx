import { useState } from "react";
import { type AttemptDetailView, type QuizResultsView, lmsApi } from "../../api-client/lms";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { BulkGradingSuggestions, GradingSuggestionButton } from "./SuggestionReview";

export interface QuizResultsProps {
  classId: string;
  quizId: string;
  aiGrading: boolean;
}

export function QuizResults({ classId, quizId, aiGrading }: QuizResultsProps) {
  const resultsResource = useResource(() => lmsApi.quizzes.results(classId, quizId), [classId, quizId]);
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);

  const data: QuizResultsView | null = resultsResource.data;

  if (resultsResource.loading && !data) {
    return <p className="ea-muted">Đang tải kết quả bài kiểm tra…</p>;
  }

  if (resultsResource.error) {
    return <div className="ea-error">{resultsResource.error}</div>;
  }

  if (!data) {
    return <p className="ea-muted">Chưa có dữ liệu kết quả.</p>;
  }

  const distribution = data.stats.distribution ?? {};
  const maxBucketCount = Math.max(1, ...Object.values(distribution));

  return (
    <div className="lms-quiz-results" style={{ display: "grid", gap: "var(--space-4)" }}>
      {aiGrading && <BulkGradingSuggestions classId={classId}
        targets={data.attempts.filter((attempt) => attempt.status !== "in_progress").flatMap((attempt) => attempt.questions.filter((question) => question.kind === "essay" && !attempt.item_scores?.[question.question_id]).map((question) => ({ type: "attempt_question" as const, id: `${attempt.id}:${question.question_id}`, name: `${attempt.student_name} · Lần ${attempt.attempt_no} · ${question.prompt}` })))}
        onReviewed={() => resultsResource.reload()} />}
      {/* Overview Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "var(--space-3)" }}>
        <div className="ea-card">
          <span className="ea-muted">Số lượt làm bài</span>
          <strong style={{ fontSize: "1.5rem" }}>{data.attempts.length}</strong>
        </div>
        <div className="ea-card">
          <span className="ea-muted">Số học sinh đã tham gia</span>
          <strong style={{ fontSize: "1.5rem" }}>{data.stats.attempted_students}</strong>
        </div>
        <div className="ea-card">
          <span className="ea-muted">Điểm trung bình</span>
          <strong style={{ fontSize: "1.5rem", color: "var(--primary)" }}>
            {data.stats.average !== null && data.stats.average !== undefined
              ? Number(data.stats.average).toFixed(1)
              : "—"}
          </strong>
        </div>
      </div>

      {/* Distribution Bars */}
      {Object.keys(distribution).length > 0 && (
        <div className="ea-card">
          <h4 style={{ margin: "0 0 var(--space-3)" }}>Phổ điểm</h4>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {Object.entries(distribution).map(([range, count]) => {
              const pct = (count / maxBucketCount) * 100;
              return (
                <div key={range} style={{ display: "grid", gridTemplateColumns: "80px 1fr 40px", alignItems: "center", gap: "var(--space-2)" }}>
                  <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{range}</span>
                  <div style={{ background: "var(--surface-subtle, #f0f0f0)", borderRadius: "4px", height: "16px", overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${pct}%`,
                        background: "var(--primary, #3b82f6)",
                        height: "100%",
                        borderRadius: "4px",
                        transition: "width 200ms ease",
                      }}
                    />
                  </div>
                  <span style={{ fontSize: "0.85rem", textAlign: "right" }}>{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Questions Correct Rate */}
      {data.stats.per_question && data.stats.per_question.length > 0 && (
        <div className="ea-card">
          <h4 style={{ margin: "0 0 var(--space-3)" }}>Tỉ lệ đúng từng câu</h4>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {data.stats.per_question.map((q, idx) => {
              const rate = q.correct_rate !== null && q.correct_rate !== undefined ? Math.round(q.correct_rate * 100) : null;
              return (
                <div
                  key={q.question_id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 120px 50px",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    padding: "6px 0",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <span style={{ fontSize: "0.9rem" }}>
                    <strong>Câu {idx + 1}:</strong> {data.attempts.flatMap((attempt) => attempt.questions).find((question) => question.question_id === q.question_id)?.prompt ?? ""}
                  </span>
                  <div style={{ background: "var(--surface-subtle, #f0f0f0)", borderRadius: "4px", height: "10px", overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${rate ?? 0}%`,
                        background: rate !== null && rate >= 50 ? "var(--success, #22c55e)" : "var(--warning, #f59e0b)",
                        height: "100%",
                      }}
                    />
                  </div>
                  <span style={{ fontSize: "0.85rem", textAlign: "right", fontWeight: 600 }}>
                    {rate !== null ? `${rate}%` : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Attempts Table */}
      <div className="ea-card">
        <h4 style={{ margin: "0 0 var(--space-3)" }}>Danh sách bài nộp ({data.attempts.length})</h4>
        {data.attempts.length === 0 ? (
          <p className="ea-muted">Chưa có học sinh nào nộp bài.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="ea-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--line)", textAlign: "left" }}>
                  <th style={{ padding: "8px" }}>Học sinh</th>
                  <th style={{ padding: "8px" }}>Lần làm</th>
                  <th style={{ padding: "8px" }}>Thời gian nộp</th>
                  <th style={{ padding: "8px" }}>Trạng thái</th>
                  <th style={{ padding: "8px" }}>Điểm số</th>
                  <th style={{ padding: "8px" }}>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {data.attempts.map((att) => (
                  <tr key={att.id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "8px", fontWeight: 600 }}>{att.student_name}</td>
                    <td style={{ padding: "8px" }}>Lần {att.attempt_no}</td>
                    <td style={{ padding: "8px", fontSize: "0.85rem" }}>
                      {att.submitted_at ? new Date(att.submitted_at).toLocaleString("vi-VN") : "Đang làm"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      <span
                        className={`ea-chip ${
                          att.status === "graded"
                            ? "ea-chip--ok"
                            : att.status === "submitted"
                              ? "ea-chip--warn"
                              : ""
                        }`}
                      >
                        {att.status === "graded"
                          ? "Đã chấm"
                          : att.status === "submitted"
                            ? "Chờ chấm tự luận"
                            : "Đang làm"}
                      </span>
                    </td>
                    <td style={{ padding: "8px", fontWeight: 700 }}>
                      {att.score !== null && att.score !== undefined ? `${att.score}/${att.max_score}` : "—"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      <button
                        type="button"
                        className="button button--secondary"
                        style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                        onClick={() => setSelectedAttemptId(att.id)}
                      >
                        Xem & Chấm
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Essay Grading Modal */}
      {selectedAttemptId && (
        <AttemptGradingModal
          key={selectedAttemptId}
          classId={classId}
          attemptId={selectedAttemptId}
          aiGrading={aiGrading}
          onClose={() => setSelectedAttemptId(null)}
          onGraded={() => {
            resultsResource.reload();
          }}
        />
      )}
    </div>
  );
}

interface AttemptGradingModalProps {
  classId: string;
  attemptId: string;
  aiGrading: boolean;
  onClose: () => void;
  onGraded: () => void;
}

function AttemptGradingModal({ classId, attemptId, aiGrading, onClose, onGraded }: AttemptGradingModalProps) {
  const attemptResource = useResource(() => lmsApi.attempts.get(classId, attemptId), [classId, attemptId]);
  const [busy, setBusy] = useState(false);
  const [errorNotice, setErrorNotice] = useState("");
  const [scores, setScores] = useState<Record<string, { points: number; feedback: string }>>({});

  const attempt: AttemptDetailView | null = attemptResource.data;

  // Initialize scores for essay questions
  const essayQuestions = (attempt?.questions ?? []).filter((q) => q.kind === "essay");

  async function handleGradeQuestion(questionId: string) {
    const s = scores[questionId] ?? attempt?.item_scores?.[questionId] ?? { points: 0, feedback: "" };
    setBusy(true);
    setErrorNotice("");
    try {
      await lmsApi.attempts.gradeQuestion(classId, attemptId, questionId, s.points, s.feedback);
      attemptResource.reload();
      onGraded();
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog frosted"
        style={{ maxWidth: "800px", width: "95%", maxHeight: "85vh", overflowY: "auto" }}
        role="dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ea-toolbar">
          <h3>Chi tiết bài làm (Lần {attempt?.attempt_no ?? 1})</h3>
          <button className="button button--ghost" type="button" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {attemptResource.loading ? (
          <p className="ea-muted">Đang tải bài làm…</p>
        ) : !attempt ? (
          <div className="ea-error">Không tải được bài làm.</div>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-3)" }}>
            {errorNotice && <div className="ea-error">{errorNotice}</div>}

            <div style={{ display: "flex", gap: "var(--space-4)", fontSize: "0.9rem" }}>
              <span>
                <strong>Tổng điểm:</strong>{" "}
                {attempt.score !== null && attempt.score !== undefined
                  ? `${attempt.score}/${attempt.max_score}`
                  : "Chờ hoàn thành chấm"}
              </span>
              <span>
                <strong>Trạng thái:</strong> {attempt.status === "graded" ? "Đã chấm xong" : "Chờ chấm"}
              </span>
            </div>

            {essayQuestions.length === 0 ? (
              <p className="ea-muted">Bài kiểm tra này không có câu tự luận cần chấm tay.</p>
            ) : (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <h4>Chấm câu tự luận ({essayQuestions.length} câu)</h4>
                {essayQuestions.map((q, idx) => {
                  const studentAnswer = (attempt.answers[q.question_id] as string) || "—";
                  const existingScore = attempt.item_scores?.[q.question_id];
                  const currentScore = scores[q.question_id] ?? {
                    points: existingScore?.points ?? 0,
                    feedback: existingScore?.feedback ?? "",
                  };

                  return (
                    <div key={q.question_id} className="ea-card" style={{ display: "grid", gap: "var(--space-2)" }}>
                      <div className="ea-toolbar">
                        <strong>
                          Câu {idx + 1}: {q.prompt}
                        </strong>
                        <span className="ea-chip">Tối đa {q.points} điểm</span>
                      </div>

                      <div
                        style={{
                          background: "var(--surface-subtle, #f9f9f9)",
                          padding: "10px",
                          borderRadius: "4px",
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        <strong>Bài làm của học sinh:</strong>
                        <p style={{ margin: "4px 0 0" }}>{studentAnswer}</p>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "var(--space-2)" }}>
                        <label className="field">
                          <span>Điểm chấm</span>
                          <input
                            type="number"
                            min="0"
                            max={q.points}
                            step="0.25"
                            value={currentScore.points}
                            onChange={(e) =>
                              setScores({
                                ...scores,
                                [q.question_id]: {
                                  ...currentScore,
                                  points: parseFloat(e.target.value) || 0,
                                },
                              })
                            }
                            disabled={busy}
                          />
                        </label>
                        <label className="field">
                          <span>Nhận xét</span>
                          <input
                            type="text"
                            placeholder="Nhận xét cho học sinh…"
                            value={currentScore.feedback}
                            onChange={(e) =>
                              setScores({
                                ...scores,
                                [q.question_id]: {
                                  ...currentScore,
                                  feedback: e.target.value,
                                },
                              })
                            }
                            disabled={busy}
                          />
                        </label>
                      </div>

                      <div className="ea-toolbar__actions" style={{ justifyContent: "space-between" }}>
                        {aiGrading && attempt.status !== "in_progress" && <GradingSuggestionButton
                          classId={classId}
                          targetType="attempt_question"
                          targetId={`${attemptId}:${q.question_id}`}
                          onApplyGrade={(pts, fb) => {
                            setScores({
                              ...scores,
                              [q.question_id]: { points: pts, feedback: fb },
                            });
                            attemptResource.reload();
                            onGraded();
                          }}
                        />}

                        <button
                          type="button"
                          className="button button--primary"
                          disabled={busy || attempt.status === "in_progress"}
                          onClick={() => handleGradeQuestion(q.question_id)}
                        >
                          {busy ? "Đang lưu…" : "Lưu điểm câu này"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="dialog-actions" style={{ marginTop: "var(--space-3)" }}>
              <button type="button" className="button button--secondary" onClick={onClose}>
                Đóng
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
