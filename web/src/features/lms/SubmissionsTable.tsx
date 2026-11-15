import { useState } from "react";
import { type GradeAuditLog, lmsApi } from "../../api-client/lms";
import { errorMessage, useResource } from "../../app/useResource";
import { localDateTime } from "./formValues";
import { BulkGradingSuggestions } from "./SuggestionReview";
import { Icon } from "../../components/Icon";

export interface SubmissionsTableProps {
  classId: string;
  assignmentId: string;
  onSelectSubmission: (submissionId: string) => void;
  onReload?: () => void;
  aiGrading: boolean;
  reloadKey?: number;
}

export function SubmissionsTable({
  classId,
  assignmentId,
  onSelectSubmission,
  onReload,
  aiGrading,
  reloadKey,
}: SubmissionsTableProps) {
  const rosterResource = useResource(
    () => lmsApi.assignments.listSubmissions(classId, assignmentId),
    [classId, assignmentId, reloadKey],
  );

  const roster = rosterResource.data ?? [];

  // Extension dialog state
  const [extendingStudent, setExtendingStudent] = useState<{
    id: string;
    name: string;
    currentDue?: string | null;
  } | null>(null);
  const [extDueAt, setExtDueAt] = useState("");
  const [extBusy, setExtBusy] = useState(false);
  const [extError, setExtError] = useState("");

  // Return all graded state
  const [returningAll, setReturningAll] = useState(false);
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");

  // Grade Audit dialog state
  const [showAuditModal, setShowAuditModal] = useState(false);

  async function handleSaveExtension() {
    if (!extendingStudent) return;
    setExtBusy(true);
    setExtError("");
    try {
      if (!extDueAt) {
        await lmsApi.assignments.deleteExtension(classId, assignmentId, extendingStudent.id);
      } else {
        await lmsApi.assignments.setExtension(
          classId,
          assignmentId,
          extendingStudent.id,
          new Date(extDueAt).toISOString(),
        );
      }
      setExtendingStudent(null);
      rosterResource.reload();
      onReload?.();
    } catch (err: unknown) {
      setExtError(errorMessage(err));
    } finally {
      setExtBusy(false);
    }
  }

  async function handleDeleteExtension() {
    if (!extendingStudent) return;
    setExtBusy(true);
    setExtError("");
    try {
      await lmsApi.assignments.deleteExtension(classId, assignmentId, extendingStudent.id);
      setExtendingStudent(null);
      rosterResource.reload();
      onReload?.();
    } catch (err: unknown) {
      setExtError(errorMessage(err));
    } finally {
      setExtBusy(false);
    }
  }

  async function handleReturnAllGraded() {
    setReturningAll(true);
    setActionNotice("");
    setActionError("");
    try {
      const res = await lmsApi.assignments.returnSubmissions(classId, assignmentId);
      setActionNotice(`Đã trả điểm cho ${res.returned} học sinh.`);
      rosterResource.reload();
      onReload?.();
    } catch (err: unknown) {
      setActionError(errorMessage(err));
    } finally {
      setReturningAll(false);
    }
  }

  const gradedCount = roster.filter((r) => r.state === "graded").length;

  return (
    <div className="ea-card lms-submissions-table" style={{ display: "grid", gap: "var(--space-3)" }}>
      <div className="ea-toolbar">
        <div>
          <h3>Danh sách nộp bài ({roster.length} học sinh)</h3>
          <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
            Theo dõi trạng thái nộp bài, gia hạn riêng và chấm bài
          </span>
        </div>

        <div className="ea-toolbar__actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={() => setShowAuditModal(true)}
          >
            <Icon name="history" /> Lịch sử chấm
          </button>

          <button
            type="button"
            className="button button--primary"
            disabled={gradedCount === 0 || returningAll}
            onClick={handleReturnAllGraded}
          >
            {returningAll ? "Đang trả bài…" : `Trả tất cả bài đã chấm (${gradedCount})`}
          </button>
        </div>
      </div>

      {rosterResource.error && <div className="ea-error">{rosterResource.error}</div>}
      {actionNotice && <div className="ea-notice ea-notice--ok">{actionNotice}</div>}
      {actionError && <div className="ea-error">{actionError}</div>}
      {aiGrading && <BulkGradingSuggestions
        classId={classId}
        targets={roster.filter((row) => row.submission_id && (row.state === "submitted" || row.state === "late")).map((row) => ({ type: "submission", id: row.submission_id!, name: row.name }))}
        onReviewed={() => { rosterResource.reload(); onReload?.(); }}
      />}

      {rosterResource.loading && roster.length === 0 ? (
        <p className="ea-muted">Đang tải danh sách học sinh…</p>
      ) : roster.length === 0 ? (
        <p className="ea-muted">Lớp học chưa có học sinh nào.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="ea-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--line)", textAlign: "left" }}>
                <th style={{ padding: "8px" }}>Học sinh</th>
                <th style={{ padding: "8px" }}>Trạng thái</th>
                <th style={{ padding: "8px" }}>Hạn riêng</th>
                <th style={{ padding: "8px" }}>Thời gian nộp</th>
                <th style={{ padding: "8px" }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {roster.map((row) => {
                const state = row.state;
                const isSubmitted = state === "submitted" || state === "late" || state === "graded" || state === "returned";

                return (
                  <tr key={row.student_id} style={{ borderBottom: "1px solid var(--line)" }}>
                    <td style={{ padding: "8px", fontWeight: 600 }}>{row.name}</td>
                    <td style={{ padding: "8px" }}>
                      <span
                        className={`ea-chip ${
                          state === "returned"
                            ? "ea-chip--ok"
                            : state === "graded"
                              ? "ea-chip--info"
                              : state === "late"
                                ? "ea-chip--warn"
                                : state === "submitted"
                                  ? "ea-chip--ok"
                                  : ""
                        }`}
                      >
                        {state === "returned"
                          ? "Đã trả bài"
                          : state === "graded"
                            ? "Đã chấm"
                            : state === "late"
                              ? "Nộp muộn"
                              : state === "submitted"
                                ? "Đã nộp"
                                : "Chưa nộp"}
                      </span>
                    </td>
                    <td style={{ padding: "8px", fontSize: "0.85rem" }}>
                      {row.effective_due ? new Date(row.effective_due).toLocaleString("vi-VN") : "Theo hạn chung"}
                    </td>
                    <td style={{ padding: "8px", fontSize: "0.85rem" }}>
                      {row.submitted_at ? new Date(row.submitted_at).toLocaleString("vi-VN") : "—"}
                    </td>
                    <td style={{ padding: "8px" }}>
                      <div style={{ display: "flex", gap: "6px" }}>
                        {row.submission_id ? (
                          <button
                            type="button"
                            className="button button--secondary"
                            style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                            onClick={() => onSelectSubmission(row.submission_id!)}
                          >
                            Chấm bài
                          </button>
                        ) : null}

                        <button
                          type="button"
                          className="button button--ghost"
                          style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                          onClick={() => {
                            setExtendingStudent({
                              id: row.student_id,
                              name: row.name,
                              currentDue: row.effective_due,
                            });
                            setExtDueAt(localDateTime(row.effective_due));
                            setExtError("");
                          }}
                          title="Gia hạn riêng"
                        >
                          <Icon name="history" /> Gia hạn
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Extension Modal */}
      {extendingStudent && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setExtendingStudent(null)}>
          <div
            className="dialog frosted"
            style={{ maxWidth: "500px", width: "95%" }}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="ea-toolbar">
              <h3>Gia hạn riêng cho {extendingStudent.name}</h3>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => setExtendingStudent(null)}
              >
                <Icon name="x" />
              </button>
            </div>

            {extError && <div className="ea-error" style={{ marginBottom: "var(--space-3)" }}>{extError}</div>}

            <label className="field" style={{ margin: "var(--space-3) 0" }}>
              <span>Hạn nộp mới riêng cho học sinh này</span>
              <input
                type="datetime-local"
                value={extDueAt}
                onChange={(e) => setExtDueAt(e.target.value)}
                disabled={extBusy}
              />
            </label>

            <div className="dialog-actions" style={{ justifyContent: "space-between" }}>
              <button
                type="button"
                className="button button--danger"
                disabled={extBusy || !extendingStudent.currentDue}
                onClick={handleDeleteExtension}
              >
                Xoá gia hạn (về hạn chung)
              </button>

              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={extBusy}
                  onClick={() => setExtendingStudent(null)}
                >
                  Huỷ
                </button>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={extBusy || !extDueAt}
                  onClick={handleSaveExtension}
                >
                  {extBusy ? "Đang lưu…" : "Lưu gia hạn"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Grade Audit Modal */}
      {showAuditModal && (
        <GradeAuditModal
          classId={classId}
          targetId={assignmentId}
          onClose={() => setShowAuditModal(false)}
        />
      )}
    </div>
  );
}

interface GradeAuditModalProps {
  classId: string;
  targetId: string;
  onClose: () => void;
}

function GradeAuditModal({ classId, targetId, onClose }: GradeAuditModalProps) {
  const auditResource = useResource(
    () => lmsApi.gradeAudit.list(classId, { target_id: targetId }),
    [classId, targetId],
  );

  const logs: GradeAuditLog[] = auditResource.data ?? [];

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dialog frosted"
        style={{ maxWidth: "700px", width: "95%", maxHeight: "80vh", overflowY: "auto" }}
        role="dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ea-toolbar">
          <h3>Nhật ký điểm và chấm bài (Grade Audit)</h3>
          <button type="button" className="button button--ghost" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>

        {auditResource.error && <div className="ea-error">{auditResource.error}</div>}
        {auditResource.loading ? (
          <p className="ea-muted">Đang tải lịch sử…</p>
        ) : auditResource.error ? null : logs.length === 0 ? (
          <p className="ea-muted">Chưa có bản ghi nhật ký chấm nào cho bài này.</p>
        ) : (
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            {logs.map((log) => (
              <div
                key={log.id}
                style={{
                  padding: "8px 12px",
                  border: "1px solid var(--line)",
                  borderRadius: "4px",
                  fontSize: "0.85rem",
                  display: "grid",
                  gap: "4px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>
                    Thao tác: <span className="ea-chip">{log.action}</span>
                  </strong>
                  <span className="ea-muted">{new Date(log.created_at).toLocaleString("vi-VN")}</span>
                </div>
                {log.student_name && <div>Học sinh: {log.student_name}</div>}
                {log.before !== undefined && log.after !== undefined && (
                  <div style={{ color: "var(--muted)" }}>
                    Trước: {JSON.stringify(log.before)} ➔ Sau: {JSON.stringify(log.after)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="dialog-actions" style={{ marginTop: "var(--space-3)" }}>
          <button type="button" className="button button--secondary" onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
