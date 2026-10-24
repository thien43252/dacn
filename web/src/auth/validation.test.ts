import { describe, expect, it } from "vitest";

import { validateLogin, validateRegistration } from "./validation";

describe("auth validation", () => {
  it("accepts a valid login", () => {
    expect(validateLogin("student@demo.edu.vn", "Student123!")).toEqual({});
  });

  it("rejects invalid registration fields", () => {
    const errors = validateRegistration("A", "sai-email", "weak", "other");
    expect(errors.name).toBeTruthy();
    expect(errors.email).toBeTruthy();
    expect(errors.password).toBeTruthy();
    expect(errors.confirmPassword).toBeTruthy();
  });
});
