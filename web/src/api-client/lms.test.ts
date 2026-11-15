import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./http";
import { lmsApi } from "./lms";

afterEach(() => vi.unstubAllGlobals());

function respond(body: unknown, status = 200) {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("LMS API contract regressions", () => {
  it("passes the selected child to lessons and quizzes with encoded identifiers", async () => {
    const fetch = respond({});
    await lmsApi.lessons.get("class /", "lesson /", "child +");
    await lmsApi.quizzes.get("class /", "quiz /", "child +");
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      "/api/classes/class%20%2F/lessons/lesson%20%2F?student_id=child%20%2B",
      "/api/classes/class%20%2F/quizzes/quiz%20%2F?student_id=child%20%2B",
    ]);
  });

  it("uses the dedicated gradebook column route for weight changes", async () => {
    const fetch = respond({ item_id: "item", weight: 0, counts_in_grade: false });
    const result = await lmsApi.gradebook.updateColumn("class", "item", { weight: 0, counts_in_grade: false });
    expect(fetch.mock.calls[0][0]).toBe("/api/classes/class/gradebook/columns/item");
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: "PATCH", body: '{"weight":0,"counts_in_grade":false}' });
    expect(result.weight).toBe(0);
  });

  it("serializes essay suggestion targets and explicit discard reviews", async () => {
    const fetch = respond([]);
    await lmsApi.assist.suggestGrading("class", [{ type: "attempt_question", id: "attempt:question" }]);
    await lmsApi.assist.reviewSuggestion("class", "suggestion", { action: "discard" });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ targets: [{ type: "attempt_question", id: "attempt:question" }] });
    expect(fetch.mock.calls[1][0]).toBe("/api/classes/class/suggestions/suggestion/review");
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ action: "discard" });
  });

  it("preserves the exact attempt_closed error used to navigate to results", async () => {
    respond({ detail: "attempt_closed" }, 409);
    await expect(lmsApi.attempts.saveAnswer("class", "attempt", "q", false)).rejects.toMatchObject({ message: "attempt_closed", status: 409 });
  });

  it("shows a readable validation error when Pydantic returns a detail list", async () => {
    respond({ detail: [{ loc: ["body", "options"], msg: "Input should be a valid list", type: "list_type" }] }, 422);
    const error = await lmsApi.quizzes.update("class", "quiz", { duration_minutes: 0 }).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("Dữ liệu không hợp lệ");
    expect((error as ApiError).message).not.toContain("[object Object]");
  });
});
