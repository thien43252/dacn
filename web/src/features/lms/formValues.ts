import type { QuestionInput, QuizQuestion } from "../../api-client/lms";

export function questionInput(question: Partial<QuizQuestion> & QuestionInput): QuestionInput {
  return {
    kind: question.kind,
    prompt: question.prompt,
    options: question.kind === "single" || question.kind === "multi" ? question.options : [],
    answer_key: question.kind === "essay" ? null : question.answer_key,
    points: question.points,
    multi_scoring: question.multi_scoring ?? "all_or_nothing",
    explanation: question.explanation,
    rubric: question.kind === "essay" ? question.rubric : null,
  };
}

export function localDateTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
