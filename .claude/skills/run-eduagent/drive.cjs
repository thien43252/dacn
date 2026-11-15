// Playwright helper for EduAgent Hub. See SKILL.md.
const os = require('os'), path = require('path');
const { chromium } = require('c:/project/dacn/web/node_modules/playwright');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173';
const OUT = process.env.DRIVE_OUT || os.tmpdir();
exports.BASE = BASE;
exports.open = async (email, pw = 'Demo123!') => {
  const b = await chromium.launch({ headless: false, channel: 'chrome' }).catch(() => chromium.launch({ headless: false }));
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE + '/login');
  await p.getByPlaceholder('ban@email.com').fill(email);
  await p.locator('input[type=password]').first().fill(pw);
  await p.locator('form button[type=submit], form button:has-text("Đăng nhập")').first().click();
  await p.waitForURL(/\/(student|teacher|parent|admin)\//, { timeout: 15000 });
  return { b, ctx, p };
};
exports.newChat = async (p, role, agent) => {
  await p.goto(`${BASE}/${role}/chat`); await p.waitForTimeout(1500);
  await p.locator('button[aria-label="Chat với agent"]').click(); await p.waitForTimeout(800);
  await p.locator('[role=dialog]').getByText(agent).first().click(); await p.waitForTimeout(2000);
};
exports.send = async (p, text, wait = 12000) => {
  const box = p.locator('textarea').last(); await box.fill(text); await box.press('Enter'); await p.waitForTimeout(300); if ((await box.inputValue()).trim()) await box.press('Enter'); /* @mention popup may swallow the first Enter */ await p.waitForTimeout(wait);
};
exports.tail = async (p, n = 800) => (await p.locator('main').innerText()).slice(-n);
exports.shot = async (p, name) => { const f = path.join(OUT, name + '.png'); await p.screenshot({ path: f }); console.log('shot:', f); return f; };
