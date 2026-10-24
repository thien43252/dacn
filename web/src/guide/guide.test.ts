import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GUIDES, GUIDE_HOME, GUIDE_VERSION, contextGuidesFor, overviewOf } from "./guideSteps";
import { guideKey, readGuide, writeGuide } from "./guideStorage";

function stubStorage(storage: Partial<Storage>) {
  Object.defineProperty(globalThis, "window", { configurable: true, value: { localStorage: storage } });
}

describe("guide storage", () => {
  const store = new Map<string, string>();
  const original = Object.getOwnPropertyDescriptor(globalThis, "window");

  beforeEach(() => {
    store.clear();
    stubStorage({
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
    });
  });

  afterEach(() => {
    if (original) Object.defineProperty(globalThis, "window", original);
    else delete (globalThis as { window?: unknown }).window;
  });

  it("keys the overview by version, role and account, and each contextual guide separately", () => {
    expect(guideKey("student", "u1")).toBe(`eduagent.guide.v${GUIDE_VERSION}:student:u1`);
    expect(guideKey("student", "u1", "plan")).toBe(`eduagent.guide.v${GUIDE_VERSION}:student:u1:ctx:plan`);
    expect(guideKey("teacher", "u1")).not.toBe(guideKey("student", "u1"));
  });

  it("remembers the overview and each area guide independently", () => {
    expect(readGuide("student", "u1")).toEqual({ available: true, record: null });
    writeGuide("student", "u1", "overview", "completed", 6);
    writeGuide("student", "u1", "plan", "dismissed", 1);
    const overview = readGuide("student", "u1");
    const plan = readGuide("student", "u1", "plan");
    expect(overview.available && overview.record?.status).toBe("completed");
    expect(plan.available && plan.record?.status).toBe("dismissed");
    expect(readGuide("student", "u1", "discussion")).toEqual({ available: true, record: null });
    expect(readGuide("student", "u2")).toEqual({ available: true, record: null });
    expect(readGuide("teacher", "u1")).toEqual({ available: true, record: null });
  });

  it("ignores a record written by another guide version", () => {
    store.set(guideKey("teacher", "t1"), JSON.stringify({ status: "completed", version: GUIDE_VERSION + 1, at: "", step: 0 }));
    expect(readGuide("teacher", "t1")).toEqual({ available: true, record: null });
  });

  it("treats unreadable storage as unavailable so a guide never auto-starts", () => {
    store.set(guideKey("student", "u1"), "not json");
    expect(readGuide("student", "u1")).toEqual({ available: false });
    stubStorage({ getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
    expect(readGuide("student", "u1")).toEqual({ available: false });
    expect(() => writeGuide("student", "u1", "overview", "completed", 3)).not.toThrow();
  });
});

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "node_modules" ? [] : sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("guide definitions", () => {
  const src = join(process.cwd(), "src");
  const code = sourceFiles(src).map((file) => readFileSync(file, "utf8")).join("\n");

  it("give each role a 5-7 step overview on its home route and short area guides", () => {
    for (const role of ["teacher", "student", "parent"] as const) {
      const overview = overviewOf(role);
      expect(overview.route).toBe(GUIDE_HOME[role]);
      expect(overview.steps.length).toBeGreaterThanOrEqual(5);
      expect(overview.steps.length).toBeLessThanOrEqual(7);
      const ids = GUIDES[role].map((guide) => guide.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const guide of GUIDES[role].filter((item) => item.kind === "context")) {
        expect(guide.steps.length).toBeGreaterThanOrEqual(2);
        expect(guide.steps.length).toBeLessThanOrEqual(4);
        expect(guide.route.startsWith(`/${role}/`)).toBe(true);
        expect(guide.route).not.toBe(GUIDE_HOME[role]);
      }
      expect(contextGuidesFor(role, GUIDE_HOME[role])).toEqual([]);
    }
  });

  it("keeps every step short and bounded", () => {
    for (const guide of Object.values(GUIDES).flat()) {
      for (const step of guide.steps) {
        expect(step.title.length).toBeLessThanOrEqual(42);
        expect(step.text).not.toContain("—");
        expect((step.bullets ?? []).length).toBeLessThanOrEqual(3);
        expect(step.text.length).toBeLessThanOrEqual(320);
      }
    }
  });

  it("only points at targets that exist in the app", () => {
    for (const guide of Object.values(GUIDES).flat()) {
      for (const step of guide.steps) {
        if (step.target.startsWith("nav-")) {
          expect(code).toContain(`path: "/${guide.role}/${step.target.slice(4)}"`);
        } else {
          const present = code.includes(`data-guide="${step.target}"`) || code.includes(`guide="${step.target}"`);
          expect({ guide: guide.id, target: step.target, present }).toEqual({ guide: guide.id, target: step.target, present: true });
        }
      }
    }
  });
});
