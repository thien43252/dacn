import { useState } from "react";
import {
  type QuestionKind,
  type Quiz,
  type QuizQuestion,
  type QuizTeacherView,
  lmsApi,
} from "../../api-client/lms";
import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { localDateTime } from "./formValues";
import { QuestionEditor } from "./QuestionEditor";
import { QuizResults } from "./QuizResults";
import { QuestionSuggestionModal } from "./SuggestionReview";
import "./lms.css";

const KIND_NAMES: Record<QuestionKind, string> = {
  single: "Trắc nghiệm 1 đáp án",
  multi: "Nhiều đáp án",
  true_false: "Đúng / Sai",
  short: "Trả lời ngắn",
  essay: "Tự luận",
};

export function QuizEditor({ classId, quizId }: { classId: string; quizId: string }) {
  const [tab, setTab] = useState<"questions" | "results">("questions");
  const quizResource = useResource(
    () => lmsApi.quizzes.get(classId, quizId) as Promise<QuizTeacherView>,
    [classId, quizId],
  );

  const quiz = quizResource.data;
  const agentsResource = useResource(() => lmsApi.assist.agents(classId, "questions"), [classId]);

  // Question editing / adding state
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<QuizQuestion | null>(null);
  const [deletingQuestion, setDeletingQuestion] = useState<QuizQuestion | null>(null);
  const [showAiModal, setShowAiModal] = useState(false);

  // Regrade notice state: maps questionId -> affects count
  const [regradeMap, setRegradeMap] = useState<Record<string, number>>({});
  const [regradingId, setRegradingId] = useState<string | null>(null);

  // Config saving state
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");

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
          onClick={() => navigate(`/teacher/classes/${classId}`)}
        >
          <Icon name="chevron-left" /> Về lớp học
        </button>
      </div>
    );
  }

  const questions: QuizQuestion[] = quiz.questions ?? [];
  const totalPoints = questions.reduce((acc, q) => acc + (q.points || 0), 0);

  async function handleUpdateConfig(patch: Partial<Quiz>) {
    try {
      setBusy(true);
      setErrorNotice("");
      setNotice("");
      const updated = await lmsApi.quizzes.update(classId, quizId, patch);
      quizResource.setData({ ...quiz!, ...updated });
      setNotice("Đã lưu cấu hình bài kiểm tra.");
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleMoveQuestion(index: number, direction: "up" | "down") {
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= questions.length) return;

    const newQuestions = [...questions];
    const [moved] = newQuestions.splice(index, 1);
    newQuestions.splice(targetIndex, 0, moved);

    quizResource.setData({ ...quiz!, questions: newQuestions });
    try {
      await lmsApi.quizzes.reorderQuestions(
        classId,
        quizId,
        newQuestions.map((q) => q.id),
      );
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
      quizResource.reload();
    }
  }

  async function handleDeleteQuestion() {
    if (!deletingQuestion) return;
    setBusy(true);
    try {
      const res = await lmsApi.questions.delete(classId, deletingQuestion.id);
      if (res.affects_submitted && res.affects_submitted > 0) {
        setNotice(`Đã xoá câu hỏi (ảnh hưởng tới ${res.affects_submitted} bài nộp).`);
      } else {
        setNotice("Đã xoá câu hỏi.");
      }
      setDeletingQuestion(null);
      quizResource.reload();
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegrade(questionId: string) {
    try {
      setRegradingId(questionId);
      setErrorNotice("");
      const res = await lmsApi.questions.regrade(classId, questionId);
      setNotice(`Đã chấm lại thành công cho ${res.updated} bài nộp.`);
      setRegradeMap((prev) => {
        const next = { ...prev };
        delete next[questionId];
        return next;
      });
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setRegradingId(null);
    }
  }

  return (
    <div className="ea-page lms-quiz-editor">
      <button
        className="ea-back"
        type="button"
        onClick={() => navigate(`/teacher/classes/${classId}`)}
      >
        <Icon name="chevron-left" /> Về lớp học
      </button>

      <div className="ea-toolbar">
        <div>
          <h2>{quiz.title || "Quản lý bài kiểm tra"}</h2>
          <span className="ea-muted">
            {questions.length} câu hỏi · Tổng {totalPoints} điểm
          </span>
        </div>

        {/* Tab switcher */}
        <div className="ea-toolbar__actions">
          <div className="ea-subtabs" style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              className={`button ${tab === "questions" ? "button--primary" : "button--secondary"}`}
              onClick={() => setTab("questions")}
            >
              Cấu hình & Câu hỏi
            </button>
            <button
              type="button"
              className={`button ${tab === "results" ? "button--primary" : "button--secondary"}`}
              onClick={() => setTab("results")}
            >
              Kết quả làm bài
            </button>
          </div>
        </div>
      </div>

      {notice && <div className="ea-notice ea-notice--ok">{notice}</div>}
      {errorNotice && <div className="ea-error">{errorNotice}</div>}

      {tab === "results" ? (
        <QuizResults classId={classId} quizId={quizId} aiGrading={quiz.ai_grading} />
      ) : (
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {/* Config Card */}
          <div className="ea-card">
            <h3>Cấu hình bài kiểm tra</h3>
            <div
              className="ea-form-grid"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: "var(--space-3)",
                marginTop: "var(--space-3)",
              }}
            >
              <label className="field">
                <span>Thời gian mở</span>
                <input
                  type="datetime-local"
                  value={localDateTime(quiz.open_at)}
                  onChange={(e) =>
                    handleUpdateConfig({
                      open_at: e.target.value ? new Date(e.target.value).toISOString() : null,
                    })
                  }
                  disabled={busy}
                />
              </label>

              <label className="field">
                <span>Thời gian đóng</span>
                <input
                  type="datetime-local"
                  value={localDateTime(quiz.close_at)}
                  onChange={(e) =>
                    handleUpdateConfig({
                      close_at: e.target.value ? new Date(e.target.value).toISOString() : null,
                    })
                  }
                  disabled={busy}
                />
              </label>

              <label className="field">
                <span>Thời lượng làm bài (phút)</span>
                <input
                  type="number"
                  min="1"
                  placeholder="Không giới hạn"
                  value={quiz.duration_minutes ?? ""}
                  onChange={(e) =>
                    handleUpdateConfig({
                      duration_minutes: e.target.value ? parseInt(e.target.value, 10) : null,
                    })
                  }
                  disabled={busy}
                />
              </label>

              <label className="field">
                <span>Số lượt làm tối đa (0 = không giới hạn)</span>
                <input
                  type="number"
                  min="0"
                  value={quiz.max_attempts}
                  onChange={(e) =>
                    handleUpdateConfig({
                      max_attempts: parseInt(e.target.value, 10) || 0,
                    })
                  }
                  disabled={busy}
                />
              </label>

              <label className="field">
                <span>Cách tính điểm tổng</span>
                <select
                  value={quiz.scoring_policy}
                  onChange={(e) =>
                    handleUpdateConfig({
                      scoring_policy: e.target.value as "best" | "last" | "average",
                    })
                  }
                  disabled={busy}
                >
                  <option value="best">Lấy điểm cao nhất</option>
                  <option value="last">Lấy điểm lần cuối</option>
                  <option value="average">Lấy điểm trung bình</option>
                </select>
              </label>

              <label className="field">
                <span>Thời điểm hiện điểm cho học sinh</span>
                <select
                  value={quiz.show_score}
                  onChange={(e) =>
                    handleUpdateConfig({
                      show_score: e.target.value as "on_submit" | "after_close" | "never",
                    })
                  }
                  disabled={busy}
                >
                  <option value="on_submit">Ngay sau khi nộp</option>
                  <option value="after_close">Sau khi đóng bài kiểm tra</option>
                  <option value="never">Không hiển thị</option>
                </select>
              </label>

              <label className="field">
                <span>Thời điểm hiện đáp án & giải thích</span>
                <select
                  value={quiz.show_answers}
                  onChange={(e) =>
                    handleUpdateConfig({
                      show_answers: e.target.value as "on_submit" | "after_close" | "never",
                    })
                  }
                  disabled={busy}
                >
                  <option value="after_close">Sau khi đóng bài kiểm tra</option>
                  <option value="on_submit">Ngay sau khi nộp</option>
                  <option value="never">Không hiển thị</option>
                </select>
              </label>

              <label className="field">
                <span>Trọng số điểm trong sổ điểm</span>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={quiz.weight}
                  onChange={(e) =>
                    handleUpdateConfig({
                      weight: parseFloat(e.target.value) || 0,
                    })
                  }
                  disabled={busy}
                />
              </label>
            </div>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "var(--space-4)",
                marginTop: "var(--space-3)",
                paddingTop: "var(--space-3)",
                borderTop: "1px solid var(--line)",
              }}
            >
              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={quiz.shuffle_questions}
                  onChange={(e) => handleUpdateConfig({ shuffle_questions: e.target.checked })}
                  disabled={busy}
                />
                Trộn thứ tự câu hỏi
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={quiz.shuffle_options}
                  onChange={(e) => handleUpdateConfig({ shuffle_options: e.target.checked })}
                  disabled={busy}
                />
                Trộn thứ tự các lựa chọn
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={!quiz.block_agents}
                  onChange={(e) => handleUpdateConfig({ block_agents: !e.target.checked })}
                  disabled={busy}
                />
                Cho phép hỏi agent khi làm bài
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={quiz.ai_grading}
                  onChange={(e) => handleUpdateConfig({ ai_grading: e.target.checked })}
                  disabled={busy}
                />
                Trợ lý chấm AI
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={quiz.counts_in_grade}
                  onChange={(e) => handleUpdateConfig({ counts_in_grade: e.target.checked })}
                  disabled={busy}
                />
                Tính vào điểm tổng kết
              </label>
            </div>
          </div>

          {/* Question List */}
          <div className="ea-card">
            <div className="ea-toolbar">
              <h3>Danh sách câu hỏi ({questions.length})</h3>
              <div className="ea-toolbar__actions">
                {Boolean(agentsResource.data?.length) && <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => setShowAiModal(true)}
                >
                  <Icon name="sparkles" /> Gợi ý câu hỏi
                </button>}
                <button
                  type="button"
                  className="button button--primary"
                  onClick={() => setAddingQuestion(true)}
                >
                  <Icon name="plus" /> Thêm câu hỏi
                </button>
              </div>
            </div>

            {agentsResource.error && <div className="ea-error">{agentsResource.error}</div>}
            {agentsResource.data?.length === 0 && <p className="ea-muted">Cài agent Trợ giảng LMS từ <a href="/teacher/hub">Agent Hub</a> để dùng gợi ý.</p>}

            {questions.length === 0 ? (
              <p className="ea-muted" style={{ padding: "var(--space-4) 0" }}>
                Bài kiểm tra chưa có câu hỏi nào. Bạn có thể tự thêm hoặc dùng Trợ giảng LMS để gợi ý câu hỏi từ tài liệu.
              </p>
            ) : (
              <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
                {questions.map((q, idx) => {
                  const affectedCount = regradeMap[q.id];
                  return (
                    <div
                      key={q.id}
                      className="ea-card"
                      style={{
                        padding: "var(--space-3)",
                        border: "1px solid var(--line)",
                        borderRadius: "var(--radius-sm)",
                      }}
                    >
                      <div className="ea-toolbar">
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{ fontWeight: 700 }}>Câu {idx + 1}.</span>
                          <span className="ea-chip">{KIND_NAMES[q.kind] || q.kind}</span>
                          <span className="ea-chip ea-chip--info">{q.points} điểm</span>
                        </div>

                        <div className="ea-toolbar__actions">
                          <button
                            type="button"
                            className="button button--ghost"
                            disabled={idx === 0 || busy}
                            onClick={() => handleMoveQuestion(idx, "up")}
                            title="Di chuyển lên"
                          >
                            <Icon name="chevron-up" />
                          </button>
                          <button
                            type="button"
                            className="button button--ghost"
                            disabled={idx === questions.length - 1 || busy}
                            onClick={() => handleMoveQuestion(idx, "down")}
                            title="Di chuyển xuống"
                          >
                            <Icon name="chevron-down" />
                          </button>
                          <button
                            type="button"
                            className="button button--secondary"
                            onClick={() => setEditingQuestion(q)}
                            title="Sửa câu hỏi"
                          >
                            <Icon name="edit" /> Sửa
                          </button>
                          <button
                            type="button"
                            className="button button--ghost"
                            onClick={() => setDeletingQuestion(q)}
                            title="Xoá câu hỏi"
                          >
                            <Icon name="trash" />
                          </button>
                        </div>
                      </div>

                      <p style={{ margin: "var(--space-2) 0", fontWeight: 500 }}>{q.prompt}</p>

                      {q.options && q.options.length > 0 && (
                        <div style={{ display: "grid", gap: "4px", paddingLeft: "16px" }}>
                          {q.options.map((opt) => (
                            <div
                              key={opt.id}
                              style={{
                                fontSize: "0.9rem",
                                fontWeight:
                                  q.answer_key === opt.id ||
                                  (Array.isArray(q.answer_key) && q.answer_key.includes(opt.id))
                                    ? 700
                                    : 400,
                                color:
                                  q.answer_key === opt.id ||
                                  (Array.isArray(q.answer_key) && q.answer_key.includes(opt.id))
                                    ? "var(--success, #16a34a)"
                                    : "inherit",
                              }}
                            >
                              • {opt.text}
                            </div>
                          ))}
                        </div>
                      )}

                      {q.explanation && (
                        <p className="ea-muted" style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                          <em>Lời giải:</em> {q.explanation}
                        </p>
                      )}

                      {/* Regrade warning and button if affected */}
                      {affectedCount && affectedCount > 0 ? (
                        <div
                          className="ea-notice ea-notice--warn"
                          style={{
                            marginTop: "8px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <span>Thay đổi này ảnh hưởng đến {affectedCount} bài nộp trước đó.</span>
                          <button
                            type="button"
                            className="button button--primary"
                            disabled={regradingId === q.id}
                            onClick={() => handleRegrade(q.id)}
                          >
                            {regradingId === q.id ? "Đang chấm lại…" : "Chấm lại"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Question Modal */}
      {addingQuestion && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setAddingQuestion(false)}>
          <div
            className="dialog frosted"
            style={{ maxWidth: "750px", width: "95%", maxHeight: "90vh", overflowY: "auto" }}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <QuestionEditor
              onSave={async (newQ) => {
                await lmsApi.quizzes.addQuestion(classId, quizId, newQ);
                setAddingQuestion(false);
                quizResource.reload();
              }}
              onCancel={() => setAddingQuestion(false)}
            />
          </div>
        </div>
      )}

      {/* Edit Question Modal */}
      {editingQuestion && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setEditingQuestion(null)}>
          <div
            className="dialog frosted"
            style={{ maxWidth: "750px", width: "95%", maxHeight: "90vh", overflowY: "auto" }}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <QuestionEditor
              initial={editingQuestion}
              onSave={async (patch) => {
                const res = await lmsApi.questions.update(classId, editingQuestion.id, patch);
                if (res.affects_submitted && res.affects_submitted > 0) {
                  setRegradeMap((prev) => ({
                    ...prev,
                    [editingQuestion.id]: res.affects_submitted!,
                  }));
                }
                setEditingQuestion(null);
                quizResource.reload();
              }}
              onCancel={() => setEditingQuestion(null)}
            />
          </div>
        </div>
      )}

      {/* Delete Question Confirm Dialog */}
      <ConfirmDialog
        open={Boolean(deletingQuestion)}
        title="Xác nhận xoá câu hỏi"
        description="Bạn có chắc chắn muốn xoá câu hỏi này? Các lượt đã làm vẫn giữ câu hỏi trong đề đã nhận."
        confirmLabel="Xoá câu hỏi"
        onConfirm={handleDeleteQuestion}
        onCancel={() => setDeletingQuestion(null)}
        busy={busy}
      />

      {/* Suggest Question Modal */}
      {showAiModal && (
        <QuestionSuggestionModal
          classId={classId}
          quizId={quizId}
          onClose={() => setShowAiModal(false)}
          onApplied={() => quizResource.reload()}
        />
      )}
    </div>
  );
}
