import { describe, expect, it } from "vitest";

import { canAccessPath, getHomePath, isWorkspacePath, matchPath } from "./router";

describe("role navigation", () => {
  it("returns each role's home", () => {
    expect(getHomePath("teacher")).toBe("/teacher/classes");
    expect(getHomePath("student")).toBe("/student/home");
    expect(getHomePath("parent")).toBe("/parent/home");
    expect(getHomePath("admin")).toBe("/admin/certification");
  });

  it("treats every role prefix as a workspace that needs a login", () => {
    expect(isWorkspacePath("/parent/home")).toBe(true);
    expect(isWorkspacePath("/teacher/classes/abc")).toBe(true);
    expect(isWorkspacePath("/login")).toBe(false);
  });

  it("blocks routes belonging to another role", () => {
    expect(canAccessPath("student", "/student/hub")).toBe(true);
    expect(canAccessPath("student", "/teacher/classes")).toBe(false);
    expect(canAccessPath("parent", "/student/home")).toBe(false);
    expect(canAccessPath("teacher", "/admin/certification")).toBe(false);
  });
});

describe("matchPath", () => {
  it("extracts params", () => {
    expect(matchPath("/teacher/classes/:classId", "/teacher/classes/c%201")).toEqual({ classId: "c 1" });
  });

  it("rejects different shapes", () => {
    expect(matchPath("/teacher/classes/:classId", "/teacher/classes")).toBeNull();
    expect(matchPath("/teacher/classes/:classId", "/teacher/hub/x")).toBeNull();
  });
});
