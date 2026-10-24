import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatLauncher } from "./ChatLauncher";

describe("ChatLauncher", () => {
  it("shows the fox under the plain open label while idle", () => {
    const html = renderToStaticMarkup(<ChatLauncher open={false} busy={false} onOpen={() => {}} />);
    expect(html).toContain('aria-label="Mở trợ lý"');
    expect(html).toContain('data-state="idle"');
    expect(html).toMatch(/<span class="mascot" data-mascot="fox" data-mood="idle" aria-hidden="true">/);
    expect(html).toMatch(/fox-directions\.webp/);
    expect(html).not.toContain("chat-fab__typing");
    expect(html).not.toContain("chat-fab__badge");
  });

  it("shows the fox writing with a typing bubble and says so while a reply is running", () => {
    const html = renderToStaticMarkup(<ChatLauncher open={false} busy onOpen={() => {}} />);
    expect(html).toContain('aria-label="Mở trợ lý, đang trả lời"');
    expect(html).toContain('data-state="working"');
    expect(html).toContain('data-mascot="fox" data-mood="writing"');
    expect(html).toContain('<span class="chat-fab__typing" aria-hidden="true"><i></i><i></i><i></i></span>');
    expect(html).toContain('<span class="chat-fab__hint" aria-hidden="true">Đang trả lời…</span>');
  });

  it("stays in the tree but hidden by class while the panel is open", () => {
    const html = renderToStaticMarkup(<ChatLauncher open busy={false} onOpen={() => {}} />);
    expect(html).toContain('class="chat-fab chat-fab--open"');
    expect(html).toContain('aria-expanded="true"');
  });
});
