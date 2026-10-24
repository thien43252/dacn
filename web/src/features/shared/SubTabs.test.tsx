import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubTabs } from "./SubTabs";

describe("sub-tab badge", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a waiting count beside the label without changing the tab's name", () => {
    // SubTabs reads the active tab from the address; the node test environment has no window.
    vi.stubGlobal("window", { location: { pathname: "/teacher/approval", search: "?tab=agent", hash: "" } });
    const html = renderToStaticMarkup(
      <SubTabs
        ariaLabel="Phê duyệt"
        idPrefix="approval-tab"
        tabs={[
          { id: "plan", label: "Kế hoạch", badge: 0, render: () => null },
          { id: "agent", label: "Đề xuất agent", badge: 120, render: () => null },
        ]}
      />,
    );
    expect(html).toContain('aria-describedby="approval-tab-agent-badge"');
    expect(html).toContain('<em class="subtabs__badge" id="approval-tab-agent-badge" aria-hidden="true">99+');
    expect(html).not.toContain("approval-tab-plan-badge");
    expect(html.match(/subtabs__badge/g)).toHaveLength(1);
    expect(html).toContain('aria-selected="true" class="subtabs__tab is-active" id="approval-tab-agent"');
  });
});
