import { useState } from "react";

import { navigate } from "../../app/router";
import { errorMessage, useResource } from "../../app/useResource";
import { classesApi } from "../../api-client/classes";
import { subjectLabel } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { SubTabs } from "../shared/SubTabs";
import { auditApi } from "../../api-client/agents";
import { ClassAgentsTab } from "../agents/ClassAgentsTab";
import { AuditLogView } from "../audit/AuditLogView";
import { DocumentsTab } from "../documents/DocumentsTab";
import { ClassFormDialog } from "./ClassForm";
import { MembersTab } from "./MembersTab";
import { PolicyTab } from "./PolicyTab";

export function ClassDetailPage({ classId }: { classId: string }) {
  const room = useResource(() => classesApi.get(classId), [classId]);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState("");

  if (room.error) {
    return (
      <div className="ea-page">
        <div className="ea-error">{room.error}</div>
        <button className="button button--secondary" type="button" onClick={() => navigate("/teacher/classes")}>
          <Icon name="chevron-left" /> Về danh sách lớp
        </button>
      </div>
    );
  }
  if (!room.data) return <p className="ea-muted">Đang tải lớp…</p>;
  const data = room.data;

  async function rotate() {
    try {
      room.setData(await classesApi.rotateCode(data.id));
      setNotice("Đã tạo mã mới. Mã cũ không còn dùng được; học sinh đã tham gia vẫn ở trong lớp.");
    } catch (reason) {
      setNotice(errorMessage(reason));
    }
  }

  async function copyCode() {
    if (!data.join_code) return;
    try {
      await navigator.clipboard.writeText(data.join_code);
      setNotice("Đã sao chép mã lớp.");
    } catch {
      setNotice(`Mã lớp: ${data.join_code}`);
    }
  }

  return (
    <div className="ea-page">
      <button className="ea-back" type="button" onClick={() => navigate("/teacher/classes")}><Icon name="chevron-left" /> Lớp của tôi</button>
      <section className="ea-card">
        <div className="ea-card__meta">
          <span className="ea-chip">{subjectLabel(data.subject)}</span>
          <span>Lớp {data.grade}</span>
          <span>· {data.student_count} học sinh</span>
          {data.archived && <span className="ea-chip ea-chip--warn">Đã lưu trữ</span>}
        </div>
        <div className="ea-toolbar">
          <h2>{data.name}</h2>
          <div className="ea-toolbar__actions">
            <button className="button button--secondary" type="button" onClick={() => setEditing(true)}><Icon name="edit" /> Sửa</button>
          </div>
        </div>
        {data.description && <p className="ea-muted">{data.description}</p>}
        {data.join_code && (
          <div className="ea-inline-form">
            <span className="ea-code" aria-label="Mã lớp">{data.join_code}</span>
            <button className="button button--secondary" type="button" onClick={() => void copyCode()}>Sao chép mã</button>
            <button className="button button--ghost" type="button" onClick={() => void rotate()}>Đổi mã</button>
          </div>
        )}
        {notice && <p className="ea-muted" role="status">{notice}</p>}
      </section>

      <SubTabs
        ariaLabel="Quản lý lớp"
        idPrefix="class"
        tabs={[
          { id: "members", label: "Thành viên", description: "Học sinh, phụ huynh đã liên kết và trạng thái đồng ý.", render: () => <MembersTab room={data} /> },
          { id: "agents", label: "Agent", description: "Agent đang dùng trong lớp.", render: () => <ClassAgentsTab room={data} /> },
          { id: "documents", label: "Tài liệu", description: "Tài liệu agent được phép đọc khi trả lời trong lớp.", render: () => <DocumentsTab room={data} /> },
          { id: "policy", label: "Chính sách", description: "Quy tắc áp dụng cho mọi agent trong lớp.", render: () => <PolicyTab room={data} /> },
          { id: "audit", label: "Nhật ký", description: "Các lần hệ thống chặn hoặc cảnh báo trong lớp.", render: () => <AuditLogView load={(filters) => auditApi.forClass(data.id, filters)} scope={data.id} /> },
        ]}
      />

      {editing && (
        <ClassFormDialog
          initial={{ name: data.name, subject: data.subject, grade: data.grade, description: data.description, require_parent_consent: data.require_parent_consent }}
          onClose={() => setEditing(false)}
          onSubmit={async (input) => {
            room.setData(await classesApi.update(data.id, input));
            setEditing(false);
          }}
        />
      )}
    </div>
  );
}
