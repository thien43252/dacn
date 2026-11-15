import { useState } from "react";
import { type Assignment, type AssignmentTeacherView, type RubricCriterion, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { FileUpload } from "./FileUpload";
import { GradingPanel } from "./GradingPanel";
import { SubmissionsTable } from "./SubmissionsTable";
import { localDateTime } from "./formValues";
import "./lms.css";

export function AssignmentEditor({
  classId,
  assignmentId,
}: {
  classId: string;
  assignmentId: string;
}) {
  const assignmentResource = useResource(
    () => lmsApi.assignments.get(classId, assignmentId) as Promise<AssignmentTeacherView>,
    [classId, assignmentId],
  );

  const asg = assignmentResource.data;

  // Selected submission to grade
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<string | null>(null);

  // Form edit states
  const [prompt, setPrompt] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [maxPoints, setMaxPoints] = useState(10);
  const [allowLate, setAllowLate] = useState(true);
  const [latePenaltyPerDay, setLatePenaltyPerDay] = useState(0);
  const [latePenaltyMax, setLatePenaltyMax] = useState(0);
  const [aiGrading, setAiGrading] = useState(true);
  const [weight, setWeight] = useState(1);
  const [countsInGrade, setCountsInGrade] = useState(true);
  const [promptFileIds, setPromptFileIds] = useState<string[]>([]);
  const [modelAnswer, setModelAnswer] = useState("");
  const [criteria, setCriteria] = useState<RubricCriterion[]>([]);
  const [rosterVersion, setRosterVersion] = useState(0);

  const [initialized, setInitialized] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");

  // Initialize fields once loaded
  if (asg && !initialized) {
    setPrompt(asg.prompt || "");
    setDueAt(localDateTime(asg.due_at));
    setMaxPoints(asg.max_points ?? 10);
    setAllowLate(asg.allow_late ?? true);
    setLatePenaltyPerDay(asg.late_penalty_per_day_pct ?? 0);
    setLatePenaltyMax(asg.late_penalty_max_pct ?? 0);
    setAiGrading(asg.ai_grading ?? true);
    setWeight(asg.weight ?? 1);
    setCountsInGrade(asg.counts_in_grade ?? true);
    setPromptFileIds(asg.prompt_file_ids ?? []);
    setModelAnswer(asg.rubric?.model_answer ?? "");
    setCriteria(asg.rubric?.criteria ?? []);
    setInitialized(true);
  }

  if (assignmentResource.loading && !asg) {
    return (
      <div className="ea-page">
        <p className="ea-muted">Đang tải bài tập…</p>
      </div>
    );
  }

  if (assignmentResource.error || !asg) {
    return (
      <div className="ea-page">
        <div className="ea-error">{assignmentResource.error || "Không tìm thấy bài tập."}</div>
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

  async function handleSaveConfig() {
    if (saving || uploading) return;
    if (maxPoints <= 0 || weight < 0 || latePenaltyPerDay < 0 || latePenaltyPerDay > 100 || latePenaltyMax < 0 || latePenaltyMax > 100 || criteria.some((criterion) => !criterion.name.trim() || criterion.max_points <= 0)) {
      setErrorNotice("Kiểm tra điểm tối đa, trọng số, mức trừ và các tiêu chí chấm.");
      return;
    }
    setSaving(true);
    setErrorNotice("");
    setNotice("");
    try {
      const patch: Partial<Assignment> = {
        prompt: prompt.trim(),
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        max_points: Number(maxPoints),
        allow_late: allowLate,
        late_penalty_per_day_pct: Number(latePenaltyPerDay),
        late_penalty_max_pct: Number(latePenaltyMax),
        ai_grading: aiGrading,
        weight: Number(weight),
        counts_in_grade: countsInGrade,
        prompt_file_ids: promptFileIds,
        rubric: {
          criteria,
          model_answer: modelAnswer.trim(),
        },
      };

      const updated = await lmsApi.assignments.update(classId, assignmentId, patch);
      assignmentResource.setData({ ...asg!, ...updated });
      setRosterVersion((version) => version + 1);
      setNotice("Đã lưu cấu hình bài tập.");
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ea-page lms-assignment-editor">
      <button
        className="ea-back"
        type="button"
        onClick={() => navigate(`/teacher/classes/${classId}`)}
      >
        <Icon name="chevron-left" /> Về lớp học
      </button>

      <div className="ea-toolbar">
        <div>
          <h2>Quản lý & Chấm bài tập</h2>
          <span className="ea-muted">
            Tối đa {maxPoints} điểm · Hạn nộp: {dueAt ? new Date(dueAt).toLocaleString("vi-VN") : "Không có hạn"}
          </span>
        </div>
      </div>

      {notice && <div className="ea-notice ea-notice--ok">{notice}</div>}
      {errorNotice && <div className="ea-error">{errorNotice}</div>}

      {/* Assignment Configuration Form */}
      <div className="ea-card">
        <h3>Nội dung & Cấu hình bài tập</h3>

        <div className="ea-form-grid" style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
          <label className="field">
            <span>Yêu cầu / Đề bài *</span>
            <textarea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Nhập yêu cầu chi tiết của bài tập…"
              disabled={saving}
            />
          </label>

          {/* Prompt files */}
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Tệp đính kèm của đề bài</span>
            {promptFileIds.length > 0 && (
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                {promptFileIds.map((fid) => (
                  <div
                    key={fid}
                    className="ea-chip"
                    style={{ display: "flex", alignItems: "center", gap: "6px" }}
                  >
                    <Icon name="file" /> #{fid.slice(0, 8)}
                    <button
                      type="button"
                      className="button button--ghost"
                      style={{ padding: 0 }}
                      onClick={() => setPromptFileIds(promptFileIds.filter((id) => id !== fid))}
                      title="Gỡ tệp này"
                    >
                      <Icon name="x" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <FileUpload
              classId={classId}
              purpose="prompt"
              onUploadingChange={setUploading}
              label="Tải thêm tệp đề bài"
              onUploaded={(f) => setPromptFileIds((ids) => [...ids, f.id])}
              disabled={saving}
            />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "var(--space-3)",
            }}
          >
            <label className="field">
              <span>Hạn nộp bài</span>
              <input
                type="datetime-local"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                disabled={saving}
              />
            </label>

            <label className="field">
              <span>Điểm tối đa</span>
              <input
                type="number"
                min="1"
                step="0.5"
                value={maxPoints}
                onChange={(e) => setMaxPoints(parseFloat(e.target.value) || 10)}
                disabled={saving}
              />
            </label>

            <label className="field">
              <span>Trừ % mỗi ngày muộn</span>
              <input
                type="number"
                min="0"
                max="100"
                value={latePenaltyPerDay}
                onChange={(e) => setLatePenaltyPerDay(parseFloat(e.target.value) || 0)}
                disabled={saving || !allowLate}
              />
            </label>

            <label className="field">
              <span>Mức trừ tối đa (%)</span>
              <input
                type="number"
                min="0"
                max="100"
                value={latePenaltyMax}
                onChange={(e) => setLatePenaltyMax(parseFloat(e.target.value) || 0)}
                disabled={saving || !allowLate}
              />
            </label>

            <label className="field">
              <span>Trọng số điểm</span>
              <input
                type="number"
                min="0"
                step="0.5"
                value={weight}
                onChange={(e) => setWeight(Number(e.target.value))}
                disabled={saving}
              />
            </label>
          </div>

          <label className="field">
            <span>Dàn ý / Đáp án mẫu (dùng cho giáo viên và gợi ý chấm AI)</span>
            <textarea
              rows={3}
              value={modelAnswer}
              onChange={(e) => setModelAnswer(e.target.value)}
              placeholder="Nhập gợi ý giải hoặc dàn ý chuẩn…"
              disabled={saving}
            />
          </label>

          <div className="field">
            <span>Tiêu chí chấm</span>
            {criteria.map((criterion, index) => (
              <div key={index} className="ea-inline-form">
                <input aria-label="Tên tiêu chí" value={criterion.name} disabled={saving} onChange={(event) => setCriteria(criteria.map((value, i) => i === index ? { ...value, name: event.target.value } : value))} />
                <input aria-label="Điểm tối đa tiêu chí" type="number" min="0.01" step="0.25" value={criterion.max_points} disabled={saving} onChange={(event) => setCriteria(criteria.map((value, i) => i === index ? { ...value, max_points: Number(event.target.value) } : value))} />
                <input aria-label="Mô tả tiêu chí" value={criterion.description} disabled={saving} onChange={(event) => setCriteria(criteria.map((value, i) => i === index ? { ...value, description: event.target.value } : value))} />
                <button className="button button--ghost" type="button" disabled={saving} onClick={() => setCriteria(criteria.filter((_, i) => i !== index))}>Xóa</button>
              </div>
            ))}
            <button className="button button--secondary" type="button" disabled={saving} onClick={() => setCriteria([...criteria, { name: "", max_points: 1, description: "" }])}>Thêm tiêu chí</button>
          </div>

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--space-4)",
              paddingTop: "var(--space-2)",
              borderTop: "1px solid var(--line)",
            }}
          >
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={allowLate}
                onChange={(e) => setAllowLate(e.target.checked)}
                disabled={saving}
              />
              Cho phép nộp muộn
            </label>

            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={aiGrading}
                onChange={(e) => setAiGrading(e.target.checked)}
                disabled={saving}
              />
              Trợ lý chấm AI
            </label>

            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={countsInGrade}
                onChange={(e) => setCountsInGrade(e.target.checked)}
                disabled={saving}
              />
              Tính vào điểm tổng kết
            </label>
          </div>

          <div className="ea-toolbar__actions" style={{ marginTop: "var(--space-2)" }}>
            <button
              type="button"
              className="button button--primary"
              disabled={saving || uploading}
              onClick={handleSaveConfig}
            >
              {saving ? "Đang lưu cấu hình…" : "Lưu cấu hình bài tập"}
            </button>
          </div>
        </div>
      </div>

      {/* Selected Submission Grading Panel */}
      {selectedSubmissionId && (
        <GradingPanel
          key={selectedSubmissionId}
          classId={classId}
          assignmentId={assignmentId}
          submissionId={selectedSubmissionId}
          maxPoints={asg.max_points}
          aiGrading={asg.ai_grading}
          onClose={() => setSelectedSubmissionId(null)}
          onGraded={() => {
            assignmentResource.reload();
            setRosterVersion((version) => version + 1);
          }}
        />
      )}

      {/* Submissions Roster Table */}
      <SubmissionsTable
        reloadKey={rosterVersion}
        classId={classId}
        assignmentId={assignmentId}
        aiGrading={asg.ai_grading}
        onSelectSubmission={(sid) => setSelectedSubmissionId(sid)}
        onReload={() => assignmentResource.reload()}
      />
    </div>
  );
}
