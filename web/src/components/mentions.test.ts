import { describe, expect, it } from "vitest";

import {
  MENTION_AGENTS,
  applyMention,
  filterAgents,
  findMentionQuery,
  firstCoreMention,
  mentionAgentsFor,
  mentionedAgents,
  selectAgentMention,
  openMentionAt,
  undoMentionInsert,
} from "./mentions";

describe("findMentionQuery", () => {
  it("opens on @ at the start and after a space", () => {
    expect(findMentionQuery("@", 1)).toEqual({ start: 0, query: "" });
    expect(findMentionQuery("Hỏi @age", 8)).toEqual({ start: 4, query: "age" });
    expect(findMentionQuery("Hỏi\n@a", 6)).toEqual({ start: 4, query: "a" });
  });

  it("stays closed when there is no mention at the caret", () => {
    expect(findMentionQuery("", 0)).toBeNull();
    expect(findMentionQuery("Nhóm nên làm gì", 15)).toBeNull();
    expect(findMentionQuery("@Agent 1 tiếp theo", 18)).toBeNull();
  });

  it("does not treat an email as a mention", () => {
    expect(findMentionQuery("minh@demoedu", 12)).toBeNull();
  });

  it("gives up once the token grows past the limit", () => {
    expect(findMentionQuery(`@${"a".repeat(24)}`, 25)).not.toBeNull();
    expect(findMentionQuery(`@${"a".repeat(30)}`, 31)).toBeNull();
  });

  it("reads the token at the caret, not at the end of the text", () => {
    expect(findMentionQuery("@ag xong", 3)).toEqual({ start: 0, query: "ag" });
  });
});

describe("filterAgents", () => {
  it("returns every agent for an empty query", () => {
    expect(filterAgents(MENTION_AGENTS, "")).toHaveLength(4);
  });

  it("matches ignoring case and spaces", () => {
    expect(filterAgents(MENTION_AGENTS, "planner").map((a) => a.name)).toEqual(["Project Design"]);
    expect(filterAgents(MENTION_AGENTS, "SA FETY").map((a) => a.name)).toEqual(["Policy & Governance"]);
    expect(filterAgents(MENTION_AGENTS, "safet").map((a) => a.name)).toEqual(["Policy & Governance"]);
  });

  it("returns nothing when no agent matches", () => {
    expect(filterAgents(MENTION_AGENTS, "khong-co")).toEqual([]);
  });
});

describe("applyMention", () => {
  const agent = MENTION_AGENTS[1];

  it("replaces the typed token and puts the caret after the space", () => {
    const result = applyMention("Hỏi @age", { start: 4, query: "age" }, agent);
    expect(result).toEqual({ text: "Hỏi @Feasibility & Capability ", caret: 30 });
  });

  it("keeps the text that follows the caret", () => {
    const result = applyMention("@ag xong", { start: 0, query: "ag" }, agent);
    expect(result.text).toBe("@Feasibility & Capability  xong");
    expect(result.text.slice(0, result.caret)).toBe("@Feasibility & Capability ");
  });

  it("writes the name the menu shows, not the internal id", () => {
    const safety = MENTION_AGENTS.find((item) => item.id === "safety")!;
    expect(applyMention("@pol", { start: 0, query: "pol" }, safety).text).toBe("@Policy & Governance ");
  });

  it("keeps an extension agent's handle, which is how the Platform finds it", () => {
    const extension = { id: "budget-bot", name: "Budget Bot", shortLabel: "Agent mở rộng", description: "" };
    expect(applyMention("@bud", { start: 0, query: "bud" }, extension).text).toBe("@budget-bot ");
  });
});

describe("openMentionAt", () => {
  it("writes a bare @ into an empty box", () => {
    expect(openMentionAt("", 0)).toEqual({ text: "@", caret: 1 });
  });

  it("adds a space first so the token opens a word", () => {
    expect(openMentionAt("Nhờ", 3)).toEqual({ text: "Nhờ @", caret: 5 });
  });

  it("does not double the space when one is already there", () => {
    expect(openMentionAt("Nhờ ", 4)).toEqual({ text: "Nhờ @", caret: 5 });
  });

  it("inserts at the caret, keeping the rest of the text", () => {
    const result = openMentionAt("Nhờ xem", 3);
    expect(result.text).toBe("Nhờ @ xem");
    expect(result.caret).toBe(5);
  });

  it("opens a token the menu then recognises", () => {
    const result = openMentionAt("Nhờ", 3);
    expect(findMentionQuery(result.text, result.caret)).toEqual({ start: 4, query: "" });
  });
});

describe("undoMentionInsert", () => {
  it("takes back a bare @ so pressing the button twice leaves nothing behind", () => {
    const opened = openMentionAt("", 0);
    expect(undoMentionInsert(opened.text, { start: 0, length: opened.caret })).toEqual({ text: "", caret: 0 });
  });

  it("takes back the space it added too", () => {
    const opened = openMentionAt("Nhờ", 3);
    expect(undoMentionInsert(opened.text, { start: 3, length: opened.caret - 3 })).toEqual({
      text: "Nhờ",
      caret: 3,
    });
  });

  it("keeps the text that followed the caret", () => {
    const opened = openMentionAt("Nhờ xem", 3);
    expect(undoMentionInsert(opened.text, { start: 3, length: opened.caret - 3 }).text).toBe("Nhờ xem");
  });

  it("leaves the text alone when the token no longer ends in @", () => {
    expect(undoMentionInsert("Nhờ Agent", { start: 3, length: 2 })).toEqual({ text: "Nhờ Agent", caret: 5 });
  });

  it("leaves the text alone when the recorded range is past the end", () => {
    expect(undoMentionInsert("@", { start: 5, length: 2 })).toEqual({ text: "@", caret: 1 });
  });
});

describe("mentionedAgents", () => {
  it("lists the agents a finished message names, in order and without repeats", () => {
    const found = mentionedAgents("@safety và @planner cùng xem, @safety nhắc lại");
    expect(found.map((a) => a.name)).toEqual(["Project Design", "Policy & Governance"]);
  });

  it("returns nothing when the message names no agent", () => {
    expect(mentionedAgents("Nhóm nên bắt đầu từ đâu?")).toEqual([]);
  });
});


describe("selectAgentMention", () => {
  it.each([
    ["", "@Feasibility & Capability "],
    ["@", "@Feasibility & Capability "],
    ["Cần bao nhiêu thời gian?", "@Feasibility & Capability Cần bao nhiêu thời gian?"],
    ["@planner Cần bao nhiêu thời gian?", "@Feasibility & Capability Cần bao nhiêu thời gian?"],
    ["@Planner\nCâu hỏi", "@Feasibility & Capability Câu hỏi"],
    ["@Policy & Governance Câu hỏi", "@Feasibility & Capability Câu hỏi"],
    ["@unknown Câu hỏi", "@Feasibility & Capability @unknown Câu hỏi"],
    ["user@example.com", "@Feasibility & Capability user@example.com"],
  ])("preserves the question when selecting a target in %s", (text, expected) => {
    expect(selectAgentMention(text, MENTION_AGENTS[1])).toBe(expected);
  });
});

describe("firstCoreMention", () => {
  it("reads a core agent by display name or id, whichever comes first", () => {
    expect(firstCoreMention("@Policy & Governance xem giúp")).toBe("safety");
    expect(firstCoreMention("@Safety & Governance xem giúp")).toBe("safety");
    expect(firstCoreMention("Nhờ @Project Design rồi @safety")).toBe("planner");
    expect(firstCoreMention("@feasibility đánh giá")).toBe("feasibility");
    expect(firstCoreMention("user@example.com")).toBeUndefined();
  });
});

describe("mentionAgentsFor", () => {
  it("offers students only Planner, Feasibility and Safety", () => {
    expect(mentionAgentsFor("student").map((agent) => agent.id)).toEqual(["planner", "feasibility", "safety"]);
    expect(filterAgents(mentionAgentsFor("student"), "prog")).toEqual([]);
  });

  it("keeps all four core agents for the teacher", () => {
    expect(mentionAgentsFor("teacher")).toEqual(MENTION_AGENTS);
  });
});
