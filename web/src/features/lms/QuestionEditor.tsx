import { useState } from "react";
import type { AnswerValue, QuestionInput, QuestionKind, QuestionOption, QuizQuestion, Rubric } from "../../api-client/lms";
import { Icon } from "../../components/Icon";

export interface RubricCriterion {
  name: string;
  max_points: number;
  description: string;
}

export interface QuestionEditorProps {
  initial?: Partial<QuizQuestion>;
  onSave: (question: QuestionInput) => Promise<void>;
  onCancel: () => void;
  busy?: boolean;
}

const KIND_LABELS: Record<QuestionKind, string> = {
  single: "Trắc nghiệm 1 đáp án",
  multi: "Trắc nghiệm nhiều đáp án",
  true_false: "Đúng / Sai",
  short: "Trả lời ngắn",
  essay: "Tự luận",
};

export function QuestionEditor({ initial, onSave, onCancel, busy: externalBusy = false }: QuestionEditorProps) {
  const [saving, setSaving] = useState(false);
  const busy = externalBusy || saving;
  const [kind, setKind] = useState<QuestionKind>(initial?.kind ?? "single");
  const [prompt, setPrompt] = useState(initial?.prompt ?? "");
  const [points, setPoints] = useState<number>(initial?.points ?? 1);
  const [explanation, setExplanation] = useState(initial?.explanation ?? "");
  const [multiScoring, setMultiScoring] = useState<"all_or_nothing" | "partial">(
    initial?.multi_scoring ?? "all_or_nothing",
  );

  // Options for single / multi
  const [options, setOptions] = useState<QuestionOption[]>(() => {
    if (initial?.options && initial.options.length > 0) {
      return initial.options;
    }
    return [
      { id: "opt_1", text: "" },
      { id: "opt_2", text: "" },
      { id: "opt_3", text: "" },
      { id: "opt_4", text: "" },
    ];
  });

  // Answer key
  const [singleKey, setSingleKey] = useState<string>(() => {
    if (initial?.kind === "single" && typeof initial.answer_key === "string") {
      return initial.answer_key;
    }
    return options[0]?.id ?? "";
  });

  const [multiKeys, setMultiKeys] = useState<string[]>(() => {
    if (initial?.kind === "multi" && Array.isArray(initial.answer_key)) {
      return initial.answer_key.map(String);
    }
    return [];
  });

  const [tfKey, setTfKey] = useState<boolean>(() => {
    if (initial?.kind === "true_false" && typeof initial.answer_key === "boolean") {
      return initial.answer_key;
    }
    return true;
  });

  const [shortKeys, setShortKeys] = useState<string[]>(() => {
    if (initial?.kind === "short" && Array.isArray(initial.answer_key)) {
      return initial.answer_key.map(String);
    }
    return [""];
  });

  // Essay rubric & model answer
  const initialRubric = initial?.rubric as { criteria?: RubricCriterion[]; model_answer?: string } | undefined;
  const [rubricCriteria, setRubricCriteria] = useState<RubricCriterion[]>(
    initialRubric?.criteria ?? [{ name: "Nội dung & ý chính", max_points: points, description: "" }],
  );
  const [modelAnswer, setModelAnswer] = useState(initialRubric?.model_answer ?? "");

  const [error, setError] = useState("");

  function addOption() {
    const nextId = `opt_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    setOptions([...options, { id: nextId, text: "" }]);
  }

  function removeOption(id: string) {
    if (options.length <= 2) {
      setError("Cần ít nhất 2 lựa chọn.");
      return;
    }
    setOptions(options.filter((o) => o.id !== id));
    if (singleKey === id) {
      const remaining = options.filter((o) => o.id !== id);
      setSingleKey(remaining[0]?.id ?? "");
    }
    setMultiKeys(multiKeys.filter((k) => k !== id));
  }

  function updateOptionText(id: string, text: string) {
    setOptions(options.map((o) => (o.id === id ? { ...o, text } : o)));
  }

  function addCriterion() {
    setRubricCriteria([...rubricCriteria, { name: "", max_points: 1, description: "" }]);
  }

  function removeCriterion(idx: number) {
    setRubricCriteria(rubricCriteria.filter((_, i) => i !== idx));
  }

  function updateCriterion(idx: number, patch: Partial<RubricCriterion>) {
    setRubricCriteria(rubricCriteria.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  }

  async function handleSave() {
    if (busy) return;
    setError("");

    if (!prompt.trim()) {
      setError("Vui lòng nhập nội dung câu hỏi.");
      return;
    }

    if (points <= 0) {
      setError("Điểm câu hỏi phải lớn hơn 0.");
      return;
    }

    let answerKey: AnswerValue = null;
    let rubricPayload: Rubric | null = null;

    if (kind === "single") {
      if (options.length < 2) {
        setError("Cần ít nhất 2 lựa chọn.");
        return;
      }
      if (options.some((o) => !o.text.trim())) {
        setError("Nội dung các lựa chọn không được để trống.");
        return;
      }
      if (!singleKey || !options.some((o) => o.id === singleKey)) {
        setError("Vui lòng chọn một đáp án đúng.");
        return;
      }
      answerKey = singleKey;
    } else if (kind === "multi") {
      if (options.length < 2) {
        setError("Cần ít nhất 2 lựa chọn.");
        return;
      }
      if (options.some((o) => !o.text.trim())) {
        setError("Nội dung các lựa chọn không được để trống.");
        return;
      }
      if (multiKeys.length === 0) {
        setError("Vui lòng chọn ít nhất một đáp án đúng.");
        return;
      }
      answerKey = multiKeys;
    } else if (kind === "true_false") {
      answerKey = tfKey;
    } else if (kind === "short") {
      const validAnswers = shortKeys.map((s) => s.trim()).filter(Boolean);
      if (validAnswers.length === 0) {
        setError("Cần ít nhất một đáp án ngắn được chấp nhận.");
        return;
      }
      answerKey = validAnswers;
    } else if (kind === "essay") {
      answerKey = null;
      rubricPayload = {
        criteria: rubricCriteria.map((c) => ({
          name: c.name.trim() || "Tiêu chí",
          max_points: Number(c.max_points) || 1,
          description: c.description.trim(),
        })),
        model_answer: modelAnswer.trim(),
      };
    }

    const payload: QuestionInput = {
      kind,
      prompt: prompt.trim(),
      options: kind === "single" || kind === "multi" ? options : [],
      answer_key: answerKey,
      multi_scoring: kind === "multi" ? multiScoring : undefined,
      points: Number(points),
      explanation: explanation.trim(),
      rubric: rubricPayload,
    };

    setSaving(true);
    try {
      await onSave(payload);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Lưu câu hỏi thất bại.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ea-card lms-question-editor">
      <div className="ea-toolbar">
        <h3>{initial?.prompt ? "Sửa câu hỏi" : "Thêm câu hỏi mới"}</h3>
        <button className="button button--ghost" type="button" onClick={onCancel}>
          <Icon name="x" /> Đóng
        </button>
      </div>

      {error && <div className="ea-error">{error}</div>}

      <div className="ea-form-grid" style={{ display: "grid", gap: "var(--space-3)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: "var(--space-3)" }}>
          <label className="field">
            <span>Loại câu hỏi</span>
            <select
              value={kind}
              onChange={(e) => {
                const newKind = e.target.value as QuestionKind;
                setKind(newKind);
                setError("");
              }}
              disabled={busy}
            >
              {(Object.keys(KIND_LABELS) as QuestionKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Điểm số</span>
            <input
              type="number"
              min="0.25"
              step="0.25"
              value={points}
              onChange={(e) => setPoints(Math.max(0.25, parseFloat(e.target.value) || 0))}
              disabled={busy}
            />
          </label>
        </div>

        <label className="field">
          <span>Nội dung câu hỏi *</span>
          <textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Nhập nội dung đề bài câu hỏi…"
            disabled={busy}
          />
        </label>

        {/* Single Choice Options */}
        {kind === "single" && (
          <div className="lms-options-editor" style={{ display: "grid", gap: "var(--space-2)" }}>
            <span style={{ fontWeight: 600 }}>Lựa chọn (chọn nút tròn để đánh dấu đáp án đúng)</span>
            {options.map((opt, idx) => (
              <div key={opt.id} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input
                  type="radio"
                  name="single_correct"
                  checked={singleKey === opt.id}
                  onChange={() => setSingleKey(opt.id)}
                  aria-label={`Đáp án đúng lựa chọn ${idx + 1}`}
                  disabled={busy}
                />
                <input
                  type="text"
                  value={opt.text}
                  onChange={(e) => updateOptionText(opt.id, e.target.value)}
                  placeholder={`Lựa chọn ${idx + 1}`}
                  style={{ flex: 1 }}
                  disabled={busy}
                />
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => removeOption(opt.id)}
                  disabled={options.length <= 2 || busy}
                  title="Xoá lựa chọn"
                >
                  <Icon name="trash" />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="button button--secondary"
              style={{ justifySelf: "start" }}
              onClick={addOption}
              disabled={busy}
            >
              <Icon name="plus" /> Thêm lựa chọn
            </button>
          </div>
        )}

        {/* Multi Choice Options */}
        {kind === "multi" && (
          <div className="lms-options-editor" style={{ display: "grid", gap: "var(--space-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600 }}>Lựa chọn (tích chọn các đáp án đúng)</span>
              <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
                <span>Cách tính điểm:</span>
                <select
                  value={multiScoring}
                  onChange={(e) => setMultiScoring(e.target.value as "all_or_nothing" | "partial")}
                  disabled={busy}
                >
                  <option value="all_or_nothing">Đúng toàn bộ mới có điểm</option>
                  <option value="partial">Tính điểm từng phần</option>
                </select>
              </label>
            </div>
            {options.map((opt, idx) => {
              const isChecked = multiKeys.includes(opt.id);
              return (
                <div key={opt.id} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setMultiKeys([...multiKeys, opt.id]);
                      } else {
                        setMultiKeys(multiKeys.filter((k) => k !== opt.id));
                      }
                    }}
                    aria-label={`Đáp án đúng lựa chọn ${idx + 1}`}
                    disabled={busy}
                  />
                  <input
                    type="text"
                    value={opt.text}
                    onChange={(e) => updateOptionText(opt.id, e.target.value)}
                    placeholder={`Lựa chọn ${idx + 1}`}
                    style={{ flex: 1 }}
                    disabled={busy}
                  />
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => removeOption(opt.id)}
                    disabled={options.length <= 2 || busy}
                    title="Xoá lựa chọn"
                  >
                    <Icon name="trash" />
                  </button>
                </div>
              );
            })}
            <button
              type="button"
              className="button button--secondary"
              style={{ justifySelf: "start" }}
              onClick={addOption}
              disabled={busy}
            >
              <Icon name="plus" /> Thêm lựa chọn
            </button>
          </div>
        )}

        {/* True / False */}
        {kind === "true_false" && (
          <div className="field">
            <span>Đáp án đúng</span>
            <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "4px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="tf_answer"
                  checked={tfKey === true}
                  onChange={() => setTfKey(true)}
                  disabled={busy}
                />
                Đúng
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input
                  type="radio"
                  name="tf_answer"
                  checked={tfKey === false}
                  onChange={() => setTfKey(false)}
                  disabled={busy}
                />
                Sai
              </label>
            </div>
          </div>
        )}

        {/* Short Answer */}
        {kind === "short" && (
          <div className="lms-options-editor" style={{ display: "grid", gap: "var(--space-2)" }}>
            <span style={{ fontWeight: 600 }}>Các đáp án được chấp nhận (không phân biệt hoa thường)</span>
            {shortKeys.map((ans, idx) => (
              <div key={idx} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input
                  type="text"
                  value={ans}
                  onChange={(e) => {
                    const next = [...shortKeys];
                    next[idx] = e.target.value;
                    setShortKeys(next);
                  }}
                  placeholder={`Đáp án hợp lệ ${idx + 1}`}
                  style={{ flex: 1 }}
                  disabled={busy}
                />
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setShortKeys(shortKeys.filter((_, i) => i !== idx))}
                  disabled={shortKeys.length <= 1 || busy}
                  title="Xoá đáp án"
                >
                  <Icon name="trash" />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="button button--secondary"
              style={{ justifySelf: "start" }}
              onClick={() => setShortKeys([...shortKeys, ""])}
              disabled={busy}
            >
              <Icon name="plus" /> Thêm đáp án chấp nhận
            </button>
          </div>
        )}

        {/* Essay with rubric */}
        {kind === "essay" && (
          <div style={{ display: "grid", gap: "var(--space-3)" }}>
            <label className="field">
              <span>Đáp án mẫu (gợi ý cho giáo viên hoặc AI chấm)</span>
              <textarea
                rows={3}
                value={modelAnswer}
                onChange={(e) => setModelAnswer(e.target.value)}
                placeholder="Nhập dàn ý hoặc câu trả lời mẫu…"
                disabled={busy}
              />
            </label>

            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <span style={{ fontWeight: 600 }}>Thang chấm (Rubric tiêu chí)</span>
              {rubricCriteria.map((crit, idx) => (
                <div
                  key={idx}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 100px auto",
                    gap: "var(--space-2)",
                    alignItems: "center",
                    border: "1px solid var(--line)",
                    padding: "8px",
                    borderRadius: "var(--radius-sm)",
                  }}
                >
                  <div style={{ display: "grid", gap: "4px" }}>
                    <input
                      type="text"
                      placeholder="Tên tiêu chí (vd: Lập luận chặt chẽ)"
                      value={crit.name}
                      onChange={(e) => updateCriterion(idx, { name: e.target.value })}
                      disabled={busy}
                    />
                    <input
                      type="text"
                      placeholder="Mô tả tiêu chí…"
                      value={crit.description}
                      onChange={(e) => updateCriterion(idx, { description: e.target.value })}
                      disabled={busy}
                    />
                  </div>
                  <div>
                    <input
                      type="number"
                      min="0.25"
                      step="0.25"
                      placeholder="Điểm tối đa"
                      value={crit.max_points}
                      onChange={(e) =>
                        updateCriterion(idx, { max_points: parseFloat(e.target.value) || 0 })
                      }
                      disabled={busy}
                    />
                  </div>
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => removeCriterion(idx)}
                    disabled={rubricCriteria.length <= 1 || busy}
                  >
                    <Icon name="trash" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="button button--secondary"
                style={{ justifySelf: "start" }}
                onClick={addCriterion}
                disabled={busy}
              >
                <Icon name="plus" /> Thêm tiêu chí chấm
              </button>
            </div>
          </div>
        )}

        <label className="field">
          <span>Giải thích đáp án (hiện sau khi nộp hoặc chốt bài)</span>
          <textarea
            rows={2}
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            placeholder="Giải thích vì sao đáp án đúng, phương pháp giải…"
            disabled={busy}
          />
        </label>
      </div>

      <div className="ea-toolbar__actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="button button--secondary" type="button" onClick={onCancel} disabled={busy}>
          Huỷ
        </button>
        <button className="button button--primary" type="button" onClick={handleSave} disabled={busy}>
          {busy ? "Đang lưu…" : "Lưu câu hỏi"}
        </button>
      </div>
    </div>
  );
}
