/** Shapes returned by the EduAgent Hub backend (the schemas.py of each backend/app module). Keep in sync by hand. */

export type ClassRole = "teacher" | "student" | "parent";

export type SubjectCode = "toan" | "van" | "anh" | "ly" | "hoa" | "sinh" | "su" | "dia" | "gdcd" | "tin" | "khac";

export const SUBJECT_LABELS: Record<SubjectCode, string> = {
  toan: "Toán",
  van: "Ngữ văn",
  anh: "Tiếng Anh",
  ly: "Vật lý",
  hoa: "Hoá học",
  sinh: "Sinh học",
  su: "Lịch sử",
  dia: "Địa lý",
  gdcd: "GDCD",
  tin: "Tin học",
  khac: "Khác",
};

export function subjectLabel(code: string): string {
  return SUBJECT_LABELS[code as SubjectCode] ?? code;
}

export interface ClassRoom {
  id: string;
  name: string;
  subject: SubjectCode;
  grade: number;
  description: string;
  teacher_name: string;
  my_role: ClassRole;
  student_count: number;
  require_parent_consent: boolean;
  archived: boolean;
  created_at: string;
  join_code: string | null;
  children: string[];
}

export interface ClassInput {
  name: string;
  subject: SubjectCode;
  grade: number;
  description: string;
  require_parent_consent: boolean;
}

export interface Person {
  id: string;
  name: string;
  email: string;
}

export interface Member {
  user_id: string;
  name: string;
  email: string;
  role: "teacher" | "student";
  joined_at: string;
  parents: Person[];
  can_use_agents: boolean;
}

export interface ClassPolicy {
  no_direct_answers: boolean;
  allowed_subjects: string[];
  allow_personal_agents: boolean;
  notes_for_agents: string;
  /** Xử lý nhiều bước (feature 002, FR-046); older backends omit it, which means on. */
  multi_step?: boolean;
}

export interface Consent {
  allow_agents: boolean;
  allow_progress_reports: boolean;
  updated_at: string | null;
}

export interface Child {
  id: string;
  name: string;
  email: string;
  classes: { id: string; name: string; subject: string; grade: number; teacher_name: string }[];
  consent: Consent;
}

export interface LinkCode {
  code: string;
  parents: Person[];
}

export type AgentRole = "teacher" | "student" | "parent";
export type CertificationStatus = "uncertified" | "pending" | "certified" | "needs_review" | "rejected";

export const CERTIFICATION_LABELS: Record<CertificationStatus, string> = {
  uncertified: "Chưa kiểm định",
  pending: "Đang kiểm định",
  certified: "Đã kiểm định",
  needs_review: "Cần xem lại",
  rejected: "Không đạt",
};

export interface ChatAgent {
  slug: string;
  name: string;
  description: string;
  avatar: string;
  source: "platform" | "class" | "personal" | "sandbox";
  certification_status: CertificationStatus;
  starter_prompts: string[];
}

export interface ConversationSummary {
  id: string;
  class_id: string | null;
  title: string;
  updated_at: string;
}

/** A class document passage the agent used (class_doc_search), shown under its reply. */
export interface Citation {
  document_id: string;
  title: string;
  location: string;
  excerpt: string;
}

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent_slug: string | null;
  /** `awaiting_user`: a clarifying question or a confirmation request (feature 002). */
  status: "ok" | "blocked" | "error" | "awaiting_user";
  created_at: string;
  meta: {
    tools?: { name: string; status: string }[];
    route_reason?: string;
    guard?: { stage: string; verdict: string; category: string }[];
    citations?: Citation[];
    suggestions?: string[];
    /** Feature 002 (specs/002-multi-agent-orchestration/data-model.md, `chat_messages.meta`). */
    path?: ChatPath;
    run_id?: string;
    contributors?: AgentRef[];
    process?: ProcessSummary;
    assumptions?: string[];
    ask?: StoredAsk;
    /** On the user's message that answered a question. */
    reply_to?: { run_id: string; ask_message_id: string };
  };
}

// ---- Multi-step orchestration (specs/002-multi-agent-orchestration/contracts/chat-sse.md) ----

export type ChatPath = "fast" | "full";
export type StepStatus = "pending" | "running" | "done" | "error" | "blocked" | "skipped";

export interface AgentRef {
  slug: string;
  name: string;
  avatar: string;
}

export interface PlanStep {
  key: string;
  title: string;
  agent: AgentRef;
  depends_on: string[];
  status: StepStatus;
}

/** `plan`: sent whenever the plan is made, resumed or redone; the client replaces its whole step list. */
export interface PlanEvent {
  type: "plan";
  message_id: string;
  run_id: string;
  goal: string;
  lead: AgentRef;
  steps: PlanStep[];
  resumed: boolean;
}

/** `step`: one step changed; `analyze` and `synthesis` are the special keys. */
export interface StepEvent {
  type: "step";
  message_id: string;
  key: string;
  status: StepStatus;
  title?: string;
  agent?: AgentRef;
  duration_ms?: number;
}

export interface AskQuestion {
  id: string;
  question: string;
  options: string[];
}

export interface ConfirmPreview {
  title?: string;
  body?: string;
  items?: string[];
  before?: string;
  after?: string;
}

export interface AskConfirm {
  tool: string;
  summary: string;
  impact?: string;
  audience_count?: number;
  preview?: ConfirmPreview;
}

/** `ask`: always right before `done(status="awaiting_user")`; `message_id` is the question message. */
export interface AskEvent {
  type: "ask";
  message_id: string;
  run_id: string;
  kind: "clarify" | "confirm";
  agent: AgentRef;
  intro: string;
  questions?: AskQuestion[];
  confirm?: AskConfirm;
  skippable: boolean;
}

export type AskState = "open" | "answered" | "skipped" | "approved" | "rejected" | "expired" | "cancelled";

export interface StoredAsk {
  run_id: string;
  kind: "clarify" | "confirm";
  questions?: AskQuestion[];
  confirm?: AskConfirm;
  state: AskState;
  answers?: Record<string, string>;
}

export interface ProcessSummary {
  duration_ms: number;
  agents: number;
  steps: { key: string; title: string; agent: string; status: StepStatus }[];
}

/** `reply` of POST /api/chat/stream: an answer to the pending question of `run_id`. */
export interface ChatReply {
  run_id: string;
  answers?: Record<string, string>;
  skip_all?: boolean;
  decision?: "approve" | "reject" | null;
}

/** Extra fields of `done` on the full path. */
export interface DoneExtras {
  path?: ChatPath;
  contributors?: AgentRef[];
}

export interface AgentManifest {
  slug: string;
  name: string;
  description: string;
  avatar: string;
  subjects: string[];
  grades: number[];
  target_roles: AgentRole[];
  age_range?: [number, number] | null;
  capabilities: string[];
  tools: string[];
  knowledge: "class_documents" | "none";
  system_prompt: string;
  examples: { user: string; assistant: string }[];
  starter_prompts: string[];
}

export interface HubAgent {
  id: string;
  slug: string;
  name: string;
  description: string;
  avatar: string;
  subjects: string[];
  grades: number[];
  target_roles: AgentRole[];
  tools: string[];
  knowledge: string;
  capabilities: string[];
  is_platform: boolean;
  author: string;
  version: number;
  version_id: string;
  certification_status: CertificationStatus;
  install_count: number;
  updated_at: string;
}

export interface AgentDetail extends HubAgent {
  manifest: AgentManifest;
  visibility: "private" | "public";
  is_mine: boolean;
  forked_from_id: string | null;
  draft_manifest: AgentManifest | null;
  versions: { id: string; version: number; certification_status: CertificationStatus; created_at: string }[];
  certification: CertificationSummary | null;
}

export interface CategoryTally {
  pass: number;
  fail: number;
  unjudged: number;
}

/** Public summary of the latest finished certification of the version shown on the Hub. */
export interface CertificationSummary {
  id: string;
  status: CertificationStatus;
  score: number | null;
  cases: number;
  by_category: Record<string, CategoryTally>;
  finished_at: string;
}

export type CertificationRunStatus = "running" | "certified" | "needs_review" | "rejected" | "failed";

export interface Certification {
  id: string;
  agent_id: string;
  agent_slug: string;
  agent_name: string;
  author: string;
  version_id: string;
  version: number;
  status: CertificationRunStatus;
  score: number | null;
  publish: boolean;
  progress: { done?: number; total?: number };
  reasons: string[];
  review_note: string;
  created_at: string;
  finished_at: string | null;
}

export interface StaticFinding {
  id: string;
  title: string;
  ok: boolean;
  severity: "error" | "warning";
  detail: string;
}

export interface CertificationCase {
  id: string;
  kind: "redteam" | "benign";
  category: string;
  expected: "block" | "safe_response" | "allow";
  role: AgentRole;
  prompt: string;
  reply: string;
  tools: string[];
  outcome: "pass" | "fail" | "unjudged";
  reason: string;
}

export interface CertificationDetail extends Certification {
  report: {
    static?: StaticFinding[];
    manifest_review?: { risk: "low" | "medium" | "high"; issues: string[] } | null;
    cases?: CertificationCase[];
    by_category?: Record<string, CategoryTally>;
    decision?: { status: string; reasons: string[] };
    settings?: { guard_mode: string; provider: string; agent_model: string; judge_model: string };
    duration_s?: number;
    error?: string;
  };
}

export interface GuardEvent {
  id: string;
  created_at: string;
  source: "chat" | "sandbox" | "certify";
  class_id: string | null;
  class_name: string | null;
  user_name: string | null;
  role: string;
  agent_slug: string | null;
  stage: "input" | "tool" | "output";
  verdict: "block" | "support" | "redact" | "flag";
  category: string;
  detector: "rule" | "policy" | "llm";
  severity: "low" | "medium" | "high";
  reason: string;
  excerpt: string;
}

export interface AuditLog {
  summary: {
    days: number;
    total: number;
    by_verdict: Record<string, number>;
    by_category: Record<string, number>;
    by_stage: Record<string, number>;
    high_severity: number;
  };
  events: GuardEvent[];
}

export interface UsageRow {
  key: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
}

export interface UsageReport {
  days: number;
  total: UsageRow;
  by_purpose: UsageRow[];
  /** fast · full · other (feature 002); older backends omit it. */
  by_path?: UsageRow[];
  by_model: UsageRow[];
  by_day: UsageRow[];
}

/** Vietnamese names for guard and certification categories (eval/README.md lists the red-team ones). */
export const CATEGORY_LABELS: Record<string, string> = {
  academic_integrity: "Làm hộ bài",
  jailbreak: "Vượt quy tắc",
  pii: "Thông tin cá nhân",
  prompt_injection: "Chỉ dẫn nhúng",
  age_inappropriate: "Không hợp lứa tuổi",
  harassment: "Bắt nạt, miệt thị",
  dangerous_illegal: "Nguy hiểm, phạm pháp",
  self_harm: "Tự làm hại",
  role_boundary: "Vượt quyền vai trò",
  misinformation: "Tin sai lệch",
  benign: "Câu hỏi hợp lệ",
  class_policy: "Chính sách lớp",
  tool_denied: "Công cụ bị từ chối",
  prompt_leak: "Lộ hướng dẫn hệ thống",
};

export function categoryLabel(code: string): string {
  return CATEGORY_LABELS[code] ?? (code || "Khác");
}

export interface Installation {
  id: string;
  scope: "class" | "personal";
  enabled: boolean;
  agent: HubAgent;
  created_at: string;
}

export interface PlatformTool {
  name: string;
  title: string;
  description: string;
  roles: AgentRole[];
  needs_class: boolean;
  parameters: { properties?: Record<string, { description?: string; type?: string }> };
}

export interface ClassDocument {
  id: string;
  title: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  error: string | null;
  chunk_count: number;
  created_at: string;
}

export const ROLE_LABELS: Record<AgentRole, string> = { teacher: "Giáo viên", student: "Học sinh", parent: "Phụ huynh" };

export interface Activity {
  period_days: number;
  questions_asked: number;
  active_days: number;
  daily: { date: string; questions: number }[];
  agents_used: Record<string, number>;
  subjects: Record<string, number>;
  frequent_keywords: string[];
  blocked_messages: number;
  wellbeing_alerts: number;
  last_active: string | null;
}

export interface LearningReport {
  student_id: string;
  student_name: string;
  activity: Activity;
  narrative: { summary: string; highlights: string[]; suggestions: string[]; generated_by: "llm" | "template" };
  generated_at: string;
}

export interface ProgressRow {
  student_id: string;
  student_name: string;
  activity: Activity;
}
