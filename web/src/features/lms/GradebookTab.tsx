import { useState } from "react";
import type { ClassRoom } from "../../api-client/types";
import { type GradebookColumn, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import "./lms.css";

const STATE_LABELS: Record<string, string> = {
  open: "Chưa nộp",
  not_assigned: "Chưa giao",
  missing: "Chưa nộp",
  in_progress: "Đang làm",
  pending: "Chờ chấm",
  graded: "Đã chấm",
  returned: "Đã trả",
};

export function GradebookTab({ room }: { room: ClassRoom }) {
  const classId = room.id;
  const gradebookResource = useResource(() => lmsApi.gradebook.get(classId), [classId]);
  const data = gradebookResource.data;

  // Column edit dialog state
  const [editingCol, setEditingCol] = useState<GradebookColumn | null>(null);
  const [editWeight, setEditWeight] = useState<number>(1);
  const [editCounts, setEditCounts] = useState<boolean>(true);
  const [savingCol, setSavingCol] = useState(false);
  const [colError, setColError] = useState("");

  if (gradebookResource.loading && !data) {
    return <p className="ea-muted">Đang tải sổ điểm…</p>;
  }

  if (gradebookResource.error) {
    return <div className="ea-error">{gradebookResource.error}</div>;
  }

  if (!data || data.rows.length === 0) {
    return (
      <div className="ea-card lms-gradebook-tab">
        <div className="ea-toolbar">
          <h3>Sổ điểm lớp học</h3>
          <a
            href={lmsApi.gradebook.csvUrl(classId)}
            download
            className="button button--secondary"
          >
            <Icon name="file" /> Tải CSV
          </a>
        </div>
        <p className="ea-muted" style={{ padding: "var(--space-4) 0" }}>
          Lớp học chưa có học sinh hoặc chưa có bài tập/bài kiểm tra nào.
        </p>
      </div>
    );
  }

  const columns = data.columns ?? [];
  const rows = data.rows ?? [];

  async function handleSaveColumn() {
    if (!editingCol) return;
    setSavingCol(true);
    setColError("");
    try {
      await lmsApi.gradebook.updateColumn(classId, editingCol.item_id, {
        weight: editWeight,
        counts_in_grade: editCounts,
      });
      setEditingCol(null);
      gradebookResource.reload();
    } catch (err: unknown) {
      setColError(errorMessage(err));
    } finally {
      setSavingCol(false);
    }
  }

  return (
    <div className="ea-card lms-gradebook-tab" style={{ display: "grid", gap: "var(--space-3)" }}>
      <div className="ea-toolbar">
        <div>
          <h3>Sổ điểm lớp học</h3>
          <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
            {rows.filter((row) => !row.left_class).length} học sinh · {columns.length} đầu điểm
          </span>
        </div>

        <div className="ea-toolbar__actions">
          <a
            href={lmsApi.gradebook.csvUrl(classId)}
            download
            className="button button--secondary"
          >
            <Icon name="file" /> Tải CSV
          </a>
        </div>
      </div>

      <div
        className="lms-gradebook-scroll-wrapper"
        style={{
          overflowX: "auto",
          maxWidth: "100%",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius-sm)",
        }}
      >
        <table
          className="ea-table lms-gradebook-table"
          style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}
        >
          <thead>
            <tr style={{ background: "var(--surface-subtle, #f8f9fa)" }}>
              {/* Sticky Student Column Header */}
              <th
                style={{
                  position: "sticky",
                  left: 0,
                  zIndex: 2,
                  background: "inherit",
                  padding: "10px 14px",
                  borderRight: "2px solid var(--line)",
                  borderBottom: "2px solid var(--line)",
                  minWidth: "160px",
                }}
              >
                Học sinh
              </th>

              {/* Dynamic Columns */}
              {columns.map((col) => (
                <th
                  key={col.item_id}
                  style={{
                    padding: "10px 12px",
                    borderRight: "1px solid var(--line)",
                    borderBottom: "2px solid var(--line)",
                    minWidth: "140px",
                    textAlign: "center",
                    verticalAlign: "top",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span className="ea-chip" style={{ fontSize: "0.75rem" }}>
                        {col.kind === "quiz" ? "Quiz" : "Bài tập"}
                      </span>
                      <button
                        type="button"
                        className="button button--ghost"
                        style={{ padding: "2px 4px", height: "auto" }}
                        onClick={() => {
                          setEditingCol(col);
                          setEditWeight(col.weight ?? 1);
                          setEditCounts(col.counts ?? true);
                        }}
                        title="Sửa trọng số & tính điểm"
                      >
                        <Icon name="edit" />
                      </button>
                    </div>

                    <a
                      href={
                        col.kind === "quiz"
                          ? `/teacher/classes/${classId}/quizzes/${col.item_id}`
                          : `/teacher/classes/${classId}/assignments/${col.item_id}`
                      }
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(
                          col.kind === "quiz"
                            ? `/teacher/classes/${classId}/quizzes/${col.item_id}`
                            : `/teacher/classes/${classId}/assignments/${col.item_id}`,
                        );
                      }}
                      style={{
                        fontWeight: 600,
                        color: "var(--primary)",
                        textDecoration: "none",
                        fontSize: "0.9rem",
                      }}
                    >
                      {col.title}
                    </a>

                    <span className="ea-muted" style={{ fontSize: "0.75rem" }}>
                      Tối đa: {col.max_points}đ · Hệ số: {col.weight}
                      {!col.counts && " · (Không tính)"}
                    </span>
                  </div>
                </th>
              ))}

              {/* Average Column Header */}
              <th
                style={{
                  padding: "10px 14px",
                  borderBottom: "2px solid var(--line)",
                  minWidth: "120px",
                  textAlign: "center",
                  fontWeight: 700,
                  background: "inherit",
                }}
              >
                Trung bình (thang 10)
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.student.id} style={{ borderBottom: "1px solid var(--line)" }}>
                {/* Sticky Student Column */}
                <td
                  style={{
                    position: "sticky",
                    left: 0,
                    zIndex: 1,
                    background: "var(--surface, #fff)",
                    padding: "10px 14px",
                    fontWeight: 600,
                    borderRight: "2px solid var(--line)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {row.student.name}
                  {row.left_class && <small className="ea-muted" style={{ marginLeft: "6px" }}>Đã rời lớp</small>}
                </td>

                {/* Cells */}
                {row.cells.map((cell, idx) => {
                  const col = columns[idx];
                  const hasScore = cell.final !== null && cell.final !== undefined;
                  const label = hasScore
                    ? `${cell.final}đ`
                    : STATE_LABELS[cell.state] || cell.state || "—";

                  return (
                    <td
                      key={col ? col.item_id : idx}
                      style={{
                        padding: "8px 12px",
                        textAlign: "center",
                        borderRight: "1px solid var(--line)",
                        cursor: col ? "pointer" : "default",
                      }}
                      onClick={() => {
                        if (!col) return;
                        navigate(
                          col.kind === "quiz"
                            ? `/teacher/classes/${classId}/quizzes/${col.item_id}`
                            : `/teacher/classes/${classId}/assignments/${col.item_id}`,
                        );
                      }}
                      title="Bấm để tới bài làm"
                    >
                      <span
                        className={`ea-chip ${
                          hasScore
                            ? "ea-chip--ok"
                            : cell.state === "pending"
                              ? "ea-chip--warn"
                              : cell.state === "in_progress"
                                ? "ea-chip--info"
                                : ""
                        }`}
                        style={{ fontSize: "0.85rem" }}
                      >
                        {label}
                      </span>
                    </td>
                  );
                })}

                {/* Average Score */}
                <td
                  style={{
                    padding: "8px 14px",
                    textAlign: "center",
                    fontWeight: 700,
                    fontSize: "1rem",
                    color: "var(--primary)",
                  }}
                >
                  {row.average !== null && row.average !== undefined
                    ? Number(row.average).toFixed(1)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Edit Column Modal */}
      {editingCol && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setEditingCol(null)}>
          <div
            className="dialog frosted"
            style={{ maxWidth: "450px", width: "95%" }}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="ea-toolbar">
              <h3>Cài đặt cột: {editingCol.title}</h3>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => setEditingCol(null)}
              >
                <Icon name="x" />
              </button>
            </div>

            {colError && <div className="ea-error" style={{ marginBottom: "var(--space-2)" }}>{colError}</div>}

            <div style={{ display: "grid", gap: "var(--space-3)", margin: "var(--space-3) 0" }}>
              <label className="field">
                <span>Hệ số trọng số</span>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={editWeight}
                  onChange={(e) => setEditWeight(parseFloat(e.target.value) || 0)}
                  disabled={savingCol}
                />
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={editCounts}
                  onChange={(e) => setEditCounts(e.target.checked)}
                  disabled={savingCol}
                />
                <span>Tính vào điểm tổng kết</span>
              </label>
            </div>

            <div className="dialog-actions">
              <button
                type="button"
                className="button button--secondary"
                disabled={savingCol}
                onClick={() => setEditingCol(null)}
              >
                Huỷ
              </button>
              <button
                type="button"
                className="button button--primary"
                disabled={savingCol}
                onClick={handleSaveColumn}
              >
                {savingCol ? "Đang lưu…" : "Lưu cài đặt"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
