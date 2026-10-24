import type { Role } from "../auth/api";
import adminAmber from "../assets/illustrations/derived/portal-admin-amber.webp";
import studentCyan from "../assets/illustrations/derived/portal-student-cyan.webp";
import teacherViolet from "../assets/illustrations/derived/portal-teacher-violet.webp";

export type PortalId = "portal-stone-cyan" | "portal-stone-violet" | "portal-stone-amber";

export interface PortalTheme {
  id: PortalId;
  src: string;
  /** Gate centre (%): object-position keeps it at the same screen fraction, so a narrow crop still frames it. */
  focusX: number;
  focusY: number;
}

/** Fixed mapping by the role the app resolved (ILLUSTRATION_USAGE §14.2). Unknown role: no artwork. */
const PORTALS: Record<Role, PortalTheme> = {
  student: { id: "portal-stone-cyan", src: studentCyan, focusX: 71, focusY: 66 },
  teacher: { id: "portal-stone-violet", src: teacherViolet, focusX: 60, focusY: 72 },
  parent: { id: "portal-stone-cyan", src: studentCyan, focusX: 40, focusY: 66 },
  admin: { id: "portal-stone-amber", src: adminAmber, focusX: 60, focusY: 72 },
};

export function portalForRole(role: string | null | undefined): PortalTheme | null {
  return role && Object.prototype.hasOwnProperty.call(PORTALS, role) ? PORTALS[role as Role] : null;
}

export function welcomeHeading(name: string | null | undefined): string {
  const trimmed = name?.trim();
  return trimmed ? `Chào mừng ${trimmed} đến với EduAgent Hub!` : "Chào mừng bạn đến với EduAgent Hub!";
}
