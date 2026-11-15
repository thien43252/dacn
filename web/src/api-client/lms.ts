import { apiRequest, ApiError } from "./http";

const enc = encodeURIComponent;
const studentQuery = (studentId?: string) => studentId ? `?student_id=${enc(studentId)}` : "";

// --- Data Types ---

export type LessonStatus = "draft" | "published" | "archived";

export interface Lesson {
  id: string;
  class_id: string;
  title: string;
  description: string;
  lesson_date: string | null;
  position: number;
  status: LessonStatus;
  publish_at: string | null;
  locked: boolean;
  items: LessonItem[];
}

export type LessonItemKind = "file" | "video" | "link" | "text" | "assignment" | "quiz";

export interface LessonItem {
  id: string;
  lesson_id: string;
  class_id: string;
  kind: LessonItemKind;
  title: string;
  position: number;
  body: string;
  url?: string | null;
  embed_url?: string | null;
  file_id?: string | null;
  document_id?: string | null;
  visible: boolean;
  agent_readable?: boolean;
  quiz_id: string | null;
  assignment_id: string | null;
  viewed: boolean;
  file?: LmsFile | null;
}

export interface LessonDetail extends Lesson {
  items: LessonItem[];
}

export interface LessonInput {
  title: string;
  description?: string;
  lesson_date?: string | null;
  publish_at?: string | null;
}

export interface LessonItemInput {
  kind: LessonItemKind;
  title: string;
  body?: string;
  url?: string | null;
  file_id?: string | null;
}

export interface LessonItemPatch {
  title?: string;
  body?: string;
  url?: string | null;
  file_id?: string | null;
  visible?: boolean;
  agent_readable?: boolean;
}

export type ItemViewsResponse = Array<{
  student_id: string;
  name: string;
  viewed: boolean;
  first_viewed_at: string | null;
}>;

export interface LmsFile {
  id: string;
  purpose: "content" | "prompt" | "submission";
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string | null;
}

// --- Quizzes ---

export type QuizScoringPolicy = "best" | "last" | "average";
export type QuizShowMode = "on_submit" | "after_close" | "never";
export type QuestionKind = "single" | "multi" | "true_false" | "short" | "essay";

export interface QuestionOption {
  id: string;
  text: string;
}

export type AnswerValue = string | boolean | string[] | null;
export interface RubricCriterion {
  name: string;
  max_points: number;
  description: string;
}
export interface Rubric {
  criteria: RubricCriterion[];
  model_answer: string;
}
export interface QuestionInput {
  kind: QuestionKind;
  prompt: string;
  options: QuestionOption[];
  answer_key: AnswerValue;
  multi_scoring?: "all_or_nothing" | "partial";
  points: number;
  explanation: string;
  rubric: Rubric | null;
}
export interface QuizQuestion extends QuestionInput {
  id: string;
  position: number;
  source: string;
  affects_submitted: number;
}
export interface Quiz {
  open_at: string | null;
  close_at: string | null;
  duration_minutes: number | null;
  max_attempts: number;
  scoring_policy: QuizScoringPolicy;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  show_score: QuizShowMode;
  show_answers: QuizShowMode;
  block_agents: boolean;
  ai_grading: boolean;
  weight: number;
  counts_in_grade: boolean;
}
export interface QuizTeacherView extends Quiz {
  item_id: string;
  title: string;
  questions: QuizQuestion[];
}
export interface QuizStudentView extends Quiz {
  item_id: string;
  title: string;
  question_count: number;
  max_points: number;
  state: "upcoming" | "open" | "closed";
  attempts: AttemptView[];
}
export interface ServedQuestion {
  question_id: string;
  kind: QuestionKind;
  prompt: string;
  options: QuestionOption[];
  points: number;
  correct?: AnswerValue;
  explanation?: string;
}
export interface AttemptView {
  id: string;
  quiz_id: string;
  student_id: string;
  attempt_no: number;
  status: "in_progress" | "submitted" | "graded";
  started_at: string;
  deadline_at: string | null;
  submitted_at: string | null;
  submit_reason: string | null;
  server_now: string;
  questions: ServedQuestion[];
  answers: Record<string, AnswerValue>;
  max_score: number;
}
export interface AttemptDetailView extends AttemptView {
  score?: number | null;
  item_scores?: Record<string, { points: number; graded_by: string; feedback?: string }> | null;
}
export type AttemptSubmitResult = AttemptDetailView;
export interface QuizResultsView {
  attempts: Array<AttemptDetailView & { student_name: string }>;
  stats: {
    attempted_students: number;
    average: number | null;
    distribution: Record<string, number>;
    per_question: Array<{ question_id: string; correct_rate: number | null }>;
  };
}
export type QuizCopyResult = QuizTeacherView;

// --- Assignments ---

export interface Assignment {
  item_id: string;
  prompt: string;
  prompt_file_ids?: string[];
  due_at?: string | null;
  max_points: number;
  allow_late: boolean;
  late_penalty_per_day_pct: number;
  late_penalty_max_pct: number;
  rubric: Rubric | null;
  ai_grading: boolean;
  weight: number;
  counts_in_grade: boolean;
}

export interface AssignmentExtension {
  effective_due: string | null;
}
export interface SubmissionVersion {
  version_no: number;
  text: string;
  file_ids: string[];
  submitted_at: string;
  is_late: boolean;
}
export interface SubmissionListItem {
  student_id: string;
  name: string;
  submission_id: string | null;
  state: "missing" | "submitted" | "late" | "graded" | "returned";
  effective_due: string | null;
  submitted_at: string | null;
}
export interface GradeResult {
  raw_score?: number | null;
  penalty: number;
  final_score?: number | null;
  feedback: string;
  penalty_waived: boolean;
}
export interface SubmissionDetail {
  id: string;
  assignment_id: string;
  student_id: string;
  status: "submitted" | "graded" | "returned";
  latest_version: number;
  is_late: boolean;
  days_late: number;
  returned_at?: string | null;
  versions: SubmissionVersion[];
  result?: GradeResult;
}
export interface SubmissionTeacherView extends SubmissionDetail, GradeResult {}
export interface AssignmentTeacherView extends Assignment {
  submissions: SubmissionListItem[];
  stats: Record<"submitted" | "late" | "missing" | "graded" | "returned", number>;
}
export interface AssignmentStudentView extends Assignment {
  effective_due: string | null;
  submission: SubmissionDetail | null;
}

// --- AI Assistant ---

export interface AssistAgent {
  slug: string;
  name: string;
  agent_id: string;
}
export type QuestionLevel = "nhan_biet" | "thong_hieu" | "van_dung" | "van_dung_cao" | "hon_hop";
export interface GradingPayload {
  points: number;
  feedback: string;
  criteria?: Array<{ name: string; points: number; reason: string }>;
}
export interface AISuggestion {
  id: string;
  kind: "questions" | "grading";
  target_type: "quiz" | "submission" | "attempt_question";
  target_id: string;
  agent_id: string | null;
  status: "pending" | "ready" | "failed" | "skipped_consent" | "approved" | "edited" | "discarded";
  payload: { questions?: Array<QuestionInput & { source: string }> } & Partial<GradingPayload> | null;
  final: Record<string, unknown> | null;
  error: string | null;
}
export interface SuggestionReviewInput {
  decisions?: Array<{ index: number; action: "approve" | "edit" | "discard"; question?: QuestionInput }>;
  action?: "approve" | "edit" | "discard";
  points?: number;
  feedback?: string;
}

// --- Gradebook, Todo, Notifications, Grade Audit ---

export interface GradebookColumn {
  item_id: string;
  kind: "quiz" | "assignment";
  title: string;
  max_points: number;
  weight: number;
  counts: boolean;
  counts_in_grade: boolean;
  lesson_title: string;
  archived: boolean;
}

export interface GradebookCell {
  item_id: string;
  state: "open" | "not_assigned" | "missing" | "in_progress" | "pending" | "graded" | "returned";
  score?: number | null;
  final?: number | null;
}

export interface GradebookRow {
  student: {
    id: string;
    name: string;
  };
  cells: GradebookCell[];
  average?: number | null;
}

export interface Gradebook {
  columns: GradebookColumn[];
  rows: GradebookRow[];
}

export interface MyGrades {
  student_id: string;
  items: Array<{
    item_id: string;
    kind: "quiz" | "assignment";
    title: string;
    max_points: number;
    score?: number | null;
    returned_at?: string | null;
  }>;
  overall_average?: number | null;
}

export interface TodoItem {
  class_id: string;
  class_name: string;
  item_id: string;
  kind: "quiz" | "assignment";
  title: string;
  due_at?: string | null;
  status: "open" | "missing" | "in_progress";
  state: "open" | "missing" | "in_progress";
  link: string;
}

export interface NotificationItem {
  id: string;
  kind: "lesson_published" | "assigned" | "due_soon" | "returned" | "to_grade" | "ai_ready";
  class_id?: string | null;
  title: string;
  link: string;
  read_at?: string | null;
  created_at: string | null;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

export interface GradeAuditLog {
  id: string;
  class_id: string;
  actor_id: string;
  actor_name?: string;
  action: "grade" | "regrade" | "edit_score" | "waive_penalty" | "extend" | "return" | "delete_submission" | "ai_approve";
  target_type: string;
  target_id: string;
  student_id?: string | null;
  student_name?: string | null;
  before?: unknown;
  after?: unknown;
  created_at: string;
}

// --- File URL Helper ---

export function fileUrl(classId: string, fileId: string, download = false): string {
  return `/api/classes/${enc(classId)}/files/${enc(fileId)}${download ? "?download=1" : ""}`;
}

// --- Upload File With Progress ---

export function uploadFile(
  classId: string,
  file: File,
  purpose: "content" | "prompt" | "submission",
  onProgress?: (percent: number) => void,
): Promise<LmsFile> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/classes/${enc(classId)}/files`);
    xhr.withCredentials = true;

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      let data: { detail?: string } & LmsFile = {} as LmsFile;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // Non-JSON response
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else {
        reject(new ApiError(typeof data.detail === "string" ? data.detail : "Tải tệp lên thất bại.", xhr.status));
      }
    };

    xhr.onerror = () => {
      reject(new ApiError("Không kết nối được máy chủ. Vui lòng thử lại.", 0));
    };

    const formData = new FormData();
    formData.append("file", file);
    formData.append("purpose", purpose);
    xhr.send(formData);
  });
}

// --- API Client ---

export const lmsApi = {
  lessons: {
    list: (classId: string, studentId?: string) => apiRequest<Lesson[]>(`/api/classes/${enc(classId)}/lessons${studentQuery(studentId)}`),
    create: (classId: string, input: LessonInput) =>
      apiRequest<Lesson>(`/api/classes/${enc(classId)}/lessons`, { method: "POST", body: input }),
    get: (classId: string, lessonId: string, studentId?: string) =>
      apiRequest<LessonDetail>(`/api/classes/${enc(classId)}/lessons/${enc(lessonId)}${studentQuery(studentId)}`),
    update: (classId: string, lessonId: string, patch: Partial<LessonInput> & { status?: LessonStatus }) =>
      apiRequest<Lesson>(`/api/classes/${enc(classId)}/lessons/${enc(lessonId)}`, { method: "PATCH", body: patch }),
    delete: (classId: string, lessonId: string) =>
      apiRequest<void>(`/api/classes/${enc(classId)}/lessons/${enc(lessonId)}`, { method: "DELETE" }),
    reorder: (classId: string, ids: string[]) =>
      apiRequest<void>(`/api/classes/${enc(classId)}/lessons/order`, { method: "PUT", body: { ids } }),
  },

  items: {
    create: (classId: string, lessonId: string, input: LessonItemInput) =>
      apiRequest<LessonItem>(`/api/classes/${enc(classId)}/lessons/${enc(lessonId)}/items`, { method: "POST", body: input }),
    update: (classId: string, itemId: string, patch: LessonItemPatch) =>
      apiRequest<LessonItem>(`/api/classes/${enc(classId)}/items/${enc(itemId)}`, { method: "PATCH", body: patch }),
    delete: (classId: string, itemId: string) =>
      apiRequest<void>(`/api/classes/${enc(classId)}/items/${enc(itemId)}`, { method: "DELETE" }),
    reorder: (classId: string, lessonId: string, ids: string[]) =>
      apiRequest<void>(`/api/classes/${enc(classId)}/lessons/${enc(lessonId)}/items/order`, { method: "PUT", body: { ids } }),
    recordView: (classId: string, itemId: string) =>
      apiRequest<void>(`/api/classes/${enc(classId)}/items/${enc(itemId)}/view`, { method: "POST" }),
    getViews: (classId: string, itemId: string) =>
      apiRequest<ItemViewsResponse>(`/api/classes/${enc(classId)}/items/${enc(itemId)}/views`),
  },

  files: {
    upload: uploadFile,
    url: fileUrl,
  },

  quizzes: {
    get: (classId: string, quizId: string, studentId?: string) =>
      apiRequest<QuizTeacherView | QuizStudentView>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}${studentQuery(studentId)}`),
    update: (classId: string, quizId: string, patch: Partial<Quiz>) =>
      apiRequest<QuizTeacherView>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}`, { method: "PATCH", body: patch }),
    addQuestion: (classId: string, quizId: string, question: QuestionInput) =>
      apiRequest<QuizQuestion>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/questions`, { method: "POST", body: question }),
    reorderQuestions: (classId: string, quizId: string, ids: string[]) =>
      apiRequest<{ ids: string[] }>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/questions/order`, { method: "PUT", body: { ids } }),
    results: (classId: string, quizId: string) =>
      apiRequest<QuizResultsView>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/results`),
    copy: (classId: string, quizId: string, targetLessonId: string) =>
      apiRequest<QuizCopyResult>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/copy`, {
        method: "POST",
        body: { target_lesson_id: targetLessonId },
      }),
    startAttempt: (classId: string, quizId: string) =>
      apiRequest<AttemptView>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/attempts`, { method: "POST" }),
  },

  questions: {
    update: (classId: string, questionId: string, patch: Partial<QuestionInput>) =>
      apiRequest<QuizQuestion & { affects_submitted?: number }>(`/api/classes/${enc(classId)}/questions/${enc(questionId)}`, {
        method: "PATCH",
        body: patch,
      }),
    delete: (classId: string, questionId: string) =>
      apiRequest<{ affects_submitted?: number }>(`/api/classes/${enc(classId)}/questions/${enc(questionId)}`, { method: "DELETE" }),
    regrade: (classId: string, questionId: string) =>
      apiRequest<{ updated: number }>(`/api/classes/${enc(classId)}/questions/${enc(questionId)}/regrade`, { method: "POST" }),
  },

  attempts: {
    get: (classId: string, attemptId: string) =>
      apiRequest<AttemptDetailView>(`/api/classes/${enc(classId)}/attempts/${enc(attemptId)}`),
    saveAnswer: (classId: string, attemptId: string, questionId: string, value: AnswerValue) =>
      apiRequest<{ saved_at: string }>(`/api/classes/${enc(classId)}/attempts/${enc(attemptId)}/answers`, {
        method: "PUT",
        body: { question_id: questionId, value },
      }),
    submit: (classId: string, attemptId: string) =>
      apiRequest<AttemptSubmitResult>(`/api/classes/${enc(classId)}/attempts/${enc(attemptId)}/submit`, { method: "POST" }),
    gradeQuestion: (classId: string, attemptId: string, questionId: string, points: number, feedback?: string) =>
      apiRequest<AttemptDetailView>(`/api/classes/${enc(classId)}/attempts/${enc(attemptId)}/scores/${enc(questionId)}`, {
        method: "PUT",
        body: { points, feedback },
      }),
  },

  assignments: {
    get: (classId: string, assignmentId: string, studentId?: string) =>
      apiRequest<AssignmentTeacherView | AssignmentStudentView>(
        `/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}${studentId ? `?student_id=${enc(studentId)}` : ""}`,
      ),
    update: (classId: string, assignmentId: string, patch: Partial<Assignment>) =>
      apiRequest<Omit<Assignment, "item_id">>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}`, { method: "PATCH", body: patch }),
    setExtension: (classId: string, assignmentId: string, studentId: string, dueAt: string) =>
      apiRequest<AssignmentExtension>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}/extensions/${enc(studentId)}`, {
        method: "PUT",
        body: { due_at: dueAt },
      }),
    deleteExtension: (classId: string, assignmentId: string, studentId: string) =>
      apiRequest<AssignmentExtension>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}/extensions/${enc(studentId)}`, {
        method: "DELETE",
      }),
    submit: (classId: string, assignmentId: string, input: { text?: string; file_ids?: string[] }) =>
      apiRequest<SubmissionDetail>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}/submissions`, {
        method: "POST",
        body: input,
      }),
    listSubmissions: (classId: string, assignmentId: string) =>
      apiRequest<SubmissionListItem[]>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}/submissions`),
    returnSubmissions: (classId: string, assignmentId: string, submissionIds?: string[]) =>
      apiRequest<{ returned: number }>(`/api/classes/${enc(classId)}/assignments/${enc(assignmentId)}/return`, {
        method: "POST",
        body: { submission_ids: submissionIds },
      }),
  },

  submissions: {
    get: (classId: string, submissionId: string) =>
      apiRequest<SubmissionTeacherView | SubmissionDetail>(`/api/classes/${enc(classId)}/submissions/${enc(submissionId)}`),
    grade: (classId: string, submissionId: string, grade: { raw_score: number; feedback?: string; penalty_waived?: boolean }) =>
      apiRequest<SubmissionTeacherView>(`/api/classes/${enc(classId)}/submissions/${enc(submissionId)}/grade`, {
        method: "PUT",
        body: grade,
      }),
  },

  assist: {
    agents: (classId: string, capability?: "questions" | "grading") =>
      apiRequest<AssistAgent[]>(`/api/classes/${enc(classId)}/assist/agents${capability ? `?capability=${enc(capability)}` : ""}`),
    suggestQuestions: (
      classId: string,
      quizId: string,
      params: { agent_slug?: string; count: number; kinds: QuestionKind[]; level: QuestionLevel; document_ids?: string[] },
    ) =>
      apiRequest<AISuggestion>(`/api/classes/${enc(classId)}/quizzes/${enc(quizId)}/suggest-questions`, {
        method: "POST",
        body: params,
      }),
    suggestGrading: (
      classId: string,
      targets: Array<{ type: "submission" | "attempt_question"; id: string }>,
      agentSlug?: string,
    ) =>
      apiRequest<AISuggestion[]>(`/api/classes/${enc(classId)}/suggest-grading`, {
        method: "POST",
        body: { targets, agent_slug: agentSlug },
      }),
    getSuggestion: (classId: string, suggestionId: string) =>
      apiRequest<AISuggestion>(`/api/classes/${enc(classId)}/suggestions/${enc(suggestionId)}`),
    reviewSuggestion: (classId: string, suggestionId: string, review: SuggestionReviewInput) =>
      apiRequest<AISuggestion>(`/api/classes/${enc(classId)}/suggestions/${enc(suggestionId)}/review`, {
        method: "POST",
        body: review,
      }),
  },

  gradebook: {
    get: (classId: string) => apiRequest<Gradebook>(`/api/classes/${enc(classId)}/gradebook`),
    updateColumn: (classId: string, itemId: string, patch: { weight?: number; counts_in_grade?: boolean }) =>
      apiRequest<{ item_id: string; weight: number; counts_in_grade: boolean }>(`/api/classes/${enc(classId)}/gradebook/columns/${enc(itemId)}`, { method: "PATCH", body: patch }),
    csvUrl: (classId: string) => `/api/classes/${enc(classId)}/gradebook.csv`,
  },

  myGrades: {
    get: (classId: string, studentId?: string) =>
      apiRequest<MyGrades>(`/api/classes/${enc(classId)}/my-grades${studentId ? `?student_id=${enc(studentId)}` : ""}`),
  },

  todo: {
    list: (studentId?: string) => apiRequest<TodoItem[]>(`/api/todo${studentId ? `?student_id=${enc(studentId)}` : ""}`),
  },

  notifications: {
    list: (unreadOnly = false) =>
      apiRequest<NotificationList>(`/api/notifications${unreadOnly ? "?unread=1" : ""}`),
    markRead: (ids?: string[]) =>
      apiRequest<NotificationList>("/api/notifications/read", { method: "POST", body: { ids } }),
  },

  gradeAudit: {
    list: (classId: string, params?: { student_id?: string; target_id?: string }) => {
      const q = new URLSearchParams();
      if (params?.student_id) q.set("student_id", params.student_id);
      if (params?.target_id) q.set("target_id", params.target_id);
      const qs = q.toString();
      return apiRequest<GradeAuditLog[]>(`/api/classes/${enc(classId)}/grade-audit${qs ? `?${qs}` : ""}`);
    },
  },
};
