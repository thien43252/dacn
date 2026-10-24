/**
 * Status pill shared across features.
 * Every pill carries a text label, so colour is never the only signal.
 */

export type Tone = "neutral" | "positive" | "info" | "warn" | "danger" | "muted";

interface StatusBadgeProps {
  label: string;
  tone?: Tone;
  title?: string;
  className?: string;
}

export function StatusBadge({ label, tone = "neutral", title, className = "" }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-badge--${tone}${className ? ` ${className}` : ""}`} title={title}>
      <i aria-hidden="true" />
      {label}
    </span>
  );
}
