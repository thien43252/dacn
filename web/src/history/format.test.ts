import { describe, expect, it } from "vitest";

import { historyQueryString } from "./api";
import {
  badgeFor,
  customRangeError,
  groupEventsByDay,
  presetRange,
  schoolDateKey,
  shiftDateKey,
  STATUS_META,
  SUGGESTION_STATUS_META,
  typeOptionsFor,
  versionLine,
} from "./format";
import { makeEvent } from "./testEvents";

describe("typeOptionsFor", () => {
  it("only offers team activity in the team scope", () => {
    expect(typeOptionsFor("mine").map((option) => option.label)).toEqual(["Tất cả", "Gửi kế hoạch", "Thay đổi", "Đề xuất agent"]);
    expect(typeOptionsFor("team").map((option) => option.value)).toContain("team");
  });
});

describe("status badges", () => {
  it("always pair an icon with text", () => {
    for (const meta of Object.values(STATUS_META)) {
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.icon.length).toBeGreaterThan(0);
    }
  });

  it("keep submission and approval distinct", () => {
    expect(STATUS_META.SUBMITTED.label).not.toBe(STATUS_META.APPROVED.label);
    expect(STATUS_META.SUBMITTED.label).toBe("Đã gửi duyệt");
  });

  it("show a disabled agent as not evaluated, never as PASS", () => {
    expect(STATUS_META.DISABLED.label).toBe("Chưa đánh giá, agent đang tắt");
    expect(STATUS_META.DISABLED.tone).not.toBe("success");
  });

  it("shows a new-agent suggestion with the same badges as the proposals tab", () => {
    const suggestion = makeEvent({ type: "platform_agent_suggestion.created", category: "agent", version: null, version_hash: null });
    expect(badgeFor({ ...suggestion, status: "SUBMITTED" })).toEqual(SUGGESTION_STATUS_META.SUBMITTED);
    expect(badgeFor({ ...suggestion, status: "SEEN" })?.label).toBe("Đã xem");
    expect(SUGGESTION_STATUS_META.SUBMITTED.label).toBe("Đã gửi");
  });

  it("gives team activity no badge", () => {
    expect(badgeFor(makeEvent({ type: "team.task_completed", category: "team", status: null, version: null }))).toBeNull();
  });
});

describe("versionLine", () => {
  it("shows the version chain, hash and coverage", () => {
    expect(versionLine(makeEvent())).toBe("v3");
    expect(versionLine(makeEvent({ previous_version: 2, version_hash: null }))).toBe("v2 → v3");
    expect(versionLine(makeEvent({ coverage_percent: 50 }))).toBe("v3 · đã kiểm tra 50% khi gửi");
  });

  it("is hidden for team activity", () => {
    expect(versionLine(makeEvent({ category: "team", version: null, version_hash: null }))).toBeNull();
  });
});

describe("date helpers", () => {
  it("uses school time for the calendar day", () => {
    expect(schoolDateKey(new Date("2026-09-25T18:30:00Z"))).toBe("2026-09-26");
  });

  it("shifts across month boundaries", () => {
    expect(shiftDateKey("2026-10-02", -6)).toBe("2026-09-26");
  });

  it("builds inclusive presets", () => {
    expect(presetRange("all", "2026-09-26")).toEqual({});
    expect(presetRange("7d", "2026-09-26")).toEqual({ from: "2026-09-20", to: "2026-09-26" });
    expect(presetRange("30d", "2026-09-26")).toEqual({ from: "2026-08-28", to: "2026-09-26" });
  });

  it("rejects a reversed custom range", () => {
    expect(customRangeError({ from: "2026-09-20", to: "2026-09-10" })).not.toBeNull();
    expect(customRangeError({ from: "2026-09-10", to: "2026-09-10" })).toBeNull();
    expect(customRangeError({ from: "2026-09-10" })).toBeNull();
  });
});

describe("historyQueryString", () => {
  it("combines scope, type and dates and omits empty dates", () => {
    expect(historyQueryString({ scope: "team", type: "agent", from: "2026-09-20", to: "2026-09-26" })).toBe(
      "scope=team&type=agent&from=2026-09-20&to=2026-09-26",
    );
    expect(historyQueryString({ scope: "mine", type: "all" })).toBe("scope=mine&type=all");
  });
});

describe("groupEventsByDay", () => {
  it("groups by school day and labels today and yesterday", () => {
    const days = groupEventsByDay(
      [
        makeEvent({ id: "a", occurred_at: "2026-09-26T02:00:00Z" }),
        makeEvent({ id: "b", occurred_at: "2026-09-25T20:00:00Z" }),
        makeEvent({ id: "c", occurred_at: "2026-09-25T01:00:00Z" }),
        makeEvent({ id: "d", occurred_at: "2026-09-20T01:00:00Z" }),
      ],
      "2026-09-26",
    );

    expect(days.map((day) => [day.label, day.events.map((event) => event.id)])).toEqual([
      ["Hôm nay", ["a", "b"]],
      ["Hôm qua", ["c"]],
      [days[2].label, ["d"]],
    ]);
    expect(days[2].key).toBe("2026-09-20");
  });
});
