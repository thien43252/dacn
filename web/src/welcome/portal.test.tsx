import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { WelcomePortal } from "./WelcomePortal";
import { aggregate } from "./WelcomeGate";
import { portalForRole, welcomeHeading } from "./portalAssets";
import { endWelcome, getWelcomeSession, startWelcome } from "./welcomeStore";

describe("portal mapping", () => {
  it("maps each real role to its fixed portal", () => {
    expect(portalForRole("student")?.id).toBe("portal-stone-cyan");
    expect(portalForRole("teacher")?.id).toBe("portal-stone-violet");
    expect(portalForRole("admin")?.id).toBe("portal-stone-amber");
  });
  it("never guesses a portal for an unknown role", () => {
    expect(portalForRole(undefined)).toBeNull();
    expect(portalForRole(null)).toBeNull();
    expect(portalForRole("toString")).toBeNull();
    expect(portalForRole("guardian")).toBeNull();
  });
  it("uses the known name or the neutral fallback", () => {
    expect(welcomeHeading("Nguyễn Minh Anh")).toBe("Chào mừng Nguyễn Minh Anh đến với EduAgent Hub!");
    expect(welcomeHeading("  ")).toBe("Chào mừng bạn đến với EduAgent Hub!");
    expect(welcomeHeading(undefined)).toBe("Chào mừng bạn đến với EduAgent Hub!");
  });
});

describe("portal markup", () => {
  it("renders an accessible status with the greeting and loading text", () => {
    const html = renderToStaticMarkup(<WelcomePortal theme={portalForRole("teacher")} name="Cô Hà" leaving={false} slow={false} />);
    expect(html).toContain('role="status"');
    expect(html).toContain('data-portal="portal-stone-violet"');
    expect(html).toContain("Chào mừng Cô Hà đến với EduAgent Hub!");
    expect(html).toContain("Đang chuẩn bị không gian của bạn…");
    expect(html).not.toContain("lâu hơn dự kiến");
    expect(html).not.toContain("<button");
  });
  it("adds the slow notice and the leaving class", () => {
    const html = renderToStaticMarkup(<WelcomePortal theme={portalForRole("admin")} name="" leaving slow />);
    expect(html).toContain("Đang tải lâu hơn dự kiến…");
    expect(html).toContain("welcome-portal--leaving");
    expect(html).toContain("Chào mừng bạn đến với EduAgent Hub!");
  });
  it("shows neutral loading, no artwork and no greeting, for an unknown role", () => {
    const html = renderToStaticMarkup(<WelcomePortal theme={null} name="X" leaving={false} slow={false} />);
    expect(html).toContain('data-portal="neutral"');
    expect(html).not.toContain("welcome-portal__art");
    expect(html).not.toContain("Chào mừng");
  });
});

describe("readiness aggregate", () => {
  it("is pending until the destination is settled", () => expect(aggregate(false, [])).toBe("pending"));
  it("is ready with no declared essential data", () => expect(aggregate(true, [])).toBe("ready"));
  it("waits for every declared source", () => expect(aggregate(true, ["ready", "pending"])).toBe("pending"));
  it("lets an error win over pending so the error UI shows at once", () => expect(aggregate(true, ["pending", "error"])).toBe("error"));
});

describe("welcome session store", () => {
  beforeEach(() => endWelcome());
  it("is empty by default, so a restored session or refresh never plays a welcome", () => expect(getWelcomeSession()).toBeNull());
  it("is created only by an explicit sign-in and cleared on end", () => {
    startWelcome({ id: "u1", role: "student", name: "A" });
    expect(getWelcomeSession()?.userId).toBe("u1");
    endWelcome();
    expect(getWelcomeSession()).toBeNull();
  });
  it("a newer sign-in replaces the older one with a new id", () => {
    startWelcome({ id: "u1", role: "student", name: "A" });
    const first = getWelcomeSession()!.id;
    startWelcome({ id: "u2", role: "admin", name: "B" });
    expect(getWelcomeSession()).toMatchObject({ userId: "u2", role: "admin" });
    expect(getWelcomeSession()!.id).not.toBe(first);
  });
});
