import { useState } from "react";

import { chatApi } from "../../api-client/agents";
import type { AgentRef, ChatAgent, PlanEvent, ProcessSummary, StepEvent, StepNote, StepStatus } from "../../api-client/types";
import { Icon } from "../Icon";
import { Mascot, MASCOTS, type MascotName } from "../Mascot";
import { MessageBody, MessageCitations } from "./MessageBody";

/** One step of the progress panel (feature 002, FR-032 to FR-035). */
export interface PanelStep {
  key: string;
  title: string;
  agent: AgentRef;
  status: StepStatus;
  duration_ms?: number;
  tools: { name: string; status: string }[];
}

export interface ProcessState {
  steps: PanelStep[];
  /** Collapsed into the one-line summary once the answer is done. */
  done: boolean;
  started_at?: number;
  duration_ms?: number;
  agents?: number;
  lead?: string;
}

export const STEP_STATUS_LABELS: Record<StepStatus, string> = {
  pending: "Chờ",
  running: "Đang làm",
  done: "Xong",
  error: "Lỗi",
  blocked: "Bị chặn",
  skipped: "Bỏ qua",
};

const STEP_ICONS: Record<StepStatus, Parameters<typeof Icon>[0]["name"]> = {
  pending: "clock",
  running: "sparkles",
  done: "check",
  error: "alert",
  blocked: "shield",
  skipped: "skip",
};

function mascotName(avatar: string | undefined): MascotName {
  return (avatar && avatar in MASCOTS ? avatar : "owl") as MascotName;
}

/** `plan` replaces the whole list; tools already seen on a step are kept. */
export function applyPlan(process: ProcessState | undefined, event: PlanEvent, now = Date.now()): ProcessState {
  const tools = new Map((process?.steps ?? []).map((step) => [step.key, step.tools]));
  return {
    steps: event.steps.map((step) => ({ key: step.key, title: step.title, agent: step.agent, status: step.status, tools: tools.get(step.key) ?? [] })),
    done: false,
    started_at: process?.started_at ?? now,
    lead: event.lead.slug,
  };
}

export function applyStep(process: ProcessState | undefined, event: StepEvent): ProcessState | undefined {
  if (!process || event.key === "analyze" || event.key === "synthesis") return process;
  const known = process.steps.some((step) => step.key === event.key);
  const steps = known
    ? process.steps.map((step) => (step.key === event.key
      ? { ...step, status: event.status, title: event.title ?? step.title, agent: event.agent ?? step.agent, duration_ms: event.duration_ms ?? step.duration_ms }
      : step))
    : [...process.steps, { key: event.key, title: event.title ?? event.key, agent: event.agent ?? { slug: "", name: "", avatar: "" }, status: event.status, duration_ms: event.duration_ms, tools: [] }];
  return { ...process, steps };
}

export function applyStepTool(process: ProcessState | undefined, stepKey: string, name: string, status: string): ProcessState | undefined {
  if (!process) return process;
  return {
    ...process,
    steps: process.steps.map((step) => (step.key === stepKey
      ? { ...step, tools: [...step.tools.filter((tool) => tool.name !== name), { name, status }] }
      : step)),
  };
}

export function finishProcess(process: ProcessState | undefined, now = Date.now()): ProcessState | undefined {
  if (!process) return process;
  const agents = new Set(process.steps.map((step) => step.agent.slug).filter(Boolean));
  if (process.lead) agents.add(process.lead);
  return { ...process, done: true, duration_ms: process.duration_ms ?? now - (process.started_at ?? now), agents: process.agents ?? agents.size };
}

/** The panel of a stored answer, from `meta.process` (FR-035). */
export function processFromStored(summary: ProcessSummary | undefined, agents: ChatAgent[]): ProcessState | undefined {
  if (!summary) return undefined;
  const bySlug = new Map(agents.map((agent) => [agent.slug, agent]));
  return {
    done: true,
    duration_ms: summary.duration_ms,
    agents: summary.agents,
    steps: summary.steps.map((step) => {
      const agent = bySlug.get(step.agent);
      return { key: step.key, title: step.title, status: step.status, tools: [], agent: { slug: step.agent, name: agent?.name ?? step.agent, avatar: agent?.avatar ?? "owl" } };
    }),
  };
}

/** "Đã làm việc · 2 agent · 5 giây" */
export function processSummary(process: ProcessState): string {
  if (!process.done) return "Đang làm việc…";
  const seconds = Math.max(1, Math.round((process.duration_ms ?? 0) / 1000));
  return `Đã làm việc · ${process.agents ?? process.steps.length} agent · ${seconds} giây`;
}

/** A working note as the server returned it: shown only when it passed review. */
export function StepNoteBody({ note }: { note?: StepNote }) {
  if (note?.visibility === "visible" && note.note) {
    return (
      <>
        <MessageBody text={note.note} />
        <MessageCitations items={note.citations} />
      </>
    );
  }
  if (note?.visibility === "hidden") return <span className="ea-muted"><Icon name="lock" /> {note.reason_text ?? "Nội dung này đã được ẩn"}</span>;
  return <span className="ea-muted">Phần việc này không có ghi chú.</span>;
}

type NoteState = { loading: true } | { loading: false; note?: StepNote; error?: string };

interface ProcessPanelProps {
  process: ProcessState;
  /** The stored answer the notes belong to; notes can be opened only once it is stored. */
  messageId?: string;
  loadNote?: (messageId: string, stepKey: string) => Promise<StepNote>;
}

/**
 * The progress of a multi-step answer: each step with its agent and status, updated live, then collapsed into one line
 * that opens again. Opening a finished step loads its working note, which the server reviews first (R9).
 */
export function ProcessPanel({ process, messageId, loadNote = chatApi.stepNote }: ProcessPanelProps) {
  const [notes, setNotes] = useState<Record<string, NoteState>>({});

  function open(step: PanelStep) {
    if (!messageId || !process.done || step.status !== "done" || notes[step.key]) return;
    setNotes((current) => ({ ...current, [step.key]: { loading: true } }));
    loadNote(messageId, step.key)
      .then((note) => setNotes((current) => ({ ...current, [step.key]: { loading: false, note } })))
      .catch(() => setNotes((current) => ({ ...current, [step.key]: { loading: false, error: "Chưa tải được ghi chú." } })));
  }

  return (
    <details className={`ea-process${process.done ? " is-done" : ""}`} open={!process.done}>
      <summary><Icon name="layers" /> {processSummary(process)}</summary>
      <ol className="ea-process__steps">
        {process.steps.map((step) => {
          const state = notes[step.key];
          const openable = process.done && step.status === "done" && Boolean(messageId);
          const line = (
            <>
              <Mascot character={mascotName(step.agent.avatar)} mood={step.status === "running" ? "thinking" : "still"} />
              <span className="ea-process__title">
                <strong>{step.title}</strong>
                <small>{step.agent.name}{step.duration_ms !== undefined && step.status !== "running" ? ` · ${Math.max(1, Math.round(step.duration_ms / 1000))} giây` : ""}</small>
              </span>
              <span className={`ea-process__status ea-process__status--${step.status}`}>
                <Icon name={STEP_ICONS[step.status]} /> {STEP_STATUS_LABELS[step.status]}
              </span>
            </>
          );
          return (
            <li key={step.key} className={`ea-process__step ea-process__step--${step.status}`}>
              {openable ? (
                <details onToggle={(event) => { if ((event.currentTarget as HTMLDetailsElement).open) open(step); }}>
                  <summary className="ea-process__line">{line}</summary>
                  <div className="ea-process__note">
                    {!state || state.loading ? <span className="ea-muted">Đang tải ghi chú…</span>
                      : state.error ? <span className="form-error">{state.error}</span>
                      : <StepNoteBody note={state.note} />}
                  </div>
                </details>
              ) : (
                <div className="ea-process__line">{line}</div>
              )}
              {step.tools.length > 0 && (
                <ul className="ea-process__tools">
                  {step.tools.map((tool) => <li key={tool.name} className={`ea-tool-line ea-tool-line--${tool.status}`}>{tool.name}</li>)}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
