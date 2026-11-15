import { type MyGrades, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import "./lms.css";

export function MyGradesPage({ classId, studentId }: { classId: string; studentId?: string }) {
  const gradesResource = useResource(
    () => lmsApi.myGrades.get(classId, studentId),
    [classId, studentId],
  );

  const data: MyGrades | null = gradesResource.data;

  return (
    <div className="ea-page lms-my-grades-page">
      <button
        className="ea-back"
        type="button"
        onClick={() => navigate(`/student/classes/${classId}`)}
      >
        <Icon name="chevron-left" /> Về lớp học
      </button>

      <div className="ea-toolbar">
        <div>
          <h2>Điểm số của tôi</h2>
          <span className="ea-muted">
            Xem điểm các bài kiểm tra và bài tập đã được trả kết quả
          </span>
        </div>
      </div>

      {gradesResource.loading && !data ? (
        <p className="ea-muted">Đang tải điểm số…</p>
      ) : gradesResource.error ? (
        <div className="ea-error">{gradesResource.error}</div>
      ) : !data || data.items.length === 0 ? (
        <div className="ea-card">
          <p className="ea-muted">Lớp học này chưa có bài nào được trả điểm.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {/* Average Banner */}
          {data.overall_average !== null && data.overall_average !== undefined && (
            <div
              className="ea-card"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderLeft: "6px solid var(--primary)",
              }}
            >
              <div>
                <span className="ea-muted" style={{ fontSize: "0.9rem" }}>Điểm trung bình các bài đã trả:</span>
                <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--primary)" }}>
                  {Number(data.overall_average).toFixed(1)} / 10
                </div>
              </div>
            </div>
          )}

          {/* Items Table */}
          <div className="ea-card">
            <h3>Danh sách bài đã trả ({data.items.length})</h3>
            <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
              <table className="ea-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--line)", textAlign: "left" }}>
                    <th style={{ padding: "8px" }}>Tên bài</th>
                    <th style={{ padding: "8px" }}>Loại</th>
                    <th style={{ padding: "8px" }}>Điểm đạt được</th>
                    <th style={{ padding: "8px" }}>Ngày trả điểm</th>
                    <th style={{ padding: "8px" }}>Chi tiết</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => {
                    const path =
                      item.kind === "quiz"
                        ? `/student/classes/${classId}/quizzes/${item.item_id}/result`
                        : `/student/classes/${classId}/assignments/${item.item_id}`;

                    return (
                      <tr key={item.item_id} style={{ borderBottom: "1px solid var(--line)" }}>
                        <td style={{ padding: "8px", fontWeight: 600 }}>{item.title}</td>
                        <td style={{ padding: "8px" }}>
                          <span className="ea-chip">
                            {item.kind === "quiz" ? "Quiz" : "Bài tập"}
                          </span>
                        </td>
                        <td style={{ padding: "8px", fontWeight: 700, color: "var(--primary)" }}>
                          {item.score !== null && item.score !== undefined
                            ? `${item.score} / ${item.max_points}`
                            : "—"}
                        </td>
                        <td style={{ padding: "8px", fontSize: "0.85rem" }}>
                          {item.returned_at ? new Date(item.returned_at).toLocaleDateString("vi-VN") : "—"}
                        </td>
                        <td style={{ padding: "8px" }}>
                          <button
                            type="button"
                            className="button button--secondary"
                            style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                            onClick={() => navigate(path)}
                          >
                            Xem bài
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
