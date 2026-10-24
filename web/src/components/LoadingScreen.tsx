import { Logo } from "./Logo";

export function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="loading-screen" aria-live="polite" aria-busy="true">
      <Logo />
      <span className="loading-spinner" aria-hidden="true" />
      <p>{label}…</p>
    </main>
  );
}
