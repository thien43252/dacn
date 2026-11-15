import { expect, type Page, test } from "@playwright/test";

/**
 * Feature 003 against running servers with LLM_PROVIDER=fake (see playwright.config.ts). The fake model calls a tool
 * when the message contains `[[tool:NAME {json}]]`, which makes handoffs and questions to people deterministic.
 */

const PASSWORD = "Demo123!";

async function login(page: Page, email: string) {
  const response = await page.request.post("/api/auth/login", { data: { email, password: PASSWORD } });
  expect(response.ok()).toBeTruthy();
  const { user } = await response.json();
  await page.addInitScript((u: { id: string; role: string }) => {
    localStorage.setItem(`eduagent.guide.v1:${u.role}:${u.id}`, JSON.stringify({ status: "dismissed", version: 1, at: "", step: 0 }));
  }, user);
}

async function send(page: Page, text: string) {
  // Wait until the previous turn has finished (the composer shows "send", not "stop").
  await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toBeAttached();
  await page.fill("#chat-input", text);
  await page.keyboard.press("Enter");
}

async function openDirect(page: Page, agentName: RegExp) {
  await page.goto("/student/chat");
  await page.getByRole("button", { name: "Chat với agent" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: agentName }).click();
}

test("direct chat: the tutor asks another agent, the answer appears in a collapsible bar", async ({ page }) => {
  await login(page, "student@demo.edu.vn");
  await openDirect(page, /Gia sư Toán/);
  await send(page, '[[tool:message_agent {"agent": "on-tap-tai-lieu", "task": "Tìm lý thuyết định lý Pytago", "bounds": "ngắn", "good_answer": "có nguồn"}]]');
  const bar = page.getByTestId("handoff-bar").last();
  await expect(bar).toContainText("Ôn tập theo tài liệu lớp");
  await expect(bar).toContainText("Đã trả lời", { timeout: 20_000 });
  await bar.getByRole("button").first().click();
  await expect(bar).toContainText("Tìm lý thuyết định lý Pytago");
});

test("asking a teacher: approval card, inbox, answer back in the origin chat", async ({ browser }) => {
  const student = await browser.newPage();
  await login(student, "student@demo.edu.vn");
  await openDirect(student, /Trợ lý lớp/);
  await send(student, '[[tool:ask_person {"recipient": "homeroom", "question": "Em xin nộp bài muộn 2 ngày vì em ốm", "kind": "approval"}]]');
  await expect(student.getByRole("button", { name: "Cho phép lần này" })).toBeVisible({ timeout: 20_000 });
  await expect(student.getByRole("button", { name: "Luôn cho phép ở đây" })).toHaveCount(0);
  await student.getByRole("button", { name: "Cho phép lần này" }).click();

  const teacher = await browser.newPage();
  await login(teacher, "teacher@demo.edu.vn");
  await teacher.goto("/teacher/inbox");
  const card = teacher.getByRole("group", { name: "Câu hỏi gửi người" }).first();
  await expect(card).toContainText("Em xin nộp bài muộn 2 ngày");
  await card.getByRole("button", { name: "Sửa" }).click();

  await expect(student.getByText("Sửa").last()).toBeVisible({ timeout: 20_000 });
});

test("group: a member's message reaches another member within 2 seconds (SC-008)", async ({ browser }) => {
  const first = await browser.newPage();
  const second = await browser.newPage();
  await login(first, "student@demo.edu.vn");
  await login(second, "student2@demo.edu.vn");
  for (const page of [first, second]) {
    await page.goto("/student/chat");
    await page.getByRole("button", { name: /Ôn thi HK1/ }).click();
  }
  const text = `Chào cả nhóm @Bình ${Date.now()}`;
  await send(first, text);
  const started = Date.now();
  await expect(second.getByText(text)).toBeVisible({ timeout: 5_000 });
  expect(Date.now() - started).toBeLessThan(2_000 + 500);
});
