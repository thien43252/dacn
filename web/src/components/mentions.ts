/** Main chat targets; suggestions do not grant capability, project scope or dispatch authority. */

export interface MentionAgent {
  /** A business agent, "all", or the mention of an extension agent the admin applied system-wide. */
  id: string;
  name: string;
  description: string;
  shortLabel: string;
  /** Extension only: the animal the Platform shows for it. */
  mascot?: string;
}

export const MENTION_AGENTS: MentionAgent[] = [
  { id: "planner", name: "Project Design", shortLabel: "Lập kế hoạch", description: "Làm rõ ý tưởng và xây dựng kế hoạch" },
  { id: "feasibility", name: "Feasibility & Capability", shortLabel: "Khả thi", description: "Đối chiếu kỹ năng, thời gian và nguồn lực" },
  { id: "safety", name: "Policy & Governance", shortLabel: "An toàn", description: "Đối chiếu quy định, an toàn và quyền riêng tư" },
  { id: "progress", name: "Progress & Evidence", shortLabel: "Tiến độ", description: "Theo dõi tiến độ và minh chứng" },
];

/** Canonical core display names from the mention registry; IDs and extension names stay unchanged. */
export const CORE_AGENT_LABELS = Object.fromEntries(
  MENTION_AGENTS.map(({ id, name }) => [id, name]),
) as Record<"planner" | "feasibility" | "safety" | "progress", string>;

/**
 * Temporary screen scope: the student workspace offers only Planner, Feasibility and Safety.
 * Platform applies the same scope to routing, so typing a hidden mention by hand never reaches the agent.
 */
export const STUDENT_HIDDEN_AGENTS: ReadonlySet<string> = new Set(["progress"]);

/** The core agents this role's chat menu offers. */
export function mentionAgentsFor(role: string): MentionAgent[] {
  return role === "student" ? MENTION_AGENTS.filter((agent) => !STUDENT_HIDDEN_AGENTS.has(agent.id)) : MENTION_AGENTS;
}

/** Extension agents the admin applied, as the chat menu offers them. A fetch failure leaves the four core agents. */
export async function loadExtensionAgents(projectId: string | null): Promise<MentionAgent[]> {
  return (await loadChatAgents(projectId)).extensions;
}

/**
 * The chat's "@" roster from the Platform: applied extension agents, and the core agents the admin's applied workflow
 * removed (the menu stops offering those; the Platform refuses them anyway). A fetch failure removes nothing.
 */
export async function loadChatAgents(projectId: string | null): Promise<{ extensions: MentionAgent[]; removedCore: string[] }> {
  try {
    const query = projectId ? `?${new URLSearchParams({ project_id: projectId })}` : "";
    const response = await fetch(`/api/chat/agents${query}`, { credentials: "include" });
    if (!response.ok) return { extensions: [], removedCore: [] };
    const data = (await response.json()) as {
      extensions?: Array<{ mention: string; name: string; description: string; mascot?: string }>;
      removed_core?: string[];
    };
    return {
      extensions: (data.extensions ?? []).map((item) => ({ id: item.mention, name: item.name, shortLabel: "Agent mở rộng", description: item.description, mascot: item.mascot })),
      removedCore: data.removed_core ?? [],
    };
  } catch {
    return { extensions: [], removedCore: [] };
  }
}

/** Longest text accepted after "@" before the menu gives up, so a stray "@" does not scan a whole paragraph. */
const MAX_QUERY_LENGTH = 24;

export interface MentionQuery {
  /** Index of the "@" that opens the token. */
  start: number;
  /** What was typed between "@" and the caret. */
  query: string;
}

/** The mention being typed at the caret, or null when the caret is not inside one. */
export function findMentionQuery(text: string, caret: number): MentionQuery | null {
  if (caret < 1 || caret > text.length) return null;

  for (let index = caret - 1; index >= 0 && caret - index <= MAX_QUERY_LENGTH + 1; index -= 1) {
    const char = text[index];
    if (/\s/.test(char)) return null;
    if (char !== "@") continue;
    // Only a "@" that opens a word starts a mention, so an email address never triggers the menu.
    const before = index > 0 ? text[index - 1] : "";
    if (before && !/\s/.test(before)) return null;
    return { start: index, query: text.slice(index + 1, caret) };
  }
  return null;
}

/** Ignores case and spaces when matching the business-agent catalog. */
function normalize(value: string): string {
  return value.toLowerCase().replace(/\s+/g, "");
}

export function filterAgents(agents: MentionAgent[], query: string): MentionAgent[] {
  const needle = normalize(query);
  if (!needle) return agents;
  return agents.filter((agent) => normalize(agent.name).includes(needle) || normalize(agent.id).includes(needle));
}

export interface MentionInsert {
  text: string;
  caret: number;
}

const CORE_IDS: ReadonlySet<string> = new Set(MENTION_AGENTS.map((agent) => agent.id));

/**
 * What "@" writes for an agent: a core agent's display name, as the menu shows it (the Platform resolves it to the
 * same agent), and an extension agent's handle.
 */
export function mentionToken(agent: MentionAgent): string {
  return CORE_IDS.has(agent.id) ? agent.name : agent.id;
}

const CORE_MENTION =
  /(?<![\w@])@(Project\s*Design|Feasibility\s*&\s*Capability|Policy\s*&\s*Governance|Safety\s*&\s*Governance|Progress\s*&\s*Evidence|planner|feasibility|safety|progress)\b/i;
const CORE_BY_TOKEN: Record<string, string> = {
  ...Object.fromEntries(MENTION_AGENTS.flatMap(({ id, name }) => [[id, id], [normalize(name), id]])),
  "safety&governance": "safety",
};

/** The first core agent a message mentions, by its id or display name. */
export function firstCoreMention(text: string): string | undefined {
  const token = text.match(CORE_MENTION)?.[1];
  return token ? CORE_BY_TOKEN[normalize(token)] : undefined;
}

/** Replaces the token being typed with the agent's mention and a trailing space. */
export function applyMention(text: string, mention: MentionQuery, agent: MentionAgent): MentionInsert {
  const inserted = `@${mentionToken(agent)} `;
  const caretBefore = mention.start + 1 + mention.query.length;
  return {
    text: text.slice(0, mention.start) + inserted + text.slice(caretBefore),
    caret: mention.start + inserted.length,
  };
}

/** Text and caret after the "@" button is pressed; adds a separating space so the token opens a word. */
export function openMentionAt(text: string, caret: number): MentionInsert {
  const position = Math.min(Math.max(caret, 0), text.length);
  const inserted = position > 0 && !/\s/.test(text[position - 1]) ? " @" : "@";
  return {
    text: text.slice(0, position) + inserted + text.slice(position),
    caret: position + inserted.length,
  };
}

/** What the "@" button wrote, so pressing it again can take exactly that back out. */
export interface ButtonInsert {
  start: number;
  length: number;
}

/** Undoes the button's insert. Leaves the text alone if it no longer looks like an untouched "@" token. */
export function undoMentionInsert(text: string, insert: ButtonInsert): MentionInsert {
  const end = insert.start + insert.length;
  if (end > text.length || !text.slice(insert.start, end).endsWith("@")) {
    return { text, caret: Math.min(end, text.length) };
  }
  return { text: text.slice(0, insert.start) + text.slice(end), caret: insert.start };
}

/** Agent names mentioned in a finished message, in supported-catalog order, without duplicates. */
export function mentionedAgents(text: string, agents: MentionAgent[] = MENTION_AGENTS): MentionAgent[] {
  const found: MentionAgent[] = [];
  for (const agent of agents) {
    const pattern = new RegExp(`(?<![\\w@])@(?:${agent.id}|${agent.name.replace(/\s+/g, "\\s*")})\\b`, "i");
    if (pattern.test(text)) found.push(agent);
  }
  return found;
}


/** Selects a chat target without dropping the user's question or sending a request. */
export function selectAgentMention(text: string, agent: MentionAgent): string {
  const leading =
    /^@(?:Project\s*Design|Feasibility\s*&\s*Capability|Policy\s*&\s*Governance|Safety\s*&\s*Governance|Progress\s*&\s*Evidence|planner|feasibility|safety|progress)?(?=\s|$)\s*/i;
  return `@${mentionToken(agent)} ${text.replace(leading, "")}`;
}
