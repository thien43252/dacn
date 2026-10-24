# Kế hoạch: EduAgent Hub — nền tảng mở multi-agent cho lớp học (đồ án 3 tháng)

## Context
Đồ án cá nhân 12 tuần, chỉ cần demo tốt. Đây là nền tảng B2C: giáo viên tự tạo lớp, thêm học sinh và phụ huynh, rồi cài agent từ Hub vào lớp. Agent có thể do nền tảng làm sẵn hoặc do cộng đồng chia sẻ. Giáo viên có thể tự tạo agent từ tool/MCP của nền tảng, và upload tài liệu để agent dùng RAG.

**Trọng tâm học thuật là "lớp tin cậy":**
- Orchestrator theo lớp, có chính sách lớp (class policy)
- Guardrails 3 lớp
- Certification pipeline: kiểm định tự động trước khi agent được lên Hub

**Ràng buộc:**
- **UI:** tận dụng UI của `C:\project\vsf\team-8\ui-be\web` (React 19 + Vite + plain CSS).
- **Backend, DB, core AI:** viết mới hoàn toàn, không dùng gì từ Platform/BFF của team-8.
- **Thư mục đích:** `c:\project\dacn`, hiện đang trống.

**Đã chốt với người dùng:**
- Đa provider LLM qua một lớp adapter
- LangGraph để orchestration
- Copy `web/` sang rồi cắt gọt

## 1. Cấu trúc repo `c:\project\dacn`
```
web/          # copy từ team-8/ui-be/web (bỏ node_modules, dist, e2e-*), cắt gọt
backend/
  app/
    main.py, config.py, db.py            # FastAPI, Settings (pydantic-settings), SQLAlchemy 2 async
    auth/        # cookie session, RBAC
    classes/     # lớp, thành viên, mã mời, liên kết phụ huynh–học sinh
    agents/      # manifest, version, hub, cài đặt, builder
    knowledge/   # upload, chunk, embed, tìm kiếm (pgvector)
    chat/        # hội thoại, SSE stream
    runtime/     # LangGraph: guard → router → agent → tool guard → output guard
    llm/         # adapter: base.py, openai.py, anthropic.py, gemini.py, embeddings.py
    guard/       # rules (PII, từ khóa), classifier LLM, policy engine
    tools/       # tool registry + MCP server nội bộ (FastMCP)
    certify/     # pipeline kiểm định agent
    reports/     # báo cáo cho phụ huynh/giáo viên
    audit/       # guard_events, usage ledger
  migrations/    # Alembic
  tests/
eval/            # dataset red-team tiếng Việt, routing set, script thực nghiệm
seed/            # 6–8 agent mẫu (YAML manifest), dữ liệu lớp demo
infra/docker-compose.yml   # postgres+pgvector, (tùy chọn) langfuse
docs/            # thiết kế, báo cáo
```

## 2. Tận dụng UI team-8 (file nằm dưới `web/src/`)

**Giữ nguyên, chỉ đổi brand:**
- `styles/tokens.css`, `typography.css`, `global.css`, `controls.css`, `app.css` và fonts trong `assets/fonts`
- `components/Icon.tsx`, `LoadingScreen.tsx`, `AccountPopover.tsx`, `Mascot.tsx` (dùng làm avatar agent), `ChatLauncher.tsx`, `useResizableWidth.ts`
- `agents/Modal.tsx`, `features/shared/ConfirmDialog.tsx`, `SubTabs.tsx`, `StatusBadge.tsx`
- `app/router.ts`: đổi role thành `teacher | student | parent | admin`; thêm parse tham số path, ví dụ `/teacher/classes/:id`
- `auth/*` và `pages/AuthPage.tsx`: giữ cơ chế cookie + `{detail}` error, khớp với FastAPI
- `welcome/*`, `guide/*`: giữ cơ chế, viết lại nội dung

**Sửa lại (adapt):**
- **`components/AppShell.tsx`:** bỏ các hook domain cũ (`usePendingReviews`…); viết lại `navigation` theo 4 role.
- **`pages/WorkspacePage.tsx`:** viết lại `routeMeta` và `renderModule`.
- **Chat:**
  - Giữ `api-client/chatStream.ts` (SSE reader) và `smoothText.ts`.
  - Viết lại `ChatPanel.tsx` (hiện 1890 LOC) thành khoảng 400 LOC, gồm danh sách tin nhắn, composer có @mention và stream.
  - Giữ `chat/MessageBody.tsx`, `QuestionCard.tsx`, `mentions.ts`; bỏ regex tên agent hardcode, lấy danh sách agent từ API.
- **Hub và builder:**
  - Chuyển `agents/AgentLibraryPage` + dialog thành **Hub**: card agent, badge kiểm định, nút cài vào lớp.
  - Chuyển `RegisterAgentDialog`/`EditAgentDialog` thành **Agent Builder** dạng form sinh manifest.
  - Chỉ dùng canvas (`agents/Canvas*`, `canvas/`) nếu còn thời gian, ở tuần 10. Mặc định bỏ.
- **Lớp và tài liệu:**
  - Chuyển layout trong `teacher/*` thành **Teacher dashboard**: danh sách lớp, chi tiết lớp gồm các tab Thành viên / Agent / Tài liệu / Chính sách / Nhật ký.
  - Chuyển `features/student-evidence/EvidencePage` (upload FormData) thành màn **Tài liệu lớp**.
  - Chuyển `history/HistoryTimeline` thành **Nhật ký audit**.
- **`api-client/http.ts`:** gộp với `auth/api.ts` thành một wrapper duy nhất. Viết `api-client/types.ts` mới.

**Bỏ:**
- `plan/`, `feasibility/`, `proposals/`, `customization/`, `features/student-plan`, `features/discussion`, `features/studio`
- `components/teacher/*` (chỉ giữ chart nếu cần)
- Các test e2e cũ

**Viết mới:**
- Màn phụ huynh: `parent/home` (báo cáo con), `parent/chat`
- Màn chọn hoặc tham gia lớp bằng mã
- Màn kết quả kiểm định agent
- Màn chính sách lớp

**Rebrand:**
- `index.html`, `package.json`, `Logo.tsx`, `assets/app-mark.svg`
- Các key `capstone:*` và các chữ "Capstone/Studio"
- Kiểm tra license ảnh trong `assets/illustrations` (theo `ASSET_SOURCES.md`); ảnh nào không rõ license thì thay

## 3. Backend & DB (FastAPI + PostgreSQL/pgvector)

**Bảng chính:**
| Nhóm | Bảng |
|---|---|
| Người dùng | `users`, `sessions`, `consents` (phụ huynh đồng ý cho con dùng) |
| Lớp | `classes` (có `join_code`), `class_members` (role theo lớp: teacher/student/parent), `parent_links` (parent ↔ student), `groups` |
| Agent | `agents` (owner, visibility), `agent_versions` (manifest JSONB, bất biến), `certifications` (score, report JSONB, badge, status), `installations` (version + scope: class/group/personal) |
| Chính sách | `class_policies` (rule JSON: không đưa đáp án, giờ dùng, chủ đề cấm…) |
| Tri thức | `documents`, `chunks` (embedding `vector`, metadata class_id) |
| Hội thoại | `conversations`, `messages`, `tool_calls` |
| Kiểm toán | `guard_events` (stage, verdict, reason), `usage_ledger` (token, cost) |

**API:** tất cả endpoint nằm dưới `/api`, dùng cookie httpOnly để khớp UI.
- **Auth:** `/api/auth/{login,register,logout,session}`
- **Lớp:** `/api/classes` (CRUD), `/api/classes/{id}/members`, `/api/classes/join`, `/api/classes/{id}/policy`
- **Hub và builder:** `/api/hub/agents` (tìm, lọc theo môn/lớp/role), `/api/agents` (builder CRUD), `/api/agents/{id}/versions/{v}/publish` (kích hoạt certify), `/api/installations`
- **Tài liệu:** `/api/classes/{id}/documents` (upload PDF/DOCX → chunk → embed, chạy nền)
- **Chat:** `/api/chat/stream` (SSE; event schema giữ tương thích `chatStream.ts`: `text_delta`, `message_id`, `text_offset`…), `/api/chat/agents?scope=…`
- **Báo cáo và audit:** `/api/parent/children/{id}/report`, `/api/classes/{id}/audit`
- **Tool:** `/api/tools` (registry cho builder)

## 4. Core AI

**Agent manifest:** khai báo bằng Pydantic, không chạy code tùy ý. Gồm các trường:
- `name`, `subject`, `grade`, `target_roles`, `age_range`
- `capabilities[]` (dùng cho định tuyến)
- `tools[]` (chỉ chọn từ registry)
- `knowledge` (class_docs / none)
- `system_prompt`, `examples`

**LLM adapter** (`llm/base.py`):
- Interface gồm `chat(messages, tools, stream)` và `embed(texts)`.
- Có 3 implementation, chọn bằng env `LLM_PROVIDER`.
- Model nhỏ dùng cho guard/router; model mạnh dùng cho agent. Cả hai cấu hình qua env.
- Mỗi lần gọi đều ghi vào `usage_ledger`.

**Runtime graph (LangGraph)** cho mỗi tin nhắn:
```
load_context(class, policy, installed agents, user role)
 → input_guard (rule PII/từ khoá → LLM classifier; vi phạm → refuse + guard_event)
 → router (LLM nhỏ, structured output: chọn agent theo capabilities; @mention ưu tiên; không khớp → fallback "trợ lý lớp")
 → agent_node (system prompt = platform base + class policy + manifest; tool loop)
     ↳ tool_guard trước mỗi tool call (tool ∈ manifest.tools ∧ quyền role ∧ scope class)
 → output_guard (độ phù hợp tuổi, PII, vi phạm policy lớp, "làm hộ bài")
 → persist + stream SSE
```
Class policy được chèn vào mọi agent và được output_guard kiểm tra lại. Đây chính là cơ chế "làm việc ổn định với nhau".

**Tool registry và MCP:** viết MCP server nội bộ bằng FastMCP, client gọi qua MCP Python SDK. Có 5 tool:
- `class_doc_search` (RAG)
- `quiz_generator` (structured output)
- `rubric_grader`
- `math_check` (sympy)
- `progress_summary` (đọc messages/tool_calls của học sinh, dành cho agent phụ huynh/giáo viên)

**RAG:**
- Parse bằng pypdf/python-docx, chunk khoảng 800 token, embed qua adapter, lưu pgvector.
- Lọc theo class_id.
- Coi nội dung tài liệu là dữ liệu, không phải chỉ thị (chống prompt injection).

**Certification pipeline** (`certify/`), chạy nền khi publish:
1. **Kiểm tĩnh manifest:** tool có hợp lệ không, độ tuổi và role có khớp không, prompt có chứa mẫu cấm không.
2. **Red-team động:** chạy khoảng 50 câu lấy từ `eval/redteam_vi.jsonl` qua runtime thật có agent đó.
3. **LLM-judge chấm:** an toàn, đúng vai, không làm hộ bài.
4. **Tổng hợp:** tính score và cấp badge (`certified` / `needs_review` / `rejected`), kèm report giải thích. Chỉ agent `certified` mới hiện cho học sinh/phụ huynh trên Hub.

**Seed agent mẫu (6–8):** Gia sư Toán Socratic, Luyện nói Tiếng Anh, Tạo đề kiểm tra, Chấm văn theo rubric, Trợ lý phụ huynh (báo cáo và cách kèm con), Ôn tập theo tài liệu lớp, Trợ lý lớp (fallback).

## 5. Lộ trình 12 tuần
| Tuần | Việc | Kết quả kiểm chứng |
|---|---|---|
| 1 | Setup repo, docker-compose (pgvector), FastAPI skeleton, Alembic; copy `web/`, rebrand, cắt các folder bỏ, build xanh | `npm run build` OK, `/api/health` OK |
| 2 | Auth cookie + RBAC 4 role; router có param; AppShell mới; viết `eval/redteam_vi.jsonl` (150–300 câu) và `routing_set.jsonl` (100 câu) | Đăng nhập theo role, vào đúng shell |
| 3 | Lớp: tạo lớp, mã mời, thành viên, liên kết phụ huynh, consent; màn Teacher dashboard + chi tiết lớp | Giáo viên tạo lớp, học sinh/phụ huynh join |
| 4 | LLM adapter (3 provider), chat 1 agent qua SSE; ChatPanel mới chạy với `chatStream.ts` | Chat stream được |
| 5 | Upload tài liệu → RAG; MCP server + 5 tool; tool loop trong agent | Agent trả lời trích tài liệu lớp |
| 6 | Manifest + Agent Builder (form) + cài đặt agent vào lớp/nhóm/cá nhân | Giáo viên tạo và cài agent |
| 7 | ⭐ LangGraph runtime: router nhiều agent, class policy, @mention | Lớp có 3 agent và định tuyến đúng |
| 8 | ⭐ Guard 3 lớp + `guard_events` + màn Nhật ký audit | Jailbreak bị chặn và có log |
| 9 | ⭐ Hub + certification pipeline + màn kết quả kiểm định; fork agent | Agent xấu bị reject, có lý do |
| 10 | Màn phụ huynh + `progress_summary`; seed 6–8 agent; (tùy chọn) canvas | Phụ huynh xem báo cáo con |
| 11 | Thực nghiệm: ASR guard (không guard / chỉ prompt / đầy đủ), false positive, routing accuracy, precision/recall của certify (20 agent), latency/cost | Bảng số liệu trong `eval/results/` |
| 12 | Sửa lỗi, kịch bản demo, báo cáo, slide, video dự phòng | Nộp bài |

## 6. Verification
- **Backend:** `pytest backend/tests`. Test guard/router/certify dùng LLM giả (fake adapter) để chạy offline. Lint bằng `ruff`.
- **Frontend:** `npm test` (vitest; chỉ giữ các test của component được giữ lại) và `npm run build`. Thêm 1 Playwright e2e cho luồng demo chính.
- **End-to-end:** `docker compose up` + `uvicorn` + `npm run dev`, rồi chạy tay kịch bản demo:
  1. Giáo viên tạo lớp, mời học sinh/phụ huynh.
  2. Cài "Gia sư Toán" từ Hub, upload tài liệu.
  3. Học sinh xin đáp án → agent chỉ gợi ý; học sinh thử jailbreak → bị chặn và có log.
  4. Phụ huynh xem báo cáo.
  5. Publish agent có prompt độc hại → bị reject.
- **Số liệu:** `python eval/run_redteam.py`, `eval/run_routing.py`, `eval/run_certify.py` xuất ra CSV/markdown.

## Bước đầu tiên khi bắt đầu code (tuần 1)
1. Copy `C:\project\vsf\team-8\ui-be\web` sang `c:\project\dacn\web`, loại trừ `node_modules`, `dist`, `e2e*`, `playwright.*.config.ts`, `vercel.json`.
2. Xóa các folder bỏ và gỡ import trong `AppShell.tsx`/`WorkspacePage.tsx` cho tới khi `tsc` sạch.
3. Tạo skeleton `backend/` và `infra/docker-compose.yml`.
4. `git init`, commit đầu.
