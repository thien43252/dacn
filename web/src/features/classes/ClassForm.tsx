import { type FormEvent, useState } from "react";

import { Modal } from "../../agents/Modal";
import { errorMessage } from "../../app/useResource";
import { SUBJECT_LABELS, type ClassInput, type SubjectCode } from "../../api-client/types";

const EMPTY: ClassInput = { name: "", subject: "toan", grade: 8, description: "", require_parent_consent: true };

/** Create or edit a class. `initial` switches it to edit mode. */
export function ClassFormDialog({ initial, onSubmit, onClose }: {
  initial?: ClassInput;
  onSubmit: (input: ClassInput) => Promise<void>;
  onClose: () => void;
}) {
  const [form, setForm] = useState<ClassInput>(initial ?? EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof ClassInput>(key: K, value: ClassInput[K]) => setForm((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (form.name.trim().length < 2) {
      setError("Tên lớp cần có ít nhất 2 ký tự.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit({ ...form, name: form.name.trim() });
    } catch (reason) {
      setError(errorMessage(reason));
      setBusy(false);
    }
  }

  return (
    <Modal
      title={initial ? "Sửa thông tin lớp" : "Tạo lớp mới"}
      eyebrow="LỚP HỌC"
      onClose={onClose}
      busy={busy}
      footer={
        <>
          <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>Huỷ</button>
          <button className="button button--primary" type="submit" form="class-form" disabled={busy}>
            {busy ? <span className="button-spinner" /> : null} {initial ? "Lưu" : "Tạo lớp"}
          </button>
        </>
      }
    >
      <form id="class-form" className="ea-form" onSubmit={submit} noValidate>
        <label className="field">
          <span>Tên lớp</span>
          <input value={form.name} onChange={(event) => set("name", event.target.value)} placeholder="Toán 8A1 – học thêm tối thứ 3" />
        </label>
        <div className="ea-form__row">
          <label className="field">
            <span>Môn học</span>
            <select value={form.subject} onChange={(event) => set("subject", event.target.value as SubjectCode)}>
              {Object.entries(SUBJECT_LABELS).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Khối lớp</span>
            <select value={form.grade} onChange={(event) => set("grade", Number(event.target.value))}>
              {Array.from({ length: 12 }, (_, index) => index + 1).map((grade) => <option key={grade} value={grade}>Lớp {grade}</option>)}
            </select>
          </label>
        </div>
        <label className="field">
          <span>Mô tả (không bắt buộc)</span>
          <textarea rows={3} value={form.description} onChange={(event) => set("description", event.target.value)} />
        </label>
        <label className="ea-switch">
          <input type="checkbox" checked={form.require_parent_consent} onChange={(event) => set("require_parent_consent", event.target.checked)} />
          <span>
            <strong>Cần phụ huynh đồng ý</strong>
            <br />
            <small className="ea-muted">Học sinh chỉ dùng được agent khi phụ huynh đã liên kết và đồng ý. Nên bật với học sinh dưới 16 tuổi.</small>
          </span>
        </label>
        {error && <div className="form-error" role="alert">{error}</div>}
      </form>
    </Modal>
  );
}
