import { apiRequest } from "./http";
import type {
  AgentDetail,
  AgentManifest,
  ChatAgent,
  ClassDocument,
  ConversationSummary,
  HubAgent,
  Installation,
  PlatformTool,
  StoredMessage,
} from "./types";

const enc = encodeURIComponent;

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const chatApi = {
  agents: (classId: string | null) => apiRequest<ChatAgent[]>(`/api/chat/agents${query({ class_id: classId })}`),
  conversations: (classId: string | null) =>
    apiRequest<ConversationSummary[]>(`/api/chat/conversations${query({ class_id: classId })}`),
  messages: (conversationId: string) => apiRequest<StoredMessage[]>(`/api/chat/conversations/${enc(conversationId)}/messages`),
  deleteConversation: (conversationId: string) =>
    apiRequest<void>(`/api/chat/conversations/${enc(conversationId)}`, { method: "DELETE" }),
};

export const hubApi = {
  list: (filters: { q?: string; subject?: string; grade?: number | null; role?: string } = {}) =>
    apiRequest<HubAgent[]>(`/api/hub/agents${query(filters)}`),
  detail: (agentId: string) => apiRequest<AgentDetail>(`/api/hub/agents/${enc(agentId)}`),
};

export const installApi = {
  classAgents: (classId: string) => apiRequest<Installation[]>(`/api/classes/${enc(classId)}/agents`),
  installInClass: (classId: string, agentId: string, versionId?: string) =>
    apiRequest<Installation>(`/api/classes/${enc(classId)}/agents`, {
      method: "POST",
      body: { agent_id: agentId, version_id: versionId ?? null },
    }),
  toggle: (classId: string, installationId: string, enabled: boolean) =>
    apiRequest<Installation>(`/api/classes/${enc(classId)}/agents/${enc(installationId)}`, { method: "PATCH", body: { enabled } }),
  uninstall: (classId: string, installationId: string) =>
    apiRequest<void>(`/api/classes/${enc(classId)}/agents/${enc(installationId)}`, { method: "DELETE" }),
  mine: () => apiRequest<Installation[]>("/api/me/agents"),
  installPersonal: (agentId: string) => apiRequest<Installation>("/api/me/agents", { method: "POST", body: { agent_id: agentId } }),
  uninstallPersonal: (installationId: string) => apiRequest<void>(`/api/me/agents/${enc(installationId)}`, { method: "DELETE" }),
};

export const builderApi = {
  mine: () => apiRequest<AgentDetail[]>("/api/agents/mine"),
  create: (manifest: AgentManifest) => apiRequest<AgentDetail>("/api/agents", { method: "POST", body: { manifest } }),
  update: (agentId: string, manifest: AgentManifest) =>
    apiRequest<AgentDetail>(`/api/agents/${enc(agentId)}`, { method: "PUT", body: { manifest } }),
  snapshot: (agentId: string) => apiRequest<AgentDetail>(`/api/agents/${enc(agentId)}/versions`, { method: "POST" }),
  fork: (agentId: string) => apiRequest<AgentDetail>(`/api/agents/${enc(agentId)}/fork`, { method: "POST" }),
  remove: (agentId: string) => apiRequest<void>(`/api/agents/${enc(agentId)}`, { method: "DELETE" }),
  tryPath: (agentId: string) => `/api/agents/${enc(agentId)}/try`,
};

export const toolsApi = {
  list: () => apiRequest<PlatformTool[]>("/api/tools"),
};

export const documentsApi = {
  list: (classId: string) => apiRequest<ClassDocument[]>(`/api/classes/${enc(classId)}/documents`),
  upload: (classId: string, file: File, title: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    return apiRequest<ClassDocument>(`/api/classes/${enc(classId)}/documents`, { method: "POST", formData: form });
  },
  chunks: (classId: string, documentId: string) =>
    apiRequest<{ position: number; location: string; content: string }[]>(
      `/api/classes/${enc(classId)}/documents/${enc(documentId)}/chunks`,
    ),
  reprocess: (classId: string, documentId: string) =>
    apiRequest<ClassDocument>(`/api/classes/${enc(classId)}/documents/${enc(documentId)}/reprocess`, { method: "POST" }),
  remove: (classId: string, documentId: string) =>
    apiRequest<void>(`/api/classes/${enc(classId)}/documents/${enc(documentId)}`, { method: "DELETE" }),
};
