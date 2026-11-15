import { useState } from "react";
import { type AssignmentStudentView, type LmsFile, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { ApiError } from "../../api-client/http";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import { FileUpload } from "./FileUpload";
import "./lms.css";

export interface AssignmentViewProps {
  classId: string;
  assignmentId: string;
  role?: "student" | "parent";
  studentId?: string;
}

export function AssignmentView({
  classId,
  assignmentId,
  role = "student",
  studentId,
}: AssignmentViewProps) {
  const isParent = role === "parent";

  const assignmentResource = useResource(
    () => lmsApi.assignments.get(classId, assignmentId, studentId) as Promise<AssignmentStudentView>,
    [classId, assignmentId, studentId],
  );

  const asg = assignmentResource.data;

  // Student submission form states
  const [showSubmitForm, setShowSubmitForm] = useState(false);
  const [text, setText] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<LmsFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorNotice, setErrorNotice] = useState("");

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
          onClick={() => navigate(isParent ? `/parent/classes/${classId}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}` : `/student/classes/${classId}`)}
        >
          <Icon name="chevron-left" /> Về lớp học
        </button>
      </div>
    );
  }

  const submission = asg.submission;
  const versions = submission?.versions ?? [];
  const result = submission?.status === "returned" ? submission.result : undefined;
  const effectiveDueStr = asg.effective_due;
  const effectiveDue = effectiveDueStr ? new Date(effectiveDueStr) : null;
  const isPastDue = effectiveDue ? new Date() > effectiveDue : false;

  // Determine state chip
  let stateLabel = "Chưa nộp";
  let stateTone: "neutral" | "ok" | "warn" | "danger" = "neutral";

  if (submission) {
    if (submission.status === "returned") {
      stateLabel = "Đã trả";
      stateTone = "ok";
    } else if (submission.is_late) {
      stateLabel = "Nộp muộn";
      stateTone = "warn";
    } else {
      stateLabel = "Đã nộp";
      stateTone = "ok";
    }
  } else if (isPastDue) {
    stateLabel = "Quá hạn";
    stateTone = "danger";
  }

  const canSubmit = !isParent && (!isPastDue || asg.allow_late);

  async function handleSubmit() {
    if (!canSubmit || submitting || uploading) return;
    if (!text.trim() && uploadedFiles.length === 0) {
      setErrorNotice("Vui lòng nhập văn bản bài làm hoặc tải lên ít nhất một tệp đính kèm.");
      return;
    }

    setSubmitting(true);
    setErrorNotice("");
    setNotice("");
    try {
      await lmsApi.assignments.submit(classId, assignmentId, {
        text: text.trim(),
        file_ids: uploadedFiles.map((f) => f.id),
      });
      setNotice("Đã nộp bài tập thành công!");
      setText("");
      setUploadedFiles([]);
      setShowSubmitForm(false);
      assignmentResource.reload();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409 && err.message.includes("past_due")) {
        setErrorNotice("Bài tập đã quá hạn và không nhận bài nộp muộn.");
      } else {
        setErrorNotice(errorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="ea-page lms-assignment-view">
      <button
        className="ea-back"
        type="button"
        onClick={() => navigate(isParent ? `/parent/classes/${classId}${studentId ? `?student_id=${encodeURIComponent(studentId)}` : ""}` : `/student/classes/${classId}`)}
      >
        <Icon name="chevron-left" /> Về lớp học
      </button>

      <div className="ea-toolbar">
        <div>
          <h2>Yêu cầu bài tập</h2>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "4px" }}>
            <span
              className={`ea-chip ${
                stateTone === "ok"
                  ? "ea-chip--ok"
                  : stateTone === "warn"
                    ? "ea-chip--warn"
                    : stateTone === "danger"
                      ? "ea-chip--danger"
                      : ""
              }`}
            >
              {stateLabel}
            </span>
            <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
              Tối đa {asg.max_points} điểm · Hạn nộp:{" "}
              {effectiveDue ? effectiveDue.toLocaleString("vi-VN") : "Không có hạn"}
            </span>
          </div>
        </div>

        {canSubmit && submission && !showSubmitForm && (
          <div className="ea-toolbar__actions">
            <button
              type="button"
              className="button button--secondary"
              onClick={() => setShowSubmitForm(true)}
            >
              Nộp lại bài
            </button>
          </div>
        )}
      </div>

      {notice && <div className="ea-notice ea-notice--ok">{notice}</div>}
      {errorNotice && <div className="ea-error">{errorNotice}</div>}

      {/* Assignment Prompt Card */}
      <div className="ea-card">
        <h3>Đề bài</h3>
        <div style={{ whiteSpace: "pre-wrap", margin: "var(--space-2) 0 var(--space-3)", lineHeight: 1.6 }}>
          {asg.prompt || "Chưa có đề bài chi tiết."}
        </div>

        {/* Prompt files */}
        {asg.prompt_file_ids && asg.prompt_file_ids.length > 0 && (
          <div style={{ marginTop: "var(--space-3)", borderTop: "1px solid var(--line)", paddingTop: "var(--space-2)" }}>
            <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Tệp tài liệu đính kèm:</span>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "6px" }}>
              {asg.prompt_file_ids.map((fileId) => (
                <a
                  key={fileId}
                  href={lmsApi.files.url(classId, fileId, true)}
                  target="_blank"
                  rel="noreferrer"
                  className="ea-chip"
                  style={{ textDecoration: "none", color: "var(--primary)" }}
                >
                  <Icon name="file" /> Tải tệp #{fileId.slice(0, 8)}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Result Block when Returned */}
      {result && (
        <div
          className="ea-card"
          style={{
            borderLeft: "6px solid var(--success, #22c55e)",
            background: "var(--surface, #fff)",
          }}
        >
          <h3>Kết quả đánh giá của giáo viên</h3>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "var(--space-3)",
              margin: "var(--space-3) 0",
            }}
          >
            <div>
              <span className="ea-muted" style={{ fontSize: "0.85rem" }}>Điểm chấm:</span>
              <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>
                {result.raw_score !== null && result.raw_score !== undefined
                  ? `${result.raw_score} / ${asg.max_points}`
                  : "—"}
              </div>
            </div>

            <div>
              <span className="ea-muted" style={{ fontSize: "0.85rem" }}>Trừ nộp muộn:</span>
              <div style={{ fontSize: "1.2rem", fontWeight: 700, color: (result.penalty ?? 0) > 0 ? "var(--danger)" : "inherit" }}>
                -{result.penalty}
              </div>
            </div>

            <div>
              <span className="ea-muted" style={{ fontSize: "0.85rem" }}>Điểm cuối cùng:</span>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--primary)" }}>
                {result.final_score ?? "—"} / {asg.max_points}
              </div>
            </div>
          </div>

          {result.feedback && (
            <div
              style={{
                marginTop: "var(--space-2)",
                padding: "10px 14px",
                background: "var(--surface-subtle, #f9f9f9)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <strong>Nhận xét:</strong>
              <p style={{ margin: "4px 0 0", fontStyle: "italic", whiteSpace: "pre-wrap" }}>
                {result.feedback}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Student Submission Form (Hidden for parents) */}
      {canSubmit && (!submission || showSubmitForm) && (
        <div className="ea-card">
          <h3>{submission ? "Nộp lại bài tập (Tạo phiên bản mới)" : "Nộp bài tập"}</h3>

          <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
            <label className="field">
              <span>Nội dung bài làm (văn bản)</span>
              <textarea
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Nhập câu trả lời hoặc phần trình bày của bạn…"
                disabled={submitting}
              />
            </label>

            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>Tệp đính kèm bài làm</span>
              {uploadedFiles.length > 0 && (
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  {uploadedFiles.map((f) => (
                    <div key={f.id} className="ea-chip" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <Icon name="file" /> {f.filename}
                      <button
                        type="button"
                        className="button button--ghost"
                        style={{ padding: 0 }}
                        onClick={() => setUploadedFiles(uploadedFiles.filter((item) => item.id !== f.id))}
                        title="Gỡ tệp"
                      >
                        <Icon name="x" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <FileUpload
                classId={classId}
                purpose="submission"
                onUploadingChange={setUploading}
                label="Tải lên tệp bài làm"
                onUploaded={(f) => setUploadedFiles((files) => [...files, f])}
                disabled={submitting}
              />
            </div>

            <div className="ea-toolbar__actions" style={{ marginTop: "var(--space-2)" }}>
              {showSubmitForm && (
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={submitting}
                  onClick={() => setShowSubmitForm(false)}
                >
                  Huỷ
                </button>
              )}
              <button
                type="button"
                className="button button--primary"
                disabled={submitting || uploading}
                onClick={handleSubmit}
              >
                {submitting ? "Đang gửi bài…" : "Xác nhận nộp bài"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version History List */}
      {versions.length > 0 && (
        <div className="ea-card">
          <h3>Lịch sử nộp bài ({versions.length} phiên bản)</h3>
          <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-3)" }}>
            {[...versions].reverse().map((v) => (
              <div
                key={v.version_no}
                style={{
                  padding: "12px",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius-sm)",
                  background: v.version_no === submission?.latest_version ? "var(--surface, #fff)" : "var(--surface-subtle, #fbfbfb)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>
                    Phiên bản {v.version_no} {v.version_no === submission?.latest_version ? "(Mới nhất)" : ""}
                  </strong>
                  <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
                    {new Date(v.submitted_at).toLocaleString("vi-VN")}
                    {v.is_late && <span className="ea-chip ea-chip--warn" style={{ marginLeft: "8px" }}>Nộp muộn</span>}
                  </span>
                </div>

                {v.text && <p style={{ margin: "8px 0 4px", whiteSpace: "pre-wrap" }}>{v.text}</p>}

                {v.file_ids && v.file_ids.length > 0 && (
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "6px" }}>
                    {v.file_ids.map((fid) => (
                      <a
                        key={fid}
                        href={lmsApi.files.url(classId, fid, true)}
                        target="_blank"
                        rel="noreferrer"
                        className="ea-chip"
                        style={{ textDecoration: "none", color: "var(--primary)", fontSize: "0.8rem" }}
                      >
                        <Icon name="file" /> Tải tệp #{fid.slice(0, 8)}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
