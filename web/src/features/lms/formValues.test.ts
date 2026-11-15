import { describe, expect, it } from "vitest";
import type { QuestionInput } from "../../api-client/lms";
import { localDateTime, questionInput } from "./formValues";

describe("question request serialization", () => {
  const base: QuestionInput = {
    kind: "true_false", prompt: "True?", options: [], answer_key: false,
    points: 1, explanation: "Reason", rubric: null,
  };

  it("keeps boolean false and removes server metadata rejected by QuestionIn", () => {
    expect(questionInput({ ...base, id: "q", position: 3, source: "ai", affects_submitted: 2 })).toEqual({ ...base, multi_scoring: "all_or_nothing" });
  });

  it("sends empty options for essays and preserves their rubric", () => {
    const rubric = { criteria: [{ name: "Reasoning", max_points: 2, description: "Explain" }], model_answer: "Example" };
    expect(questionInput({ ...base, kind: "essay", options: [{ id: "a", text: "stale" }], rubric })).toMatchObject({ options: [], answer_key: null, rubric });
  });

  it("preserves option identifiers and accepted short answers", () => {
    const options = [{ id: "a", text: "A" }, { id: "b", text: "B" }];
    expect(questionInput({ ...base, kind: "multi", options, answer_key: ["a", "b"], multi_scoring: "partial" })).toMatchObject({ options, answer_key: ["a", "b"], multi_scoring: "partial" });
    expect(questionInput({ ...base, kind: "short", answer_key: ["One", "1"] }).answer_key).toEqual(["One", "1"]);
  });
});

it("formats datetime-local using the local clock instead of slicing UTC", () => {
  const date = new Date(2026, 10, 16, 14, 35);
  expect(localDateTime(date.toISOString())).toBe("2026-11-16T14:35");
  expect(localDateTime(null)).toBe("");
  expect(localDateTime("invalid")).toBe("");
});
