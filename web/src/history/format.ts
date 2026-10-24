import type { IconName } from "../components/Icon";
import { CORE_AGENT_LABELS } from "../components/mentions";
import type { AgentId, HistoryEvent, HistoryEventType, HistoryFilter, HistoryScope, HistoryStatus } from "./api";

export const SCHOOL_TIME_ZONE = "Asia/Ho_Chi_Minh";

export const SCOPE_OPTIONS: { value: HistoryScope; label: string }[] = [
  { value: "mine", label: "Của tôi" },
  { value: "team", label: "Cả nhóm" },
];

const TYPE_OPTIONS: { value: HistoryFilter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "submission", label: "Gửi kế hoạch" },
  { value: "change", label: "Thay đổi" },
  { value: "agent", label: "Đề xuất agent" },
  { value: "team", label: "Hoạt động nhóm" },
];

/** "Hoạt động nhóm" only exists in the team scope. */
export function typeOptionsFor(scope: HistoryScope) {
  return scope === "team" ? TYPE_OPTIONS : TYPE_OPTIONS.filter((option) => option.value !== "team");
}

export type TimePreset = "all" | "7d" | "30d" | "custom";

export const TIME_OPTIONS: { value: TimePreset; label: string }[] = [
  { value: "all", label: "Tất cả thời gian" },
  { value: "7d", label: "7 ngày qua" },
  { value: "30d", label: "30 ngày qua" },
  { value: "custom", label: "Tùy chọn" },
];

export type Tone = "success" | "danger" | "warning" | "primary" | "neutral";

export interface BadgeMeta {
  label: string;
  icon: IconName;
  tone: Tone;
}

// Every badge carries an icon and text so colour is never the only signal.
export const STATUS_META: Record<HistoryStatus, BadgeMeta> = {
  CONFIRMED: { label: "Đã xác nhận", icon: "check", tone: "primary" },
  SUBMITTED: { label: "Đã gửi duyệt", icon: "send", tone: "primary" },
  PASS: { label: "Đạt", icon: "check", tone: "success" },
  FAIL: { label: "Chưa đạt", icon: "x", tone: "danger" },
  NEEDS_INPUT: { label: "Cần bổ sung thông tin", icon: "alert", tone: "warning" },
  DISABLED: { label: "Chưa đánh giá, agent đang tắt", icon: "lock", tone: "neutral" },
  APPROVED: { label: "Đã duyệt", icon: "check", tone: "success" },
  CHANGES_REQUESTED: { label: "Yêu cầu sửa", icon: "edit", tone: "warning" },
  REJECTED: { label: "Từ chối", icon: "x", tone: "danger" },
  SEEN: { label: "Đã xem", icon: "eye", tone: "success" },
};

export const SUGGESTION_EVENT: HistoryEventType = "platform_agent_suggestion.created";

/** Badges of a new-agent suggestion, shared with the proposals tab so both show the same record the same way. */
export const SUGGESTION_STATUS_META: Record<"SUBMITTED" | "SEEN" | "FORWARDED" | "TEACHER_DECLINED", BadgeMeta> = {
  SUBMITTED: { label: "Đã gửi", icon: "send", tone: "primary" },
  SEEN: STATUS_META.SEEN,
  FORWARDED: { label: "Đã chuyển admin", icon: "check", tone: "success" },
  TEACHER_DECLINED: { label: "Giáo viên từ chối", icon: "alert", tone: "warning" },
};

/** The platform admin's answer to a suggestion; it replaces the status badge once there is one. */
export const SUGGESTION_DECISION_META: Record<"UNDER_REVIEW" | "ACCEPTED" | "DECLINED", BadgeMeta> = {
  UNDER_REVIEW: { label: "Đang xem xét", icon: "clock", tone: "warning" },
  ACCEPTED: { label: "Đã tiếp nhận", icon: "check", tone: "success" },
  DECLINED: { label: "Chưa phù hợp", icon: "x", tone: "neutral" },
};

export function badgeFor(event: HistoryEvent): BadgeMeta | null {
  if (!event.status) return null;
  if (event.type === SUGGESTION_EVENT && (event.status === "SUBMITTED" || event.status === "SEEN")) {
    return SUGGESTION_STATUS_META[event.status];
  }
  return STATUS_META[event.status];
}

export const EVENT_ICONS: Record<HistoryEventType, IconName> = {
  "discussion.create": "message",
  "discussion.edit": "edit",
  "discussion.delete": "x",
  "discussion.reply": "message",
  "discussion.decide": "check",
  "plan.confirmed": "check",
  "evaluation.feasibility": "clock",
  "evaluation.safety": "shield",
  "plan.submitted": "send",
  "teacher.decision": "school",
  "plan.version_created": "layers",
  "platform_agent_suggestion.created": "sparkles",
  "team.task_completed": "check",
  "team.document_uploaded": "file",
  "team.member_joined": "user",
  "team.leader_changed": "team",
};

export const AGENT_LABELS: Record<AgentId, string> = CORE_AGENT_LABELS;

export function actorFor(event: HistoryEvent): { icon: IconName; label: string } {
  const { actor } = event;
  switch (actor.kind) {
    case "self":
      return { icon: "user", label: `Bạn (${actor.name})` };
    case "member":
      return { icon: "team", label: `${actor.name} (thành viên nhóm)` };
    case "teacher":
      return { icon: "school", label: `${actor.name} (giáo viên)` };
    case "agent":
      return { icon: "sparkles", label: actor.agent_id ? `Agent ${AGENT_LABELS[actor.agent_id]}` : actor.name };
  }
}

/** Version line for plan events; null for team activity, which never has a version. */
export function versionLine(event: HistoryEvent): string | null {
  if (event.version === null) return null;
  const version = event.previous_version ? `v${event.previous_version} → v${event.version}` : `v${event.version}`;
  const parts = [version];
  if (event.coverage_percent !== null) parts.push(`đã kiểm tra ${event.coverage_percent}% khi gửi`);
  return parts.join(" · ");
}

const dateKeyFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: SCHOOL_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const timeFormat = new Intl.DateTimeFormat("vi-VN", { timeZone: SCHOOL_TIME_ZONE, hour: "2-digit", minute: "2-digit" });
const dayLabelFormat = new Intl.DateTimeFormat("vi-VN", {
  timeZone: SCHOOL_TIME_ZONE,
  weekday: "long",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/** YYYY-MM-DD of an instant in school time. */
export function schoolDateKey(instant: Date): string {
  return dateKeyFormat.format(instant);
}

export function shiftDateKey(dateKey: string, days: number): string {
  const [year, month, day] = dateKey.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day + days));
  return shifted.toISOString().slice(0, 10);
}

export function formatTime(isoDateTime: string): string {
  return timeFormat.format(new Date(isoDateTime));
}

export interface DateRange {
  from?: string;
  to?: string;
}

/** Inclusive range for a preset; "7 ngày qua" means today and the six days before it. */
export function presetRange(preset: Exclude<TimePreset, "custom">, today: string): DateRange {
  if (preset === "all") return {};
  const days = preset === "7d" ? 7 : 30;
  return { from: shiftDateKey(today, -(days - 1)), to: today };
}

export function customRangeError(range: DateRange): string | null {
  return range.from && range.to && range.from > range.to ? "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc." : null;
}

export interface HistoryDay {
  key: string;
  label: string;
  events: HistoryEvent[];
}

/** Group newest-first events by school day while keeping their order. */
export function groupEventsByDay(events: HistoryEvent[], today: string): HistoryDay[] {
  const days: HistoryDay[] = [];
  for (const event of events) {
    const instant = new Date(event.occurred_at);
    const key = schoolDateKey(instant);
    let day = days[days.length - 1];
    if (!day || day.key !== key) {
      const label = key === today ? "Hôm nay" : key === shiftDateKey(today, -1) ? "Hôm qua" : dayLabelFormat.format(instant);
      day = { key, label, events: [] };
      days.push(day);
    }
    day.events.push(event);
  }
  return days;
}
