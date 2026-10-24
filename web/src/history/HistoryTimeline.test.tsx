import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HistoryDetailModal, HistoryTimeline } from "./HistoryTimeline";
import { makeEvent } from "./testEvents";

function render(events: Parameters<typeof HistoryTimeline>[0]["events"], showPlanOwner = false): string {
  return renderToStaticMarkup(
    <HistoryTimeline events={events} today="2026-09-26" showPlanOwner={showPlanOwner} onOpenDetail={() => undefined} />,
  );
}

const feasibility = makeEvent({
  id: "f",
  type: "evaluation.feasibility",
  actor: { kind: "agent", name: "Agent Feasibility", agent_id: "feasibility" },
  title: "Đánh giá Feasibility cho Plan v2",
  status: "PASS",
  version_hash: null,
});
const safetyDisabled = makeEvent({
  id: "s",
  type: "evaluation.safety",
  actor: { kind: "agent", name: "Agent Safety", agent_id: "safety" },
  title: "Đánh giá Safety cho Plan v2",
  status: "DISABLED",
  version_hash: null,
});

describe("HistoryTimeline", () => {
  it("renders feasibility and safety as two cards and keeps a disabled agent visible", () => {
    const html = render([feasibility, safetyDisabled]);

    expect(html.match(/<article/g)).toHaveLength(2);
    expect(html).toContain("Agent Feasibility &amp; Capability");
    expect(html).toContain("Agent Policy &amp; Governance");
    expect(html).toContain("Chưa đánh giá, agent đang tắt");
    expect(html.match(/history-badge--success/g)).toHaveLength(1);
    expect(html.match(/history-badge--neutral/g)).toHaveLength(1);
  });

  it("shows actor, version and a details button only when there is detail", () => {
    const html = render([
      makeEvent({ id: "v", detail: [{ label: "Các mốc", items: ["Mốc 1"] }] }),
      makeEvent({
        id: "t",
        type: "team.task_completed",
        category: "team",
        actor: { kind: "member", name: "Phạm Gia Huy", agent_id: null },
        title: "Phạm Gia Huy hoàn thành task",
        status: null,
        version: null,
        version_hash: null,
        plan_owner_name: null,
      }),
    ]);

    expect(html).toContain("Bạn (Minh Anh)");
    expect(html).toContain("Phạm Gia Huy (thành viên nhóm)");
    expect(html.match(/class="history-card__version"/g)).toHaveLength(1);
    expect(html.match(/class="history-card__more"/g)).toHaveLength(1);
  });

  it("names the plan owner in the team scope when someone else acted on it", () => {
    const html = render([feasibility], true);

    expect(html).toContain("Kế hoạch của Minh Anh");
  });

  it("groups cards under day headings", () => {
    const html = render([makeEvent({ occurred_at: "2026-09-26T02:00:00Z" })]);

    expect(html).toContain("Hôm nay");
  });
});

describe("HistoryDetailModal", () => {
  it("is a labelled dialog that reminds evaluations are independent", () => {
    const html = renderToStaticMarkup(
      <HistoryDetailModal event={{ ...safetyDisabled, detail: [{ label: "Kết quả", items: ["Không có model call."] }] }} onClose={() => undefined} />,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("Không có model call.");
    expect(html).toContain("không suy ra kết quả của agent đánh giá còn lại");
  });

  it("describes a new-agent suggestion as a student's text idea", () => {
    const html = renderToStaticMarkup(
      <HistoryDetailModal
        event={makeEvent({
          id: "suggestion-seed-2",
          type: "platform_agent_suggestion.created",
          category: "agent",
          title: "Đề xuất agent mới: Agent gợi ý tài liệu tham khảo",
          summary: "Gợi ý nguồn đáng tin cậy.",
          status: "SUBMITTED",
          plan_owner_name: null,
          version: null,
          version_hash: null,
          detail: [{ label: "Lý do", items: ["Nhóm mất nhiều thời gian tìm nguồn."] }],
        })}
        onClose={() => undefined}
      />,
    );

    expect(html).toContain("Đề xuất agent mới: Agent gợi ý tài liệu tham khảo");
    expect(html).toContain("Bạn (Minh Anh)");
    expect(html).toContain("Đã gửi");
    expect(html).toContain("Nhóm mất nhiều thời gian tìm nguồn.");
    expect(html).toContain("chưa tạo hoặc kích hoạt agent");
    expect(html).not.toContain("Phiên bản");
  });
});
