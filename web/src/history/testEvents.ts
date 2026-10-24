import type { HistoryEvent } from "./api";

/** Test fixture: a confirmed plan event that each test overrides as needed. */
export function makeEvent(overrides: Partial<HistoryEvent> = {}): HistoryEvent {
  return {
    id: "hist-001",
    type: "plan.confirmed",
    category: "submission",
    occurred_at: "2026-09-25T03:00:00+00:00",
    actor: { kind: "self", name: "Minh Anh", agent_id: null },
    title: "Xác nhận Plan v3 để đánh giá",
    summary: "Tóm tắt",
    plan_owner_name: "Minh Anh",
    version: 3,
    previous_version: null,
    version_hash: "a1b2c3d",
    status: "CONFIRMED",
    coverage_percent: null,
    reference_id: null,
    subject: null,
    detail: null,
    teacher_note: null,
    ...overrides,
  };
}
