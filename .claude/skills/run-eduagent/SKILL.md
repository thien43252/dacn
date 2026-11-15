---
name: run-eduagent
description: Launch EduAgent Hub (dev.ps1) and drive it in a real Chrome via Playwright to check UI/features against specs/003 quickstart scenarios. Use when asked to run/open the browser/verify the UI or test scenarios.
---

# Run & drive EduAgent Hub

## 1. Start (skip if already up)
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173   # 200 = web up
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/docs
```
If down: PowerShell `cd c:\project\dacn; .\dev.ps1` (needs Docker Desktop; opens backend/web windows; idempotent seed; ~1 min).
Do NOT read/grep `.env` (blocked by permission classifier).

## 2. Drive with the helper
`drive.cjs` (this folder) uses `web/node_modules/playwright` + system Chrome (headed). No install needed.
```js
const d = require('c:/project/dacn/.claude/skills/run-eduagent/drive.cjs');
const { b, p } = await d.open('student@demo.edu.vn');   // password Demo123!
await d.newChat(p, 'student', 'Trợ lý lớp');            // "Chat với agent" dialog -> pick agent
await d.send(p, 'text');                                // fill + Enter + wait
console.log(await d.tail(p, 800));                      // last chars of <main>
await d.shot(p, 'name');                                // PNG in $DRIVE_OUT or os tmp; then Read it
await b.close();
```
Write scenario scripts in the scratchpad, `node file.cjs`. Batch several steps/roles per script to save turns.

## 3. Facts learned
- Accounts: student@ teacher@ toan@ parent@ student2@ parent2@ admin@demo.edu.vn.
- Routes: /{role}/chat, /{role}/inbox, /teacher/audit, /teacher/classes, /student/builder ...
- Login: landing -> /login; email input is `type=text` (placeholder `ban@email.com`).
- Inbox filter tabs are `role="tab"` (not button). Selectors: new-chat button `button[aria-label="Chat với agent"]`, new-group `button[aria-label="Tạo nhóm"]`, composer placeholder `Đặt câu hỏi`. Do NOT use `aria-label*="agent"` (matches sidebar "Agent Hub"). Dialog: `[role=dialog]`.
- Contact list item text for the first thread "Trợ lý tự chọn agent" preview may contain other agent names: click specific agents via `.last()` or use newChat.
- LLM may be REAL or FAKE: if replies say "chế độ thử nghiệm" it is fake and `[[tool:NAME {json}]]` in a message calls that tool (backend/app/llm/fake.py). With the real LLM, `[[tool:` is ignored; write natural Vietnamese and confirm if the agent asks. Tools: message_agent, ask_person, reply_privately. Safety filter may block injection-like text.
- API (cookie auth): POST /api/auth/login, POST /api/chat/stream {message,class_id,conversation_id}. DB: docker exec eduagent-hub-postgres-1 psql -U eduagent -d eduagent_main.
- Scenario list + expected results: specs/003-agent-group-delegation/quickstart.md section 3.
- Dev DB accumulates chat history across runs; that is expected.
