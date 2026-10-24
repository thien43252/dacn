import { apiRequest } from "../api-client/http";

export type HistoryScope = "mine" | "team";
export type HistoryCategory = "submission" | "change" | "agent" | "team";
export type HistoryFilter = "all" | HistoryCategory;
export type HistoryEventType =
  | "discussion.create"
  | "discussion.edit"
  | "discussion.delete"
  | "discussion.reply"
  | "discussion.decide"
  | "plan.confirmed"
  | "evaluation.feasibility"
  | "evaluation.safety"
  | "plan.submitted"
  | "teacher.decision"
  | "plan.version_created"
  | "platform_agent_suggestion.created"
  | "team.task_completed"
  | "team.document_uploaded"
  | "team.member_joined"
  | "team.leader_changed";
export type HistoryActorKind = "self" | "member" | "teacher" | "agent";
export type AgentId = "planner" | "feasibility" | "safety" | "progress";
export type HistoryStatus =
  | "CONFIRMED"
  | "SUBMITTED"
  | "PASS"
  | "FAIL"
  | "NEEDS_INPUT"
  | "DISABLED"
  | "APPROVED"
  | "CHANGES_REQUESTED"
  | "REJECTED"
  | "SEEN";

export interface HistoryActor {
  kind: HistoryActorKind;
  name: string;
  agent_id: AgentId | null;
}

export interface DetailSection {
  label: string;
  items: string[];
}

export interface HistoryEvent {
  id: string;
  type: HistoryEventType;
  category: HistoryCategory;
  occurred_at: string;
  actor: HistoryActor;
  title: string;
  summary: string;
  plan_owner_name: string | null;
  version: number | null;
  previous_version: number | null;
  version_hash: string | null;
  status: HistoryStatus | null;
  coverage_percent: number | null;
  reference_id: string | null;
  subject: string | null;
  detail: DetailSection[] | null;
  teacher_note: string | null;
}

export interface StudentHistory {
  scope: HistoryScope;
  team: { id: string; name: string } | null;
  events: HistoryEvent[];
}

export interface HistoryParams {
  scope: HistoryScope;
  type: HistoryFilter;
  from?: string;
  to?: string;
}

export function historyQueryString({ scope, type, from, to }: HistoryParams): string {
  const params = new URLSearchParams({ scope, type });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  return params.toString();
}

export function getStudentHistory(studentId: string, params: HistoryParams): Promise<StudentHistory> {
  return apiRequest<StudentHistory>(`/api/students/${encodeURIComponent(studentId)}/history?${historyQueryString(params)}`);
}
