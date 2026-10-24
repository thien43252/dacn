import { useEffect, useState } from "react";

import type { Role } from "../auth/api";

const NAVIGATION_EVENT = "eduagent:navigate";
const BEFORE_NAVIGATION_EVENT = "eduagent:before-navigate";
const handledHistoryEvents = new WeakSet<Event>();

/** A mounted editor can defer navigation until the user chooses to discard its draft. */
let navigationBlockers = 0;

/** True while an editor has deferred navigation, i.e. leaving the page could discard unsaved work. */
export function hasNavigationGuard(): boolean {
  return navigationBlockers > 0;
}

export function protectNavigation(block: (proceed: () => void) => void): () => void {
  navigationBlockers += 1;
  const listener = (event: Event) => {
    event.preventDefault();
    block((event as CustomEvent<() => void>).detail);
  };
  window.addEventListener(BEFORE_NAVIGATION_EVENT, listener);
  return () => {
    navigationBlockers -= 1;
    window.removeEventListener(BEFORE_NAVIGATION_EVENT, listener);
  };
}

export function navigate(path: string, replace = false): void {
  const proceed = () => publishNavigation(path, replace);
  if (window.dispatchEvent(new CustomEvent(BEFORE_NAVIGATION_EVENT, { cancelable: true, detail: proceed }))) proceed();
}

function publishNavigation(path: string, replace: boolean): void {
  if (replace) {
    window.history.replaceState({}, "", path);
  } else {
    window.history.pushState({}, "", path);
  }
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}

export function useLocation(): { pathname: string; search: string } {
  const readLocation = () => ({ pathname: window.location.pathname, search: window.location.search });
  const [location, setLocation] = useState(readLocation);

  useEffect(() => {
    let previous = window.location.pathname + window.location.search + window.location.hash;
    const update = () => { previous = window.location.pathname + window.location.search + window.location.hash; setLocation(readLocation()); };
    const back = (event: PopStateEvent) => {
      // Several mounted components useLocation; one history event must ask the editor only once.
      if (handledHistoryEvents.has(event)) return;
      handledHistoryEvents.add(event);
      const target = window.location.pathname + window.location.search + window.location.hash;
      const allowed = window.dispatchEvent(new CustomEvent(BEFORE_NAVIGATION_EVENT, {
        cancelable: true, detail: () => publishNavigation(target, false),
      }));
      if (allowed) window.dispatchEvent(new Event(NAVIGATION_EVENT));
      else window.history.pushState({}, "", previous);
    };
    window.addEventListener("popstate", back);
    window.addEventListener(NAVIGATION_EVENT, update);
    return () => {
      window.removeEventListener("popstate", back);
      window.removeEventListener(NAVIGATION_EVENT, update);
    };
  }, []);

  return location;
}

const HOME_PATHS: Record<Role, string> = {
  teacher: "/teacher/classes",
  student: "/student/home",
  parent: "/parent/home",
  admin: "/admin/certification",
};

export const roleLabels: Record<Role, string> = {
  teacher: "Giáo viên",
  student: "Học sinh",
  parent: "Phụ huynh",
  admin: "Quản trị viên",
};

export function getHomePath(role: Role): string {
  return HOME_PATHS[role];
}

export function isWorkspacePath(pathname: string): boolean {
  return Object.keys(HOME_PATHS).some((role) => pathname.startsWith(`/${role}/`));
}

export function canAccessPath(role: Role, pathname: string): boolean {
  return pathname.startsWith(`/${role}/`);
}

/**
 * Matches a pattern such as `/teacher/classes/:classId` against a pathname.
 * Returns the decoded params, or null when the segment counts or literal segments differ.
 */
export function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const patternParts = pattern.split("/").filter(Boolean);
  const pathParts = pathname.split("/").filter(Boolean);
  if (patternParts.length !== pathParts.length) return null;
  const params: Record<string, string> = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const expected = patternParts[index];
    const actual = pathParts[index];
    if (expected.startsWith(":")) {
      params[expected.slice(1)] = decodeURIComponent(actual);
    } else if (expected !== actual) {
      return null;
    }
  }
  return params;
}
