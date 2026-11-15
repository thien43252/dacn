import { apiRequest } from "./http";
import type {
  ApprovalCard,
  ApprovalSettings,
  ConversationListItem,
  GroupCandidates,
  GroupMember,
  PersonRequest,
  StoredMessage,
} from "./types";

const enc = encodeURIComponent;

/** Messenger-style conversations, groups and the per-conversation event stream (contracts/rest-api.md). */
export const conversationsApi = {
  all: (q = "") => apiRequest<ConversationListItem[]>(`/api/chat/conversations?all=true${q ? `&q=${enc(q)}` : ""}`),
  get: (id: string) => apiRequest<ConversationListItem>(`/api/chat/conversations/${enc(id)}`),
  messages: (id: string) => apiRequest<StoredMessage[]>(`/api/chat/conversations/${enc(id)}/messages`),
  openDirect: (classId: string | null, agent: string | null) =>
    apiRequest<ConversationListItem>("/api/chat/direct", { method: "POST", body: { class_id: classId, agent } }),
  restartDirect: (id: string) => apiRequest<ConversationListItem>(`/api/chat/direct/${enc(id)}/restart`, { method: "POST" }),
  markRead: (id: string, seq: number) =>
    apiRequest<void>(`/api/chat/conversations/${enc(id)}/read`, { method: "POST", body: { seq } }),
  eventsUrl: (id: string, after: number) => `/api/chat/conversations/${enc(id)}/events?after=${after}`,
};

export const groupsApi = {
  candidates: (classId: string) => apiRequest<GroupCandidates>(`/api/chat/groups/candidates?class_id=${enc(classId)}`),
  groupCandidates: (groupId: string) => apiRequest<GroupCandidates>(`/api/chat/groups/${enc(groupId)}/candidates`),
  create: (body: { class_id: string; title: string; members: string[]; agents: string[]; default_agent?: string | null }) =>
    apiRequest<ConversationListItem>("/api/chat/groups", { method: "POST", body }),
  update: (groupId: string, body: { title?: string; default_agent?: string }) =>
    apiRequest<ConversationListItem>(`/api/chat/groups/${enc(groupId)}`, { method: "PATCH", body }),
  members: (groupId: string) => apiRequest<GroupMember[]>(`/api/chat/groups/${enc(groupId)}/members`),
  addMembers: (groupId: string, body: { users?: string[]; agents?: string[]; can_see_history?: boolean }) =>
    apiRequest<GroupMember[]>(`/api/chat/groups/${enc(groupId)}/members`, { method: "POST", body }),
  removeMember: (groupId: string, memberId: string) =>
    apiRequest<void>(`/api/chat/groups/${enc(groupId)}/members/${enc(memberId)}`, { method: "DELETE" }),
};

export const inboxApi = {
  list: (status = "open") => apiRequest<PersonRequest[]>(`/api/inbox?status=${enc(status)}`),
  count: () => apiRequest<{ open: number }>("/api/inbox/count"),
  answer: (id: string, body: { choice?: string; text?: string }) =>
    apiRequest<PersonRequest>(`/api/person-requests/${enc(id)}/answer`, { method: "POST", body }),
  cancel: (id: string) => apiRequest<PersonRequest>(`/api/person-requests/${enc(id)}/cancel`, { method: "POST" }),
};

export const approvalsApi = {
  answer: (cardId: string, choice: string, recipientId?: string) =>
    apiRequest<ApprovalCard>(`/api/approvals/${enc(cardId)}/answer`, {
      method: "POST",
      body: { choice, recipient_id: recipientId ?? null },
    }),
  settings: () => apiRequest<ApprovalSettings>("/api/settings/approvals"),
  setVigilant: (extra_vigilant: boolean) =>
    apiRequest<ApprovalSettings>("/api/settings/approvals", { method: "PATCH", body: { extra_vigilant } }),
  removeRule: (ruleId: string) => apiRequest<void>(`/api/settings/approvals/rules/${enc(ruleId)}`, { method: "DELETE" }),
};
