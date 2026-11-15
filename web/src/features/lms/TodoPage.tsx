import { type TodoItem, lmsApi } from "../../api-client/lms";
import { navigate } from "../../app/router";
import { useResource } from "../../app/useResource";
import { Icon } from "../../components/Icon";
import "./lms.css";

export function TodoPage({ studentId }: { studentId?: string }) {
  const todoResource = useResource(() => lmsApi.todo.list(studentId), [studentId]);
  const items: TodoItem[] = todoResource.data ?? [];

  return (
    <div className="ea-page lms-todo-page">
      <div className="ea-toolbar">
        <div>
          <h2>Việc cần làm</h2>
          <span className="ea-muted">
            Danh sách bài tập và bài kiểm tra chưa hoàn thành cần thực hiện
          </span>
        </div>
      </div>

      {todoResource.loading && !todoResource.data ? (
        <p className="ea-muted">Đang tải danh sách việc cần làm…</p>
      ) : todoResource.error ? (
        <div className="ea-error">{todoResource.error}</div>
      ) : items.length === 0 ? (
        <div className="ea-empty">
          <Icon name="check" />
          <h3>Tuyệt vời!</h3>
          <p className="ea-muted">Bạn đã hoàn thành tất cả bài tập và bài kiểm tra.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          {items.map((item) => {
            const due = item.due_at ? new Date(item.due_at) : null;
            const isOverdue = due ? new Date() > due : false;
            const isDueSoon = due && !isOverdue ? due.getTime() - Date.now() <= 24 * 60 * 60 * 1000 : false;

            const path = item.link;

            return (
              <div
                key={item.item_id}
                className="ea-card"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "var(--space-3)",
                  borderLeft: isOverdue
                    ? "4px solid var(--danger, #ef4444)"
                    : isDueSoon
                      ? "4px solid var(--warning, #f59e0b)"
                      : "4px solid var(--primary)",
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="ea-chip">
                      {item.kind === "quiz" ? "Bài kiểm tra" : "Bài tập"}
                    </span>
                    <span className="ea-muted" style={{ fontSize: "0.85rem" }}>
                      {item.class_name}
                    </span>
                  </div>

                  <h3 style={{ margin: "var(--space-1) 0" }}>{item.title}</h3>

                  <div style={{ fontSize: "0.85rem" }}>
                    {due ? (
                      <span style={{ color: isOverdue ? "var(--danger)" : isDueSoon ? "var(--warning)" : "var(--muted)" }}>
                        <Icon name="history" /> Hạn nộp: {due.toLocaleString("vi-VN")}{" "}
                        {isOverdue ? "(Đã quá hạn)" : isDueSoon ? "(Sắp hết hạn!)" : ""}
                      </span>
                    ) : (
                      <span className="ea-muted">Không có hạn nộp</span>
                    )}
                  </div>
                </div>

                <div className="ea-toolbar__actions">
                  <button
                    type="button"
                    className="button button--primary"
                    onClick={() => navigate(path)}
                  >
                    {item.kind === "quiz" ? "Làm bài kiểm tra" : "Nộp bài tập"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
