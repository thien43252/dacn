import { type FormEvent, useState } from "react";

import { Modal } from "../../agents/Modal";
import { errorMessage, useResource } from "../../app/useResource";
import { classesApi } from "../../api-client/classes";
import type { ClassRoom, Member } from "../../api-client/types";
import { Icon } from "../../components/Icon";
import { ConfirmDialog } from "../shared/ConfirmDialog";

export function MembersTab({ room }: { room: ClassRoom }) {
  const members = useResource(() => classesApi.members(room.id), [room.id]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [linking, setLinking] = useState<Member | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const students = (members.data ?? []).filter((member) => member.role === "student");

  async function addStudent(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError("");
    try {
      members.setData(await classesApi.addMember(room.id, email.trim()));
      setEmail("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await classesApi.removeMember(room.id, removing.user_id);
      setRemoving(null);
      members.reload();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ea-page">
      <div className="ea-notice">
        Học sinh tự tham gia bằng mã lớp <strong>{room.join_code}</strong>, hoặc bạn thêm bằng email tài khoản đã có.
        Phụ huynh liên kết với con bằng mã liên kết trong mục “Lớp của tôi” của học sinh, hoặc bạn liên kết giúp ở cột Phụ huynh.
      </div>

      <form className="ea-inline-form" onSubmit={addStudent}>
        <label className="field">
          <span>Thêm học sinh bằng email</span>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="hocsinh@email.com" />
        </label>
        <button className="button button--primary" type="submit" disabled={busy || !email.trim()}><Icon name="plus" /> Thêm</button>
      </form>
      {error && <div className="form-error" role="alert">{error}</div>}
      {members.error && <div className="ea-error">{members.error}</div>}

      {members.data && students.length === 0 && (
        <div className="ea-empty"><Icon name="team" /><p>Lớp chưa có học sinh.</p></div>
      )}

      {students.length > 0 && (
        <div className="ea-table-wrap">
          <table className="ea-table">
            <thead>
              <tr><th>Học sinh</th><th>Phụ huynh</th><th>Dùng agent</th><th aria-label="Thao tác" /></tr>
            </thead>
            <tbody>
              {students.map((member) => (
                <tr key={member.user_id}>
                  <td><strong>{member.name}</strong><br /><span className="ea-muted">{member.email}</span></td>
                  <td>
                    {member.parents.length === 0 && <span className="ea-muted">Chưa liên kết</span>}
                    {member.parents.map((parent) => <div key={parent.id}>{parent.name} <span className="ea-muted">· {parent.email}</span></div>)}
                    <button className="button button--ghost" type="button" onClick={() => setLinking(member)}>
                      <Icon name="plus" /> Liên kết phụ huynh
                    </button>
                  </td>
                  <td>
                    {member.can_use_agents
                      ? <span className="ea-chip ea-chip--ok">Được phép</span>
                      : <span className="ea-chip ea-chip--warn" title="Phụ huynh chưa đồng ý">Chờ phụ huynh đồng ý</span>}
                  </td>
                  <td>
                    <button className="icon-button icon-button--danger" type="button" aria-label={`Xoá ${member.name} khỏi lớp`} onClick={() => setRemoving(member)}>
                      <Icon name="trash" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {linking && (
        <LinkParentDialog
          student={linking}
          onClose={() => setLinking(null)}
          onSubmit={async (parentEmail) => {
            members.setData(await classesApi.linkParent(room.id, linking.user_id, parentEmail));
            setLinking(null);
          }}
        />
      )}

      <ConfirmDialog
        open={removing !== null}
        title={`Xoá ${removing?.name ?? ""} khỏi lớp?`}
        description="Học sinh sẽ không còn thấy agent và tài liệu của lớp. Có thể tham gia lại bằng mã lớp."
        confirmLabel="Xoá khỏi lớp"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}

function LinkParentDialog({ student, onSubmit, onClose }: {
  student: Member;
  onSubmit: (email: string) => Promise<void>;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit(email.trim());
    } catch (reason) {
      setError(errorMessage(reason));
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Liên kết phụ huynh của ${student.name}`}
      eyebrow="PHỤ HUYNH"
      onClose={onClose}
      busy={busy}
      footer={<button className="button button--primary" type="submit" form="link-parent" disabled={busy || !email.trim()}>Liên kết</button>}
    >
      <form id="link-parent" onSubmit={submit}>
        <p className="ea-muted">Phụ huynh cần có tài khoản vai trò Phụ huynh. Sau khi liên kết, phụ huynh tự quyết định đồng ý cho con dùng agent.</p>
        <label className="field">
          <span>Email phụ huynh</span>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="phuhuynh@email.com" />
        </label>
        {error && <div className="form-error" role="alert">{error}</div>}
      </form>
    </Modal>
  );
}
