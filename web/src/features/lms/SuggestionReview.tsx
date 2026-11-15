import { useEffect, useState } from "react";
import { type AISuggestion, type AssistAgent, type QuizQuestion, type QuestionInput, type QuestionKind, type QuestionLevel, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { questionInput } from "./formValues";
import { QuestionEditor } from "./QuestionEditor";

export interface QuestionSuggestionModalProps {
  classId: string;
  quizId: string;
  onClose: () => void;
  onApplied: () => void;
}

export function QuestionSuggestionModal({
  classId,
  quizId,
  onClose,
  onApplied,
}: QuestionSuggestionModalProps) {
  const [agents, setAgents] = useState<AssistAgent[] | null>(null);
  const [loadingAgents, setLoadingAgents] = useState(true);

  // Form params
  const [count, setCount] = useState(5);
  const [kinds, setKinds] = useState<QuestionKind[]>(["single"]);
  const [level, setLevel] = useState<QuestionLevel>("thong_hieu");
  const [selectedAgent, setSelectedAgent] = useState("");

  // Suggestion state
  const [submitting, setSubmitting] = useState(false);
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null);
  const [error, setError] = useState("");

  // Review decisions state
  interface DraftDecision {
    index: number;
    action: "approve" | "edit" | "discard";
    question: QuestionInput & { source?: string };
    edited?: boolean;
  }
  const [decisions, setDecisions] = useState<DraftDecision[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [savingReview, setSavingReview] = useState(false);

  useEffect(() => {
    let active = true;
    lmsApi.assist
      .agents(classId, "questions")
      .then((res) => {
        if (!active) return;
        setAgents(res);
        if (res.length > 0) {
          setSelectedAgent(res[0].slug);
        }
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Không tải được danh sách agent.");
      })
      .finally(() => {
        if (active) setLoadingAgents(false);
      });
    return () => {
      active = false;
    };
  }, [classId]);

  // Polling for suggestion readiness
  useEffect(() => {
    if (!suggestion || suggestion.status !== "pending") return;

    let active = true;
    let polling = false;
    const timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const updated = await lmsApi.assist.getSuggestion(classId, suggestion.id);
        if (!active) return;
        setError("");
        if (updated.status !== "pending") {
          clearInterval(timer);
          setSuggestion(updated);
          if (updated.status === "ready" && updated.payload) {
            const list = updated.payload.questions ?? [];
            setDecisions(
              list.map((q, i) => ({
                index: i,
                action: "approve",
                question: q,
              })),
            );
          } else if (updated.status === "failed") {
            setError(updated.error || "Gợi ý câu hỏi thất bại từ AI.");
          }
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Không tải được gợi ý. Đang thử lại…");
      } finally {
        polling = false;
      }
    }, 2000);

    return () => { active = false; clearInterval(timer); };
  }, [classId, suggestion]);

  async function handleRequestSuggestions() {
    if (kinds.length === 0) {
      setError("Vui lòng chọn ít nhất một loại câu hỏi.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const res = await lmsApi.assist.suggestQuestions(classId, quizId, {
        agent_slug: selectedAgent || undefined,
        count,
        kinds,
        level,
      });
      setSuggestion(res);
      if (res.status === "ready") {
        setDecisions((res.payload?.questions ?? []).map((question, index) => ({ index, action: "approve", question })));
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Yêu cầu gợi ý thất bại.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApplyReview() {
    if (!suggestion) return;
    setSavingReview(true);
    setError("");
    try {
      await lmsApi.assist.reviewSuggestion(classId, suggestion.id, {
        decisions: decisions.map((d) => ({
          index: d.index,
          action: d.action,
          question: d.action === "edit" ? questionInput(d.question) : undefined,
        })),
      });
      onApplied();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Lưu quyết định duyệt thất bại.");
    } finally {
      setSavingReview(false);
    }
  }

  function handleApproveAll() {
    setDecisions((prev) => prev.map((d) => ({ ...d, action: d.edited ? "edit" : "approve" })));
  }

  function toggleKind(kindName: QuestionKind) {
    if (kinds.includes(kindName)) {
      setKinds(kinds.filter((k) => k !== kindName));
    } else {
      setKinds([...kinds, kindName]);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog frosted"
        style={{ maxWidth: "800px", width: "95%" }}
        role="dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ea-toolbar">
          <h3>Gợi ý câu hỏi từ AI (Trợ giảng LMS)</h3>
          <button className="button button--ghost" type="button" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {loadingAgents ? (
          <p className="ea-muted">Đang kiểm tra agent trợ giảng…</p>
        ) : !agents ? <div className="ea-error">{error}</div> : agents.length === 0 ? (
          <div className="ea-notice ea-notice--warn" style={{ display: "grid", gap: "var(--space-2)" }}>
            <p>
              Chưa có agent nào hỗ trợ tạo câu hỏi trong lớp học này. Cài agent Trợ giảng LMS từ Agent Hub để dùng gợi ý.
            </p>
            <button
              type="button"
              className="button button--primary"
              style={{ justifySelf: "start" }}
              onClick={() => navigate("/teacher/hub")}
            >
              Tới Agent Hub
            </button>
          </div>
        ) : (
          <div>
            {error && <div className="ea-error" style={{ marginBottom: "var(--space-3)" }}>{error}</div>}

            {!suggestion || suggestion.status === "failed" ? (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <p className="ea-muted">
                  Trợ giảng LMS sẽ đọc tài liệu của buổi học để biên soạn câu hỏi kèm lời giải và trích đoạn dẫn chứng.
                </p>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                  <label className="field">
                    <span>Số lượng câu hỏi</span>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={count}
                      onChange={(e) => setCount(parseInt(e.target.value, 10) || 1)}
                    />
                  </label>

                  <label className="field">
                    <span>Độ khó</span>
                    <select value={level} onChange={(e) => setLevel(e.target.value as QuestionLevel)}>
                      <option value="nhan_biet">Nhận biết</option>
                      <option value="thong_hieu">Thông hiểu</option>
                      <option value="van_dung">Vận dụng</option>
                      <option value="van_dung_cao">Vận dụng cao</option>
                      <option value="hon_hop">Hỗn hợp</option>
                    </select>
                  </label>
                </div>

                <div className="field">
                  <span>Loại câu hỏi</span>
                  <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginTop: "4px" }}>
                    {[
                      { id: "single", label: "Trắc nghiệm 1 đáp án" },
                      { id: "multi", label: "Nhiều đáp án" },
                      { id: "true_false", label: "Đúng / Sai" },
                      { id: "short", label: "Trả lời ngắn" },
                      { id: "essay", label: "Tự luận" },
                    ].map((k) => (
                      <label key={k.id} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <input
                          type="checkbox"
                          checked={kinds.includes(k.id as QuestionKind)}
                          onChange={() => toggleKind(k.id as QuestionKind)}
                        />
                        {k.label}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="dialog-actions" style={{ marginTop: "var(--space-3)" }}>
                  <button type="button" className="button button--secondary" onClick={onClose}>
                    Huỷ
                  </button>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={submitting}
                    onClick={handleRequestSuggestions}
                  >
                    {submitting ? "Đang gửi yêu cầu…" : "Bắt đầu tạo câu hỏi"}
                  </button>
                </div>
              </div>
            ) : suggestion.status === "pending" ? (
              <div style={{ textAlign: "center", padding: "var(--space-6)" }}>
                <p>AI đang soạn câu hỏi từ tài liệu buổi học… Vui lòng đợi trong giây lát.</p>
                <p className="ea-muted" style={{ fontSize: "0.9rem" }}>
                  Đang kiểm tra trạng thái mỗi 2 giây…
                </p>
              </div>
            ) : (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>Đã tạo {decisions.length} câu hỏi gợi ý:</span>
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={handleApproveAll}
                  >
                    Duyệt tất cả
                  </button>
                </div>

                <div style={{ maxHeight: "50vh", overflowY: "auto", display: "grid", gap: "var(--space-3)" }}>
                  {decisions.map((item, idx) => (
                    <div
                      key={idx}
                      className="ea-card"
                      style={{
                        opacity: item.action === "discard" ? 0.5 : 1,
                        borderLeft:
                          item.action === "approve"
                            ? "4px solid var(--success, #22c55e)"
                            : item.action === "discard"
                              ? "4px solid var(--danger, #ef4444)"
                              : "4px solid var(--primary)",
                      }}
                    >
                      <div className="ea-toolbar">
                        <strong>
                          Câu {idx + 1}: {item.question.prompt}
                        </strong>
                        <span className="ea-chip">
                          {item.action === "approve"
                            ? "Sẽ duyệt"
                            : item.action === "edit"
                              ? "Đã sửa"
                              : "Bỏ qua"}
                        </span>
                      </div>

                      {item.question.options && (
                        <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                          {item.question.options.map((opt) => (
                            <li
                              key={opt.id}
                              style={{
                                fontWeight:
                                  item.question.answer_key === opt.id ||
                                  (Array.isArray(item.question.answer_key) &&
                                    item.question.answer_key.includes(opt.id))
                                    ? 700
                                    : 400,
                              }}
                            >
                              {opt.text}
                            </li>
                          ))}
                        </ul>
                      )}

                      {item.question.kind !== "single" && item.question.kind !== "multi" && (
                        <p>Đáp án: {item.question.kind === "essay" ? item.question.rubric?.model_answer : typeof item.question.answer_key === "boolean" ? (item.question.answer_key ? "Đúng" : "Sai") : Array.isArray(item.question.answer_key) ? item.question.answer_key.join(" | ") : item.question.answer_key}</p>
                      )}
                      {item.question.explanation && (
                        <p className="ea-muted" style={{ margin: "4px 0", fontSize: "0.9rem" }}>
                          <em>Lời giải:</em> {item.question.explanation}
                        </p>
                      )}

                      {item.question.source && (
                        <blockquote
                          style={{
                            margin: "4px 0",
                            paddingLeft: "10px",
                            borderLeft: "2px solid var(--line)",
                            fontSize: "0.85rem",
                            color: "var(--muted)",
                          }}
                        >
                          <em>Căn cứ tài liệu:</em> &ldquo;{item.question.source}&rdquo;
                        </blockquote>
                      )}

                      <div className="ea-toolbar__actions" style={{ marginTop: "8px" }}>
                        <button
                          type="button"
                          className={`button ${item.action === "approve" ? "button--primary" : "button--secondary"}`}
                          onClick={() =>
                            setDecisions(
                              decisions.map((d, i) =>
                                i === idx ? { ...d, action: d.edited ? "edit" : "approve" } : d,
                              ),
                            )
                          }
                        >
                          Duyệt
                        </button>
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={() => setEditingIndex(idx)}
                        >
                          Sửa
                        </button>
                        <button
                          type="button"
                          className={`button ${item.action === "discard" ? "button--danger" : "button--ghost"}`}
                          onClick={() =>
                            setDecisions(
                              decisions.map((d, i) =>
                                i === idx ? { ...d, action: "discard" } : d,
                              ),
                            )
                          }
                        >
                          Bỏ
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="dialog-actions" style={{ marginTop: "var(--space-3)" }}>
                  <button type="button" className="button button--secondary" onClick={onClose}>
                    Đóng
                  </button>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={savingReview}
                    onClick={handleApplyReview}
                  >
                    {savingReview ? "Đang áp dụng…" : "Áp dụng câu hỏi đã duyệt"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {editingIndex !== null && decisions[editingIndex] && (
          <div className="dialog-backdrop" style={{ zIndex: 1100 }}>
            <div className="dialog frosted" style={{ maxWidth: "700px", width: "95%" }}>
              <QuestionEditor
                initial={decisions[editingIndex].question as QuizQuestion}
                onSave={async (updated) => {
                  setDecisions(
                    decisions.map((d, i) =>
                      i === editingIndex
                        ? {
                            ...d,
                            action: "edit",
                            edited: true,
                            question: { ...d.question, ...questionInput(updated) },
                          }
                        : d,
                    ),
                  );
                  setEditingIndex(null);
                }}
                onCancel={() => setEditingIndex(null)}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function BulkGradingSuggestions({ classId, targets, onReviewed }: {
  classId: string;
  targets: Array<{ type: "submission" | "attempt_question"; id: string; name: string }>;
  onReviewed: () => void;
}) {
  const agents = useResource(() => lmsApi.assist.agents(classId, "grading"), [classId]);
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function request() {
    setBusy(true);
    setError("");
    setSuggestions([]);
    setNames(Object.fromEntries(targets.map((target) => [target.id, target.name])));
    try {
      for (let offset = 0; offset < targets.length; offset += 100) {
        const batch = targets.slice(offset, offset + 100).map(({ type, id }) => ({ type, id }));
        const result = await lmsApi.assist.suggestGrading(classId, batch);
        setSuggestions((previous) => [...previous, ...result]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không tạo được gợi ý.");
    } finally {
      setBusy(false);
    }
  }

  if (agents.error) return <div className="ea-error">{agents.error}</div>;
  if (!agents.data) return null;
  if (agents.data.length === 0) return <p className="ea-muted">Cài agent Trợ giảng LMS từ <a href="/teacher/hub">Agent Hub</a> để dùng gợi ý.</p>;

  return <div style={{ display: "grid", gap: "8px" }}>
    <button className="button button--secondary" type="button" disabled={busy || targets.length === 0} onClick={() => void request()}>
      {busy ? "Đang yêu cầu…" : "Gợi ý chấm tất cả"}
    </button>
    {error && <div className="ea-error">{error}</div>}
    {suggestions.map((suggestion) => {
      return <div key={suggestion.id}>
        <strong>{names[suggestion.target_id] ?? suggestion.target_id}</strong>{" "}
        {suggestion.status === "skipped_consent" ? <span className="ea-chip ea-chip--warn">Bỏ qua: chưa có sự đồng ý của phụ huynh</span> :
          <GradingSuggestionButton classId={classId} targetType={suggestion.target_type as "submission" | "attempt_question"} targetId={suggestion.target_id} initialSuggestion={suggestion} onUpdated={(updated) => setSuggestions((previous) => previous.map((entry) => entry.id === updated.id ? updated : entry))} onApplyGrade={() => onReviewed()} />}
      </div>;
    })}
  </div>;
}

export interface GradingSuggestionProps {
  classId: string;
  targetType: "submission" | "attempt_question";
  targetId: string;
  onApplyGrade: (points: number, feedback: string) => void;
  initialSuggestion?: AISuggestion;
  label?: string;
  onUpdated?: (suggestion: AISuggestion) => void;
}

export function GradingSuggestionButton({
  classId,
  targetType,
  targetId,
  onApplyGrade,
  initialSuggestion,
  label,
  onUpdated,
}: GradingSuggestionProps) {
  const [agents, setAgents] = useState<AssistAgent[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(initialSuggestion ?? null);
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const [editPoints, setEditPoints] = useState<number>(0);
  const [editFeedback, setEditFeedback] = useState("");
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    let active = true;
    lmsApi.assist
      .agents(classId, "grading")
      .then((res) => {
        if (active) setAgents(res);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Không tải được danh sách agent.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [classId]);

  async function handleRequestGrading() {
    setShowModal(true);
    setIsEditing(false);
    if (initialSuggestion) return;
    setSuggestion(null);
    setRequesting(true);
    setError("");
    try {
      const list = await lmsApi.assist.suggestGrading(classId, [{ type: targetType, id: targetId }]);
      if (list.length > 0) {
        const item = list[0];
        setSuggestion(item);
        if (item.status === "ready" && item.payload) {
          const p = item.payload;
          const pts = p.points ?? 0;
          const fb = p.feedback ?? "";
          setEditPoints(pts);
          setEditFeedback(fb);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Yêu cầu gợi ý chấm thất bại.");
    } finally {
      setRequesting(false);
    }
  }

  // Poll for single suggestion readiness if needed
  useEffect(() => {
    if (!suggestion || suggestion.status !== "pending") return;

    let active = true;
    let polling = false;
    const timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const updated = await lmsApi.assist.getSuggestion(classId, suggestion.id);
        if (!active) return;
        setError("");
        if (updated.status !== "pending") {
          clearInterval(timer);
          setSuggestion(updated);
          onUpdated?.(updated);
          if (updated.status === "ready" && updated.payload) {
            const p = updated.payload;
            const pts = p.points ?? 0;
            const fb = p.feedback ?? "";
            setEditPoints(pts);
            setEditFeedback(fb);
          }
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Không tải được gợi ý. Đang thử lại…");
      } finally {
        polling = false;
      }
    }, 2000);

    return () => { active = false; clearInterval(timer); };
  }, [classId, suggestion]);

  useEffect(() => {
    if (suggestion?.status === "ready") {
      setEditPoints(suggestion.payload?.points ?? 0);
      setEditFeedback(suggestion.payload?.feedback ?? "");
    }
  }, [suggestion]);

  async function handleDecision(action: "approve" | "edit" | "discard") {
    if (!suggestion || suggestion.status !== "ready" || reviewing) return;
    setReviewing(true);
    setError("");
    try {
      const reviewed = await lmsApi.assist.reviewSuggestion(classId, suggestion.id, {
        action,
        ...(action === "edit" ? { points: editPoints, feedback: editFeedback } : {}),
      });
      setSuggestion(reviewed);
      onUpdated?.(reviewed);
      if (action !== "discard") {
        onApplyGrade(
          typeof reviewed.final?.points === "number" ? reviewed.final.points : editPoints,
          typeof reviewed.final?.feedback === "string" ? reviewed.final.feedback : editFeedback,
        );
      }
      setShowModal(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không lưu được quyết định duyệt.");
    } finally {
      setReviewing(false);
    }
  }

  if (loading) return null;
  if (!agents) return <div className="ea-error">{error}</div>;

  if (agents && agents.length === 0) {
    return (
      <div className="ea-muted" style={{ fontSize: "0.85rem" }}>
        Cài agent Trợ giảng LMS từ <a href="/teacher/hub">Agent Hub</a> để dùng gợi ý chấm.
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="button button--secondary"
        onClick={handleRequestGrading}
        disabled={requesting}
        title="Gợi ý chấm từ AI"
      >
        <Icon name="sparkles" /> {label ?? (initialSuggestion ? "Xem gợi ý" : "Gợi ý chấm")}
      </button>

      {showModal && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setShowModal(false)}>
          <div
            className="dialog frosted"
            style={{ maxWidth: "600px", width: "95%" }}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="ea-toolbar">
              <h3>Gợi ý chấm của AI</h3>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => setShowModal(false)}
              >
                <Icon name="x" />
              </button>
            </div>

            {error && <div className="ea-error">{error}</div>}

            {requesting || suggestion?.status === "pending" ? (
              <div style={{ textAlign: "center", padding: "var(--space-6)" }}>
                <p>Trợ giảng LMS đang đọc bài làm và đối chiếu thang chấm…</p>
              </div>
            ) : suggestion?.status === "skipped_consent" ? (
              <div className="ea-notice ea-notice--warn">
                Học sinh này chưa có sự đồng ý của phụ huynh để xử lý bài làm qua agent.
              </div>
            ) : suggestion?.status === "failed" ? (
              <div className="ea-error">
                {suggestion.error || "Không thể tạo gợi ý chấm cho bài này."}
              </div>
            ) : suggestion?.status === "ready" ? (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <div className="ea-chip ea-chip--info" style={{ justifySelf: "start" }}>
                  Gợi ý của AI
                </div>

                {/* Show criteria breakdown if available */}
                {suggestion.payload?.criteria && (
                  <div style={{ display: "grid", gap: "6px" }}>
                    <span style={{ fontWeight: 600 }}>Chi tiết tiêu chí:</span>
                    {suggestion.payload.criteria.map((c, i) => (
                      <div
                        key={i}
                        style={{
                          padding: "6px 10px",
                          background: "var(--surface-subtle, rgba(0,0,0,0.03))",
                          borderRadius: "4px",
                          fontSize: "0.9rem",
                        }}
                      >
                        <strong>{c.name}:</strong> {c.points} điểm — <em>{c.reason}</em>
                      </div>
                    ))}
                  </div>
                )}

                {!isEditing ? (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                      <span>Điểm đề xuất:</span>
                      <strong style={{ fontSize: "1.2rem", color: "var(--primary)" }}>{editPoints}</strong>
                    </div>
                    {editFeedback && (
                      <div>
                        <span>Nhận xét đề xuất:</span>
                        <p style={{ margin: "4px 0", fontStyle: "italic" }}>&ldquo;{editFeedback}&rdquo;</p>
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ display: "grid", gap: "var(--space-2)" }}>
                    <label className="field">
                      <span>Điểm</span>
                      <input
                        type="number"
                        step="0.25"
                        value={editPoints}
                        onChange={(e) => setEditPoints(parseFloat(e.target.value) || 0)}
                      />
                    </label>
                    <label className="field">
                      <span>Nhận xét</span>
                      <textarea
                        rows={3}
                        value={editFeedback}
                        onChange={(e) => setEditFeedback(e.target.value)}
                      />
                    </label>
                  </div>
                )}

                <div className="dialog-actions" style={{ marginTop: "var(--space-3)" }}>
                  <button
                    type="button"
                    className="button button--secondary"
                    disabled={reviewing}
                    onClick={() => handleDecision("discard")}
                  >
                    Bỏ
                  </button>
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => setIsEditing(!isEditing)}
                  >
                    {isEditing ? "Xem gợi ý gốc" : "Sửa"}
                  </button>
                  <button
                    type="button"
                    className="button button--primary"
                    disabled={reviewing}
                    onClick={() => handleDecision(isEditing ? "edit" : "approve")}
                  >
                    Duyệt điểm này
                  </button>
                </div>
              </div>
            ) : <p className="ea-muted">{suggestion ? "Gợi ý đã được xử lý." : "Chưa có gợi ý."}</p>}
          </div>
        </div>
      )}
    </>
  );
}
