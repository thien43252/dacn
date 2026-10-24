import { createContext, useContext, useId, useLayoutEffect } from "react";

/** Whether a screen's essential data is still loading, usable, or failed (its own error UI is then shown). */
export type EssentialStatus = "pending" | "ready" | "error";

export interface ReadinessReporter {
  report: (id: string, status: EssentialStatus) => void;
  remove: (id: string) => void;
}

export const ReadinessContext = createContext<ReadinessReporter | null>(null);

/**
 * A screen declares the data without which it cannot be used (not widgets or background requests). The post-login
 * welcome waits on the declared statuses; outside the welcome gate this is a no-op. Registration happens in a layout
 * effect so it is visible before the gate evaluates the first committed frame.
 */
export function useEssentialData(status: EssentialStatus): void {
  const reporter = useContext(ReadinessContext);
  const id = useId();
  useLayoutEffect(() => { reporter?.report(id, status); }, [reporter, id, status]);
  useLayoutEffect(() => () => reporter?.remove(id), [reporter, id]);
}
