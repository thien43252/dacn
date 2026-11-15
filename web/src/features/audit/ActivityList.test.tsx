import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ActivityRow } from "../../api-client/types";
import { ActivityList } from "./ActivityList";

const at = "2026-11-15T08:00:00Z";

describe("activity list", () => {
  it("shows each refusal with what stopped it and each approval with how it was decided", () => {
    const rows: ActivityRow[] = [
      { type: "handoff", id: "h1", at, status: "refused", from_agent: "gia-su-toan", to_agent: "tien-do", depth: 1, reason: "not_granted" },
      { type: "approval", id: "a1", at, status: "denied", agent: "tro-ly-lop", decided_by: "rule", reason: "ask_person (send): deny rule, do quy tắc r1" },
      { type: "approval", id: "a2", at, status: "allowed", agent: "tro-ly-lop", tool: "ask_person", decided_by: "card", answer: "once" },
      { type: "person_request", id: "p1", at, status: "undeliverable", agent: "tro-ly-lop", kind: "approval" },
    ];
    const html = renderToStaticMarkup(<ActivityList rows={rows} empty="trống" />);
    expect(html).toContain("@gia-su-toan hỏi @tien-do");
    expect(html).toContain("Chưa được cấp quyền giao việc");
    expect(html).toContain("do quy tắc r1");
    expect(html).toContain("Lựa chọn trên thẻ: Cho phép lần này");
    expect(html).toContain("Không đến được ai");
  });

  it("says so when there is nothing yet", () => {
    expect(renderToStaticMarkup(<ActivityList rows={[]} empty="Chưa có gì." />)).toContain("Chưa có gì.");
  });
});
