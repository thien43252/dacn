import { apiRequest } from "./http";
import type { Announcement, AnnouncementInput, Assignment, Child, ClassInput, ClassPolicy, ClassRoom, Consent, LearningReport, LinkCode, Member, ProgressRow } from "./types";

const enc = encodeURIComponent;

export const classesApi = {
  list: () => apiRequest<ClassRoom[]>("/api/classes"),
  get: (id: string) => apiRequest<ClassRoom>(`/api/classes/${enc(id)}`),
  create: (input: ClassInput) => apiRequest<ClassRoom>("/api/classes", { method: "POST", body: input }),
  update: (id: string, patch: Partial<ClassInput> & { archived?: boolean }) =>
    apiRequest<ClassRoom>(`/api/classes/${enc(id)}`, { method: "PATCH", body: patch }),
  rotateCode: (id: string) => apiRequest<ClassRoom>(`/api/classes/${enc(id)}/join-code`, { method: "POST" }),
  join: (code: string) => apiRequest<ClassRoom>("/api/classes/join", { method: "POST", body: { code } }),

  members: (id: string) => apiRequest<Member[]>(`/api/classes/${enc(id)}/members`),
  addMember: (id: string, email: string) =>
    apiRequest<Member[]>(`/api/classes/${enc(id)}/members`, { method: "POST", body: { email } }),
  removeMember: (id: string, userId: string) =>
    apiRequest<void>(`/api/classes/${enc(id)}/members/${enc(userId)}`, { method: "DELETE" }),
  linkParent: (id: string, studentId: string, parentEmail: string) =>
    apiRequest<Member[]>(`/api/classes/${enc(id)}/parents`, {
      method: "POST",
      body: { student_id: studentId, parent_email: parentEmail },
    }),

  policy: (id: string) => apiRequest<ClassPolicy>(`/api/classes/${enc(id)}/policy`),
  savePolicy: (id: string, policy: ClassPolicy) =>
    apiRequest<ClassPolicy>(`/api/classes/${enc(id)}/policy`, { method: "PUT", body: policy }),
};

export const familyApi = {
  myLinkCode: () => apiRequest<LinkCode>("/api/me/link-code"),
  children: () => apiRequest<Child[]>("/api/parent/children"),
  linkChild: (code: string) => apiRequest<Child[]>("/api/parent/children", { method: "POST", body: { code } }),
  setConsent: (studentId: string, consent: Pick<Consent, "allow_agents" | "allow_progress_reports">) =>
    apiRequest<Consent>(`/api/parent/children/${enc(studentId)}/consent`, { method: "PUT", body: consent }),
};

export const reportsApi = {
  child: (studentId: string, days: number) =>
    apiRequest<LearningReport>(`/api/parent/children/${enc(studentId)}/report?days=${days}`),
  classProgress: (classId: string, days: number) => apiRequest<ProgressRow[]>(`/api/classes/${enc(classId)}/progress?days=${days}`),
  student: (classId: string, studentId: string, days: number) =>
    apiRequest<LearningReport>(`/api/classes/${enc(classId)}/students/${enc(studentId)}/report?days=${days}`),
};

/** Class announcements and assigned practice (feature 002). */
export const feedApi = {
  announcements: (classId: string) => apiRequest<Announcement[]>(`/api/classes/${enc(classId)}/announcements`),
  postAnnouncement: (classId: string, input: AnnouncementInput) =>
    apiRequest<Announcement>(`/api/classes/${enc(classId)}/announcements`, { method: "POST", body: input }),
  deleteAnnouncement: (classId: string, id: string) =>
    apiRequest<void>(`/api/classes/${enc(classId)}/announcements/${enc(id)}`, { method: "DELETE" }),
  assignments: (classId: string) => apiRequest<Assignment[]>(`/api/classes/${enc(classId)}/assignments`),
  assignment: (classId: string, id: string) => apiRequest<Assignment>(`/api/classes/${enc(classId)}/assignments/${enc(id)}`),
  deleteAssignment: (classId: string, id: string) =>
    apiRequest<void>(`/api/classes/${enc(classId)}/assignments/${enc(id)}`, { method: "DELETE" }),
};
