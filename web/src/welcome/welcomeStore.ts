import type { User } from "../auth/api";

/** One welcome attempt, created only by an active sign-in. `startedAt` is the moment authentication succeeded. */
export interface WelcomeSession {
  id: number;
  userId: string;
  role: User["role"];
  name: string;
  startedAt: number;
}

let current: WelcomeSession | null = null;
let nextId = 1;
const listeners = new Set<() => void>();

function publish(next: WelcomeSession | null) {
  current = next;
  listeners.forEach((listener) => listener());
}

/** Called by the sign-in form after a successful login/register. Session restore never calls this, so a refresh
 *  can never replay the welcome. A newer sign-in replaces an older one. */
export function startWelcome(user: Pick<User, "id" | "role" | "name">): void {
  publish({ id: nextId++, userId: user.id, role: user.role, name: user.name, startedAt: performance.now() });
}

export function endWelcome(): void {
  if (current) publish(null);
}

export function subscribeWelcome(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getWelcomeSession(): WelcomeSession | null {
  return current;
}
