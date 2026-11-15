import { useEffect, useState } from "react";
import { type SubmissionTeacherView, lmsApi } from "../../api-client/lms";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { GradingSuggestionButton } from "./SuggestionReview";

export interface GradingPanelProps {
  classId: string;
  assignmentId: string;
  submissionId: string;
  maxPoints: number;
  aiGrading: boolean;
  onClose: () => void;
  onGraded: () => void;
}

export function GradingPanel({
  classId,
  assignmentId,
  submissionId,
  maxPoints,
  aiGrading,
  onClose,
  onGraded,
}: GradingPanelProps) {
  const submissionResource = useResource(
    () => lmsApi.submissions.get(classId, submissionId),
    [classId, submissionId],
  );

  const sub = submissionResource.data as SubmissionTeacherView | null;

  const [rawScore, setRawScore] = useState<number>(0);
  const [feedback, setFeedback] = useState("");
  const [penaltyWaived, setPenaltyWaived] = useState(false);
  const [selectedVersionNo, setSelectedVersionNo] = useState<number>(1);

  const [saving, setSaving] = useState(false);
  const [returning, setReturning] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");

  // Sync initial values when submission loads
  useEffect(() => {
    if (sub) {
      setRawScore(sub.raw_score ?? 0);
      setFeedback(sub.feedback ?? "");
      setPenaltyWaived(Boolean(sub.penalty_waived));
      setSelectedVersionNo(sub.latest_version || 1);
    }
  }, [sub]);

  if (submissionResource.loading && !sub) {
    return <p className="ea-muted">Đang tải bài nộp…</p>;
  }

  if (submissionResource.error || !sub) {
    return (
      <div className="ea-card">
        <div className="ea-error">{submissionResource.error || "Không tìm thấy bài nộp."}</div>
        <button type="button" className="button button--secondary" onClick={onClose}>
          Đóng
        </button>
      </div>
    );
  }

  const versions = sub.versions ?? [];
  const currentVersion = versions.find((v) => v.version_no === selectedVersionNo) || versions[versions.length - 1];

  async function handleSaveGrade() {
    setSaving(true);
    setErrorNotice("");
    setNotice("");
    try {
      const res = await lmsApi.submissions.grade(classId, submissionId, {
        raw_score: Number(rawScore),
        feedback,
        penalty_waived: penaltyWaived,
      });
      submissionResource.setData(res);
      setNotice("Đã lưu điểm bài nộp.");
      onGraded();
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleReturn() {
    setReturning(true);
    setErrorNotice("");
    try {
      await lmsApi.assignments.returnSubmissions(classId, assignmentId, [submissionId]);
      submissionResource.setData({
        ...sub!,
        status: "returned",
      });
      setNotice("Đã trả bài cho học sinh.");
      onGraded();
    } catch (err: unknown) {
      setErrorNotice(errorMessage(err));
    } finally {
      setReturning(false);
    }
  }

  return (
    <div className="ea-card lms-grading-panel" style={{ border: "2px solid var(--primary-subtle, #3b82f6)" }}>
      <div className="ea-toolbar">
        <div>
          <h3>Chấm bài: {sub.student_id}</h3>
          <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
            Trạng thái:{" "}
            <strong>
              {sub.status === "returned"
                ? "Đã trả bài"
                : sub.status === "graded"
                  ? "Đã chấm (chưa trả)"
                  : "Chờ chấm"}
            </strong>
            {sub.is_late && <span className="ea-chip ea-chip--warn" style={{ marginLeft: "8px" }}>Nộp muộn ({sub.days_late} ngày)</span>}
          </span>
        </div>

        <button type="button" className="button button--ghost" onClick={onClose}>
          <Icon name="x" />
        </button>
      </div>

      {notice && <div className="ea-notice ea-notice--ok">{notice}</div>}
      {errorNotice && <div className="ea-error">{errorNotice}</div>}

      {/* Version Selector */}
      {versions.length > 1 && (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "var(--space-2) 0" }}>
          <span style={{ fontSize: "0.9rem", fontWeight: 600 }}>Phiên bản nộp:</span>
          {versions.map((v) => (
            <button
              key={v.version_no}
              type="button"
              className={`button ${selectedVersionNo === v.version_no ? "button--primary" : "button--secondary"}`}
              style={{ fontSize: "0.8rem", padding: "2px 8px" }}
              onClick={() => setSelectedVersionNo(v.version_no)}
            >
              v{v.version_no} {v.is_late ? "(muộn)" : ""}
            </button>
          ))}
        </div>
      )}

      {/* Current Version Content */}
      <div
        style={{
          background: "var(--surface-subtle, #f9f9f9)",
          padding: "var(--space-3)",
          borderRadius: "var(--radius-sm)",
          margin: "var(--space-3) 0",
        }}
      >
        <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
          Nộp lúc: {currentVersion?.submitted_at ? new Date(currentVersion.submitted_at).toLocaleString("vi-VN") : "—"}
        </span>

        {currentVersion?.text ? (
          <div style={{ whiteSpace: "pre-wrap", margin: "8px 0" }}>{currentVersion.text}</div>
        ) : (
          <p className="ea-muted" style={{ margin: "8px 0" }}>Không có văn bản nộp kèm.</p>
        )}

        {/* Submission files */}
        {currentVersion?.file_ids && currentVersion.file_ids.length > 0 && (
          <div style={{ marginTop: "var(--space-2)" }}>
            <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Tệp đính kèm:</span>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "4px" }}>
              {currentVersion.file_ids.map((fid) => (
                <a
                  key={fid}
                  href={lmsApi.files.url(classId, fid, true)}
                  target="_blank"
                  rel="noreferrer"
                  className="ea-chip"
                  style={{ textDecoration: "none", color: "var(--primary)" }}
                >
                  <Icon name="file" /> Tải tệp #{fid.slice(0, 8)}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Grading Form */}
      <div style={{ display: "grid", gap: "var(--space-3)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "var(--space-3)", alignItems: "center" }}>
          <label className="field">
            <span>Điểm chấm (tối đa {maxPoints})</span>
            <input
              type="number"
              min="0"
              max={maxPoints}
              step="0.25"
              value={rawScore}
              onChange={(e) => setRawScore(parseFloat(e.target.value) || 0)}
              disabled={saving}
            />
          </label>

          {/* Computed Penalty & Final Score Display */}
          <div style={{ fontSize: "0.9rem", display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
            <div>
              <span className="ea-muted">Trừ điểm muộn:</span>{" "}
              <strong style={{ color: (sub.penalty ?? 0) > 0 ? "var(--danger)" : "inherit" }}>
                -{sub.penalty ?? 0}
              </strong>
            </div>
            <div>
              <span className="ea-muted">Điểm cuối cùng:</span>{" "}
              <strong style={{ fontSize: "1.2rem", color: "var(--primary)" }}>
                {sub.final_score ?? rawScore} / {maxPoints}
              </strong>
            </div>
          </div>
        </div>

        {sub.is_late && (
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={penaltyWaived}
              onChange={(e) => setPenaltyWaived(e.target.checked)}
              disabled={saving}
            />
            <span>Miễn trừ điểm nộp muộn cho học sinh này</span>
          </label>
        )}

        <label className="field">
          <span>Nhận xét và phản hồi</span>
          <textarea
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Nhận xét ưu điểm, điểm cần cải thiện…"
            disabled={saving}
          />
        </label>

        {/* Action Buttons */}
        <div className="ea-toolbar__actions" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {aiGrading && <GradingSuggestionButton
            classId={classId}
            targetType="submission"
            targetId={submissionId}
            onApplyGrade={(pts, fb) => {
              setRawScore(pts);
              setFeedback(fb);
              submissionResource.reload();
              onGraded();
            }}
          />}

          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              className="button button--secondary"
              disabled={saving}
              onClick={handleSaveGrade}
            >
              {saving ? "Đang lưu…" : "Lưu điểm"}
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={saving || returning || sub.status !== "graded"}
              onClick={handleReturn}
            >
              {returning ? "Đang trả…" : sub.status === "returned" ? "Đã trả bài" : "Trả bài này"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
