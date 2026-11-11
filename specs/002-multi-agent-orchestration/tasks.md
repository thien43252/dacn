---

description: "Danh sách task cho feature 002: xử lý yêu cầu nhiều bước với nhiều agent phối hợp"
---

# Tasks: Xử lý yêu cầu nhiều bước với nhiều agent phối hợp

**Input**: Tài liệu thiết kế trong `specs/002-multi-agent-orchestration/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Có. Plan liệt kê các file test và quickstart chạy chúng (`test_orchestrator.py`, `test_orchestrator_resume.py`,
`test_signal_tools.py`, `test_confirm_tools.py`, `test_class_actions.py`). Test backend chạy offline: SQLite in-memory,
`httpx.MockTransport`, fixture ghi từ Dify 1.19.0, không cần Dify. Trong mỗi story, viết test trước và kiểm tra test
fail trước khi làm phần cài đặt.

**Organization**: Task được nhóm theo user story để làm và kiểm thử độc lập từng story.

## Format: `[ID] [P?] [Story] Mô tả`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: story của task (US1…US5)
- Đường dẫn tính từ gốc repo: backend ở `backend/app/`, test ở `backend/tests/`, web ở `web/src/`, DSL Dify ở
  `infra/dify/`, eval ở `eval/`

## Lưu ý chung

- Theo hiến pháp, nguyên tắc II: không chạy `git commit`/`push`. Mọi thay đổi để trong working tree. Mỗi checkpoint
  có thể đề xuất commit message tiếng Anh dạng `type(scope): …`.
- Theo hiến pháp, nguyên tắc I: tài liệu viết tiếng Việt; định danh, API và khóa cấu hình giữ tiếng Anh.
- Mọi lời gọi mô hình đi qua app Dify. Backend chỉ điều phối (research R1).

---

## Phase 1: Setup (spike Dify và khung module)

**Purpose**: Ghi fixture thật từ Dify 1.19.0 và đo mốc độ trễ trước khi đổi triage. Đây là bước 0 của plan.

- [X] T001 Thêm cờ `--latency` vào `eval/run_routing.py`: đo thời gian tới khi triage trả về và thời gian tới chữ đầu tiên (trung vị, p90) trên nhóm câu hỏi đơn giản, ghi `eval/results/routing_latency.csv`. Chạy với Dify **trước khi** sửa triage, lưu kết quả thành `eval/results/routing_latency_baseline.csv` làm mốc cho SC-001
- [ ] T002 Spike trong Dify Studio: thêm vào `eduagent-triage` một nhánh LLM `path` chạy song song với Question Classifier (model `DIFY_TRIAGE_MODEL`, nhiệt độ 0), nối vào node Code gộp cuối. Gọi thật rồi ghi `backend/tests/fixtures/dify/triage_path_full.json` và `backend/tests/fixtures/dify/triage_path_fast.json`. Chạy lại `eval/run_routing.py --latency` để xác nhận trung vị tăng ≤ 10% so với mốc
  - *Tình trạng (2026-11-10)*: DSL `infra/dify/eduagent-triage.yml` đã có nhánh `path` (T024). Fixture hiện là bản **dựng tay**; còn chờ import DSL vào Dify Studio, ghi lại hai fixture từ Dify thật và chạy `--latency`. Mốc đã có: triage p50 2139 ms, chữ đầu p50 3244 ms (56 câu)
- [ ] T003 Spike trong Dify Studio: dựng app Workflow thô `eduagent-planner` (LLM sinh JSON, rồi Code parse) với đúng inputs và outputs ở contracts/dify-apps.md §2. Ghi `backend/tests/fixtures/dify/planner_multi.json`, `planner_missing.json`, `planner_bad_slug.json`, `planner_invalid.json`, `planner_resume_answer.json`, `planner_resume_new_topic.json`
  - *Tình trạng (2026-11-10)*: DSL `infra/dify/eduagent-planner.yml` đã viết và kiểm tra offline (T024, T025). 6 fixture là bản **dựng tay** theo hợp đồng; còn chờ import vào Studio, tạo khóa `DIFY_PLANNER_KEY` và ghi lại từ Dify thật
- [ ] T004 Spike trong Dify Studio: gọi `eduagent-runner` với `conversation_id=""` và một tool tín hiệu tạm qua MCP. Ghi `backend/tests/fixtures/dify/runner_step_note.sse`, `runner_step_signal.sse` (có lời gọi `ask_user`), `runner_step_replaced.sse` (câu trả lời bị kiểm duyệt thay); cập nhật `backend/tests/fixtures/dify/README.md`
  - *Tình trạng (2026-11-10)*: `runner_step_note.sse` và `runner_step_replaced.sse` đã ghi thật (runner hiện có, `conversation_id=""`). `runner_step_signal.sse` là bản **dựng tay**, vì runner chưa bật tool tín hiệu (T076); README fixture đã cập nhật
- [X] T005 [P] Thêm các khóa vào `Settings` trong `backend/app/config.py`: `dify_planner_key=""` (rỗng thì tắt đường đầy đủ), `orch_max_clarify_rounds=1`, `orch_max_questions=3`, `orch_max_steps=5`, `orch_max_agents=3`, `orch_max_replans=1`, `orch_step_timeout_s=60`, `orch_deadline_s=120`, `orch_pending_ttl_h=24`, `orch_share_review_timeout_s=20`, `enable_test_tools=False` (research R12). Thêm các biến tương ứng kèm chú thích tiếng Việt vào `.env.example`
- [X] T006 [P] Tạo package rỗng `backend/app/orchestrator/__init__.py` và `backend/app/class_feed/__init__.py`

---

## Phase 2: Foundational (đường đầy đủ tối thiểu)

**Purpose**: Dữ liệu, rẽ nhánh fast/full, planner, một phần việc tuần tự và bước tổng hợp. Story nào cũng cần phần này.

**⚠️ CRITICAL**: Chưa xong phase này thì chưa làm story nào.

### Dữ liệu

- [X] T007 [P] Tạo `TurnRun` và `RunStep` trong `backend/app/orchestrator/models.py` theo data-model.md:
  - `turn_runs`:
    - `id` String(36) PK
    - `status` String(16) `running · awaiting_user · done · error · cancelled · expired`
    - `conversation_id` FK `conversations.id` ON DELETE CASCADE, index
    - `user_id` FK `users.id` ON DELETE CASCADE
    - `class_id` FK `classes.id` ON DELETE SET NULL, nullable
    - `request_message_id` String(36) (tin nhắn người dùng mở đầu run); `reply_message_id` String(36) nullable (kết quả cuối)
    - `request_text` Text (yêu cầu gốc đã ẩn thông tin cá nhân; dùng khi làm tiếp)
    - `lead_agent` String(48) nullable; `goal` Text default ""
    - `plan` JSON default `{}`; `plan_version` Integer default 1; `pending` JSON nullable
    - `clarify_rounds`, `replans` Integer default 0
    - `assumptions`, `resume_answers`, `confirmations` JSON default `[]`
    - `interactive` Boolean default true; `expires_at` DateTime(tz) nullable
    - `created_at`, `updated_at` DateTime(tz)
    - unique một phần trên `conversation_id` với `status IN ('running','awaiting_user')`, khai báo cả `postgresql_where` và `sqlite_where`
  - `run_steps`:
    - `id` String(36) PK; `run_id` FK `turn_runs.id` ON DELETE CASCADE, index
    - `key` String(16), unique (`run_id`, `key`)
    - `agent_slug` String(48); `agent_version_id` String(36) nullable
    - `title` String(80); `task` Text (mô tả phần việc gửi cho agent); `depends_on` JSON default `[]`
    - `origin` String(16) `plan · help · rerun`; `requested_by` String(16) nullable
    - `status` String(16) `pending · running · done · error · blocked · skipped`
    - `note` Text default "" (≤ 6000 ký tự)
    - `note_review` String(12) default `unreviewed` (`unreviewed · visible · hidden`)
    - `signals`, `citations`, `tools` JSON default `[]`; `error` String(300) nullable
    - `started_at`, `finished_at` DateTime(tz) nullable
- [X] T008 [P] Tạo `ClassAnnouncement` và `Assignment` trong `backend/app/class_feed/models.py` theo data-model.md:
  - `class_announcements`:
    - `class_id` FK ON DELETE CASCADE, index; `author_id` FK `users.id` ON DELETE SET NULL, nullable
    - `title` String(120); `body` Text ≤ 2000 ký tự
    - `audience` String(16) `students · parents · all`; `source` String(16) `agent · ui`
    - `run_id` nullable; `created_at` index
  - `assignments`:
    - `title` String(120); `instructions` Text ≤ 1000 ký tự, default ""
    - `questions` JSON 1–20 phần tử `[{question ≤ 500, options?: string[] ≤ 6}]`
    - `answer_key` JSON nullable; `due_at` DateTime(tz) nullable
    - `source` `agent · ui`; `run_id` nullable; `created_at` index
- [X] T009 [P] Thêm cột `path` String(8), nullable (`fast · full`) vào model `usage_ledger` trong `backend/app/chat/models.py`
- [X] T010 Thêm `orchestrator.models` và `class_feed.models` vào `backend/app/models.py` (phụ thuộc T007, T008)
- [X] T011 Viết migration `backend/migrations/versions/0008_orchestration.py`:
  - tạo `turn_runs` (kèm unique index một phần), `run_steps`, `class_announcements`, `assignments`
  - thêm `usage_ledger.path`
  - có `downgrade` đầy đủ
  - kiểm tra bằng `uv run alembic upgrade head` rồi `downgrade -1`
  - phụ thuộc T007–T010
- [X] T012 [P] Thêm `multi_step: bool = True` vào `PolicyModel` trong `backend/app/classes/schemas.py`. Lớp cũ không có khóa thì hiểu là `true`. `GET/PUT /api/classes/{id}/policy` trả và nhận được trường này; chỉ giáo viên sửa được (contracts/chat-sse.md)
- [X] T013 Sửa `record_usage()` trong `backend/app/chat/router.py`: nhận và ghi `path`. Các purpose mới `planner`, `step`, `synthesis`, `note_review` ghi được mà không đổi kiểu cột. Thêm nhóm theo `path` vào `backend/app/reports/service.py`, và dùng nó trong báo cáo `/admin/usage` ở `backend/app/audit/router.py` (FR-042)
  - *Ghi chú khi làm*: báo cáo sử dụng nằm trong `audit/router.py` (`reports/service.py` là báo cáo hoạt động học sinh), nên nhóm `by_path` được thêm thẳng ở đó; web hiện thêm bảng "Đường xử lý" ở trang báo cáo của admin

### Runtime và tool

- [X] T014 Tách `_stream_runner()` khỏi `_answer()` trong `backend/app/runtime/dify_turn.py` (research R8). Hàm nhận agent, `system_prompt`, `query` và `conversation_id`; stream `agent`, `text_delta`, `text_reset`, `tool`, `citations`; trả về text và usage cuối. Không đổi hành vi: `uv run pytest tests/test_runtime_dify.py tests/test_chat.py` phải pass nguyên trạng
- [X] T015 Mở rộng `backend/app/tools/registry.py` theo data-model.md:
  - `PlatformTool` thêm `requires_confirmation: bool = False`, `signal: bool = False`, `confirm_template: str = ""`, `preview: Callable | None = None`, `share_review: bool = False`
  - `ToolContext` thêm `step_key: str | None`, `mode: Literal["fast","step","synthesis"] = "fast"`, `signals: list[dict]`, `may_request_help: bool = False`
  - `_emit()` thêm `step_key` vào sự kiện `tool`
  - `deny_reason()` thêm bước 2a (tool `signal=True` chỉ khi `mode=="step"`, lý do "Công cụ này chỉ dùng trong phần việc của quá trình nhiều bước.") và bước 2b (tool `signal=True` không cần có trong manifest), theo contracts/mcp-tools.md
- [X] T016 [P] Trong `backend/app/runtime/dify_client.py`:
  - thêm `TriageResult.path`; giá trị lạ hoặc rỗng thì là `"fast"`
  - thêm `run_planner()` (Workflow blocking, khóa `DIFY_PLANNER_KEY`, `user=<users.id>`, timeout `DIFY_TIMEOUT_S`) trả `PlannerResult(ok, plan: dict, usage)`
  - usage lấy từ `data.total_tokens`, purpose `planner`
- [X] T017 [P] Trong `backend/app/runtime/prompts.py`, thêm `planner_roster(agents)`: trả JSON `[{slug, name, description, capabilities, subjects, tools, is_fallback}]`, chỉ gồm agent dùng được với vai trò hiện tại
- [X] T018 Viết `backend/app/orchestrator/planner.py`: `plan_request(...)` gọi `run_planner()` với inputs `query, role, roster, requested_agent, history` (tối đa 6 tin, mỗi tin ≤ 500 ký tự, tổng ≤ 3000), `resume, interactive, can_ask, limits`. Sau đó áp **toàn bộ** bảng kiểm tra ở contracts/dify-apps.md §2:
  - kết quả không dùng được (`ok`, JSON) → `None`, tức quay về đường nhanh
  - `lead` thuộc roster, và bằng `requested_agent` nếu có
  - slug lạ → đổi thành `lead`
  - `key` trùng hoặc phụ thuộc lỗi → bỏ; có vòng → `None`
  - cắt theo `max_steps` và `max_agents` theo thứ tự topo
  - `missing` ≤ `max_questions`, câu ≤ 200 ký tự, ≤ 6 lựa chọn
  - `interactive=false` hoặc `can_ask=false` → `missing` và `confirm_interpretation` chuyển thành `assumptions`
  - `steps` rỗng → một phần việc cho `lead` với `task = goal`
  - `title` ≤ 80 ký tự, trúng từ khóa → "Phần việc của <tên agent>"
- [X] T019 [P] Viết `backend/app/orchestrator/prompts.py`:
  - khối `STEP_MODE` (phần việc nội bộ, viết ghi chú cho agent chính, không chào hỏi, cần gì thì gọi tool tín hiệu rồi dừng)
  - khối `SYNTHESIS_MODE`: ngắn gọn, ≤ 300 từ trừ khi tạo nội dung dài; nêu giả định; không chép nguyên văn ghi chú; nêu phần chưa làm được và kết quả xác nhận
  - `build_step_query()` gồm mục tiêu, phần việc, ghi chú phụ thuộc, yêu cầu gốc
  - `build_synthesis_query()` gồm yêu cầu gốc và "Thông tin bổ sung"
  - `build_synthesis_prompt()` cắt mỗi ghi chú còn `floor(6000 / số phần việc)` ký tự để `system_prompt` ≤ 12000
- [X] T020 Viết `run_step()` trong `backend/app/orchestrator/steps.py` (research R4):
  - gọi runner với `conversation_id=""`, `system_prompt` = `build_system_prompt(agent của phần việc)` + `STEP_MODE` + `policy_block`
  - mỗi phần việc có `ToolContext` riêng (`mode="step"`, `step_key`, quyền tool của agent đó)
  - đọc hết stream thành `note` (≤ 6000 ký tự) và `citations`; ghi `tools`, `signals`
  - kiểm duyệt runner `replace` hoặc câu cài sẵn → `status="blocked"`, kèm `guard_events` stage `step` có `agent_slug` của phần việc (FR-043)
  - hết `orch_step_timeout_s` → `error`
  - lưu `task_id` từ sự kiện `start` của runner vào tập `task_id` dùng chung của run, bỏ ra khi phần việc kết thúc, để T041 gọi `stop` được
  - usage purpose `step`, `path="full"`
  - chưa có DAG: phase này chạy tuần tự
- [X] T021 Viết `backend/app/orchestrator/conductor.py` phần chạy một mạch:
  - tạo `TurnRun`, phát `step{key:"analyze", status:"running"}` trước khi gọi planner (SC-006)
  - planner → `plan` event → chạy từng phần việc, phát `step` event, ghi `run_steps`
  - `step{key:"synthesis"}`, rồi bước tổng hợp qua `_stream_runner()` trên hội thoại Dify chính của `lead`, với purpose `synthesis`
  - `_review()`, gợi ý câu hỏi và `_store()` như đường nhanh
  - `meta` có `path="full"` và `run_id`
  - run chuyển `done` hoặc `error`; mọi phần việc lỗi → thông báo lỗi thân thiện, không có kết quả nửa vời
  - planner trả `None` → giao lại cho đường nhanh (FR-006)
- [X] T022 Rẽ nhánh trong `backend/app/runtime/dify_turn.py` (research R2):
  - đi đường đầy đủ chỉ khi đủ cả 5 điều kiện: `verdict=="allow"`, `path=="full"`, `kind=="chat"` (hoặc `force_path` nội bộ của eval), `policy.multi_step` khác `false` (không gian cá nhân luôn bật), có `dify_planner_key`
  - phát hiện dấu hiệu tự làm hại → luôn giữ luồng hiện tại (FR-038)
  - `done` thêm `path`; tin nhắn đường nhanh có `meta.path="fast"` và usage `path="fast"`
- [X] T023 [P] Thêm `orchestrator: "on" | "off"` (`off` khi thiếu `dify_planner_key`) vào `/api/health` trong `backend/app/main.py`; cập nhật `backend/tests/test_health.py`
- [X] T024 [P] Thêm nhánh `path` song song (prompt theo contracts/dify-apps.md §1, phân vân thì `fast`) và output `path` vào `infra/dify/eduagent-triage.yml`. Xuất DSL hoàn chỉnh của `infra/dify/eduagent-planner.yml` từ app ở T003
- [X] T025 [P] Trong `backend/tests/test_dify_dsl.py`: kiểm tra triage có output `path`, planner có đủ inputs `query, role, roster, requested_agent, history, resume, interactive, can_ask, limits` và outputs `ok`, `plan`
- [X] T026 Viết `backend/tests/test_orchestrator.py`, phần nền, dùng fixture ở T002–T004 qua `backend/tests/dify_fake.py`:
  - chọn đường theo đủ 5 điều kiện (mỗi điều kiện sai → `fast`)
  - mọi quy tắc kiểm tra của planner, mỗi quy tắc một ca
  - `planner_invalid.json` → đường nhanh
  - kế hoạch một phần việc → có `plan`, `step`, kết quả tổng hợp
  - usage có `planner`, `step`, `synthesis` với `path="full"`
- [X] T027 [P] Trong `web/src/api-client/types.ts`: thêm kiểu sự kiện `plan`, `step`, `ask`; `done.status` thêm `awaiting_user`, `done` thêm `path` và `contributors`; `tool.step_key`; các khóa `meta` (`path, run_id, contributors, process, assumptions, ask`); `ClassPolicy.multi_step`. Cập nhật parse trong `web/src/api-client/chatStream.ts` và `web/src/api-client/chatStream.test.ts`

**Checkpoint**: Câu hỏi đơn giản đi đường nhanh như cũ. Yêu cầu phức tạp đi planner, một hoặc vài phần việc tuần tự, rồi một kết quả cuối. Toàn bộ test cũ vẫn pass.

---

## Phase 3: User Story 1 — Hỏi lại khi thiếu thông tin quan trọng (Priority: P1) 🎯 MVP

**Goal**: Yêu cầu mơ hồ được hỏi lại đúng một lần (≤ 3 câu, có lựa chọn, có "Cứ làm luôn"). Trả lời xong thì làm tiếp mà không bắt nhắc lại yêu cầu. Yêu cầu đã rõ thì không hỏi.

**Independent Test**: Quickstart kịch bản 2–6, 13–15, 19. Gửi "làm đề ôn tập cho em" thì nhận thẻ câu hỏi; trả lời xong kết quả dùng đúng câu trả lời. Gửi "giải giúp em bước đầu của 2x + 3 = 7" thì được trả lời ngay.

### Tests cho User Story 1 ⚠️

- [ ] T028 [P] [US1] Viết `backend/tests/test_orchestrator_resume.py`, mỗi trường hợp một ca:
  - `planner_missing.json` → `ask` rồi `done(awaiting_user)`, run `awaiting_user`, tin nhắn câu hỏi có `meta.ask.state="open"`
  - `reply.answers` → làm tiếp, `resume_answers` được lưu, các phần việc đã xong giữ nguyên
  - `skip_all` → `assumptions` có trong `meta` và trong prompt tổng hợp
  - gõ ô chat chính và planner trả `answers_pending=false` → `notice(pending_cancelled)`, run `cancelled`
  - đã hỏi một lần → `can_ask=false`, không hỏi lần hai
  - `expires_at` trong quá khứ → `notice(pending_expired)`, run `expired`, tin nhắn xử lý như yêu cầu mới
  - giáo viên tắt `multi_step` trong lúc chờ → `cancelled` và đi đường nhanh
  - tin trả lời bị triage chặn → `cancelled`
  - phụ huynh rút đồng ý → cổng đồng ý chặn, run `cancelled`
  - `reply.run_id` sai → bỏ qua `reply`
  - mỗi hội thoại tối đa một run mở
  - `kind` certify hoặc sandbox → `interactive=false`, không bao giờ dừng
  - planner trả `confirm_interpretation` → dừng với `kind="confirm"`, `source="interpretation"`, `clarify_rounds` tăng; "Không" → run `cancelled`, không chạy phần việc nào; có cả `missing` thì chỉ hỏi `missing`, câu xác nhận thành giả định (FR-017, research R7)
  - làm tiếp sau khi tải lại trang (SC-010): lấy lịch sử qua `GET /api/chat/conversations/{id}/messages`, đọc `meta.ask.run_id` của tin nhắn câu hỏi, gửi `reply` với `run_id` đó → làm tiếp bình thường
- [ ] T029 [P] [US1] Viết test `AskCard` trong `web/src/components/chat/chat.test.tsx`:
  - chọn lựa chọn, gõ tự do, "Cứ làm luôn" gửi `skip_all`
  - sau khi gửi thì thẻ khoá; chỉ thẻ `open` mới nhất bấm được
  - dựng thẻ từ `meta.ask` của lịch sử tải lại (SC-010) và gửi `reply` đúng `run_id`

### Implementation cho User Story 1

- [ ] T030 [US1] Thêm `ReplyIn` vào `ChatIn` trong `backend/app/chat/router.py`: `run_id: str`, `answers: dict[str, constr(max_length=500)] = {}`, `skip_all: bool = False`, `decision: Literal["approve","reject"] | None = None`. `message` vẫn bắt buộc (contracts/chat-sse.md)
- [ ] T031 [US1] Thêm `pause_for_clarify()` vào `backend/app/orchestrator/conductor.py`:
  - chỉ dừng khi `interactive=true` và `clarify_rounds < orch_max_clarify_rounds`
  - kế hoạch có `missing` → hỏi `missing`. Kế hoạch không có `missing` nhưng có `confirm_interpretation` → dừng **trước khi chạy phần việc** với `pending.kind="confirm"`, `confirm.source="interpretation"`, `confirm.summary` = câu đó; vẫn tăng `clarify_rounds` (FR-017). Có cả hai → chỉ hỏi `missing`, câu xác nhận đưa vào `assumptions` (research R7)
  - tạo `ChatMessage` trợ lý với `status="awaiting_user"` và `meta.ask={run_id, kind:"clarify", questions, state:"open"}`
  - đặt `pending` (định dạng ở data-model.md: `kind`, `ask_message_id`, `step_key`, `questions[{id, question, options}]`), `clarify_rounds += 1`, `expires_at = now + orch_pending_ttl_h`
  - phát `plan` rồi `ask` (`skippable=true`) rồi `done(awaiting_user)`
- [ ] T032 [US1] Thêm `resume()` vào `backend/app/orchestrator/conductor.py`:
  - tìm run mở của hội thoại và kiểm tra hết hạn lười
  - lớp đã tắt `multi_step` → `cancelled`
  - ẩn thông tin cá nhân từng giá trị trong `answers`
  - gọi planner với `resume={goal, questions:[{question, answer}], skipped, done_steps, new_message}`
  - `answers_pending=false` → huỷ (FR-012)
  - agent trong kế hoạch không còn dùng được → lập lại kế hoạch với roster hiện tại
  - phát `plan(resumed=true)` kèm trạng thái các phần việc đã có, chạy tiếp các phần chưa xong
  - rời `awaiting_user` theo bất kỳ hướng nào → `pending=null`, `expires_at=null`, cập nhật `meta.ask.state` (`answered · skipped · cancelled · expired`)
- [ ] T033 [US1] Nối `reply` và run đang chờ vào `backend/app/runtime/dify_turn.py`:
  - cổng đồng ý, ẩn thông tin cá nhân và triage chạy trước như mọi tin nhắn (FR-037); bị chặn → run `cancelled`
  - có run `awaiting_user` → `resume()`, kể cả khi triage trả `fast`
  - phát `notice(pending_expired)` và `notice(pending_cancelled)` với câu chữ ở contracts/chat-sse.md
  - tin nhắn người dùng có `meta.reply_to={run_id, ask_message_id}`
- [ ] T034 [US1] Đưa `assumptions` và `resume_answers` vào `build_synthesis_prompt()` và `build_synthesis_query()` trong `backend/app/orchestrator/prompts.py`; lưu `meta.assumptions` trong `backend/app/orchestrator/conductor.py`
- [ ] T035 [US1] Chế độ không có người thật (research R14): `kind` certify/sandbox và eval gửi `interactive=false`. Thêm `force_path` chỉ dùng nội bộ (không có trong `ChatIn` công khai) vào `run_turn()` ở `backend/app/runtime/engine.py` và `backend/app/chat/router.py`
- [ ] T036 [US1] Tạo `web/src/components/chat/AskCard.tsx` chuyển thể từ `web/src/components/chat/QuestionCard.tsx`:
  - bỏ danh sách trường bắt buộc kiểu "brief"
  - giữ điều hướng từng câu và phím số chọn lựa chọn
  - thêm nút "Cứ làm luôn"
  - gửi một lần rồi khoá
  - xoá `QuestionCard.tsx` nếu không còn chỗ nào dùng
- [ ] T037 [US1] Sửa `web/src/components/chat/ChatThread.tsx`:
  - xử lý `step(analyze)` (hiện "Đang phân tích yêu cầu" qua `web/src/components/chat/thinking.ts`), `ask`, `done(awaiting_user)`
  - gửi `reply` kèm `message` ghép "câu hỏi\ncâu trả lời" (hoặc "Cứ làm luôn")
  - dựng lại thẻ từ `meta.ask` khi mở lại hội thoại; ô chat chính vẫn gõ được khi đang chờ
  - thêm kiểu cho thẻ vào `web/src/styles/chat-experience.css`
- [ ] T038 [P] [US1] Thêm công tắc "Xử lý nhiều bước (nhiều agent phối hợp, hỏi lại khi thiếu thông tin)" vào `web/src/features/classes/PolicyTab.tsx` (FR-046)

**Checkpoint**: MVP. Hệ thống biết hỏi lại, có bước phân tích và chạy được với một agent. Kiểm chứng bằng quickstart kịch bản 2–6, 13–15, 19.

---

## Phase 4: User Story 2 — Nhiều agent cùng đóng góp, một kết quả ngắn gọn (Priority: P1)

**Goal**: Kế hoạch giao phần việc cho các agent phù hợp, kể cả agent không được gọi tên. Phần việc độc lập chạy song song. Agent chính tổng hợp một kết quả có trích nguồn và tên các agent đóng góp.

**Independent Test**: Quickstart kịch bản 1, 7, 8, 12, 16. Gửi yêu cầu Pytago "theo tài liệu cô gửi rồi cho em một bài luyện" thì có ≥ 2 agent tham gia, một kết quả ≤ 300 từ có trích nguồn và chip tên các agent đóng góp.

### Tests cho User Story 2 ⚠️

- [ ] T039 [P] [US2] Thêm vào `backend/tests/test_orchestrator.py`, mỗi trường hợp một ca:
  - `planner_multi.json`: phần việc cùng tầng chạy đồng thời, phần việc phụ thuộc nhận ghi chú của phần nó cần
  - phần việc quá `orch_step_timeout_s` → `error`, các phần khác vẫn xong, kết quả nêu phần chưa làm được
  - phụ thuộc vào phần `error/blocked/skipped` vẫn chạy với ghi chú "phần X không có kết quả"
  - hết `orch_deadline_s` → phần còn lại `skipped`
  - `@mention` → agent đó là `lead`
  - `contributors` không chứa `lead`
  - trích dẫn là hợp của các phần việc
  - client ngắt kết nối → task group bị huỷ, gọi `stop` của Dify cho mọi `task_id`, run `cancelled`
  - phần việc `blocked` ghi `guard_events` có `agent_slug` của phần việc

### Implementation cho User Story 2

- [ ] T040 [US2] Thêm `run_plan()` vào `backend/app/orchestrator/steps.py` (FR-019, FR-026):
  - chạy DAG theo tầng topo bằng `asyncio.TaskGroup`
  - mỗi phần việc một `ToolContext` riêng
  - phụ thuộc lỗi → ghi chú "phần X không có kết quả" rồi vẫn chạy
  - kiểm tra `orch_deadline_s` trước mỗi tầng, hết thì `skipped`
  - phát `step` event khi bắt đầu và kết thúc, kèm `duration_ms`
  - thay vòng tuần tự ở T021 bằng `run_plan()`
- [ ] T041 [US2] Xử lý rời đi giữa chừng trong `backend/app/orchestrator/conductor.py` (research R16, FR-040): bắt `CancelledError` hoặc ngắt kết nối của generator SSE, huỷ task group, gọi `DifyClient.stop` cho mọi `task_id` đang chạy, run `cancelled`
- [ ] T042 [US2] Trong `backend/app/orchestrator/conductor.py`:
  - tính `contributors` (`[{slug, name, avatar}]` các agent có phần việc `done`, trừ `lead`) và đưa vào `done` cùng `meta.contributors`
  - gộp `citations` của mọi phần việc và bước tổng hợp vào `meta.citations` (FR-029)
  - phát `agent(lead)` trước khi stream kết quả
- [ ] T043 [P] [US2] Thêm span `plan`, `step:<key>` (loại `agent`) và `synthesis` dưới trace của lượt, dùng `backend/app/tracing.py` trong `backend/app/orchestrator/conductor.py` và `backend/app/orchestrator/steps.py` (research R13)
- [ ] T044 [US2] Hiển thị chip tên và avatar các agent đóng góp từ `meta.contributors` dưới kết quả cuối trong `web/src/components/chat/MessageBody.tsx`, dùng `web/src/agents/AgentIcon.tsx`

**Checkpoint**: US1 và US2 đều chạy độc lập. Kiểm chứng bằng quickstart kịch bản 1, 7, 8, 12, 16.

---

## Phase 5: User Story 3 — Xem quá trình làm việc ở dạng gọn (Priority: P2)

**Goal**: Khung tiến trình cập nhật theo thời gian thực, thu gọn thành "Đã làm việc · N agent · X giây" khi xong và mở lại được, kể cả sau khi tải lại trang. Ghi chú từng phần việc chỉ hiện sau khi qua kiểm duyệt.

**Independent Test**: Quickstart kịch bản 9–11. Mở một phần việc thì thấy ghi chú (lần đầu chạy review). Lớp cấm đưa đáp án thì ghi chú có lời giải bị ẩn. Tải lại trang thì dòng tóm tắt vẫn còn.

### Tests cho User Story 3 ⚠️

- [ ] T045 [P] [US3] Viết test cho `GET /api/chat/messages/{message_id}/steps/{step_key}/note` trong `backend/tests/test_orchestrator.py`:
  - người khác chủ hội thoại → 404
  - lần đầu chạy review rồi lưu `note_review`; lần sau không gọi review
  - review lỗi → `hidden` và không lưu
  - kết quả cuối bị chặn → mọi ghi chú `hidden`
  - giáo viên chỉ qua kiểm duyệt từ khóa, không gọi review
  - bị chặn → `guard_events` stage `step_note`, `detector="dify_review"`, `agent_slug` của phần việc
  - phần việc lỗi hoặc bỏ qua → `unavailable`
- [ ] T046 [P] [US3] Viết test `ProcessPanel` trong `web/src/components/chat/chat.test.tsx`: cập nhật theo `plan`/`step`/`tool{step_key}`; thu gọn khi có `done`; dựng lại từ `meta.process`; ghi chú `hidden` hiện "Nội dung này đã được ẩn"

### Implementation cho User Story 3

- [ ] T047 [US3] Lưu `meta.process={duration_ms, agents, steps:[{key, title, agent, status}]}` vào tin nhắn kết quả cuối trong `backend/app/orchestrator/conductor.py` (FR-035)
- [ ] T048 [US3] Viết `backend/app/orchestrator/notes.py` theo research R9:
  - `review_note()` theo thứ tự: kết quả cuối bị chặn → `hidden`; đã có `note_review` → trả luôn; chưa có thì chạy `dify_rules.contains_blocked_keyword`, rồi `eduagent-review` với `role` và `no_direct_answers` của người xem và lớp (giáo viên bỏ qua review)
  - lưu `visible` hoặc `hidden`; review lỗi thì không lưu
  - usage purpose `note_review`
- [ ] T049 [US3] Thêm endpoint `GET /api/chat/messages/{message_id}/steps/{step_key}/note` vào `backend/app/chat/router.py`, gọi `notes.review_note()`. Response `{key, title, agent, status, visibility, note, citations}`; `hidden` kèm `reason_text` "Nội dung này đã được ẩn" (contracts/chat-sse.md)
- [ ] T050 [P] [US3] Thêm hàm `stepNote(messageId, stepKey)` vào `web/src/api-client/agents.ts`, cạnh hàm `messages()` của chat đã có ở đó
- [ ] T051 [US3] Tạo `web/src/components/chat/ProcessPanel.tsx`:
  - danh sách phần việc với avatar, tên agent, tiêu đề và trạng thái (chờ, đang làm, xong, lỗi, bỏ qua), tool gắn theo `step_key`
  - thu gọn thành "Đã làm việc · N agent · X giây" khi có `done`, bấm để mở
  - mở một phần việc thì tải ghi chú (kèm trạng thái đang tải)
- [ ] T052 [US3] Nối `ProcessPanel` vào `web/src/components/chat/ChatThread.tsx` (sự kiện `plan`, `step`, `tool.step_key`) và `web/src/components/chat/MessageBody.tsx` (dựng lại từ `meta.process` khi mở hội thoại cũ). Đường nhanh không hiện khung. Thêm kiểu vào `web/src/styles/chat-experience.css`

**Checkpoint**: Quickstart kịch bản 9–11 đạt.

---

## Phase 6: User Story 4 — Xin xác nhận trước những việc quan trọng (Priority: P2)

**Goal**: Tool `requires_confirmation` không bao giờ chạy khi chưa có "Đồng ý" cho đúng lần gọi đó. Backend tự chạy tool đúng một lần với đúng tham số đã xem trước. Kèm 5 tool giáo viên có tác dụng ra ngoài (R18).

**Independent Test**: Quickstart kịch bản 18, 20–29. Giáo viên nhờ "giao cho cả lớp": trước khi đồng ý học sinh không thấy bài; sau "Đồng ý" bài có đúng nội dung đã xem trước; "Không" thì không có gì được tạo; bấm hai lần chỉ tạo một bài.

### Tests cho User Story 4 ⚠️

- [ ] T053 [P] [US4] Viết `backend/tests/test_signal_tools.py` với `test_confirm_probe_*`:
  - lần gọi chưa xác nhận → không chạy, `tool_calls.denied_reason="awaiting_confirmation"`
  - đường nhanh gọi tool cần xác nhận → nâng lên run để dừng hỏi, kể cả khi lớp tắt `multi_step`
  - "Đồng ý" → chạy đúng `args` đã lưu, đúng một lần: gửi lại `reply` approve **tuần tự** lần thứ hai thì bỏ qua. Test chạy trên SQLite nên không kiểm được tranh chấp đồng thời thật; trường hợp đó kiểm thủ công bằng quickstart kịch bản 28 trên Postgres
  - "Đồng ý" sau khi handle cũ đã hết hạn (đẩy đồng hồ của `backend/app/tools/context.py` qua 600 giây) → vẫn chạy với `ToolContext` dựng lại, `dataset_id` lấy từ lớp hiện tại
  - "Không", hết hạn, gõ tin khác khi đang chờ xác nhận → không chạy, `confirmations[].decision` đúng
  - `interactive=false` → coi là "Không"
  - xác nhận không tăng `clarify_rounds`
  - `request_confirmation` ngoài `mode="step"` bị từ chối và tính như một lần hỏi lại
  - `confirm_probe` chỉ có khi `enable_test_tools=True`
- [ ] T054 [P] [US4] Viết `backend/tests/test_confirm_tools.py` cho 5 tool:
  - học sinh và phụ huynh bị từ chối theo vai trò
  - giáo viên không thuộc lớp bị từ chối (bước 6a)
  - kiểm duyệt chia sẻ trúng → lỗi tool, `guard_events` category `share_blocked`, không có yêu cầu xác nhận
  - review quá `orch_share_review_timeout_s` hoặc lỗi (MockTransport trả chậm hoặc 500) → fail closed: lỗi "Chưa kiểm duyệt được nội dung, thử lại sau.", `share_blocked` với `detector="timeout"`, không có yêu cầu xác nhận
  - `preview` đúng nội dung và `audience_count`
  - sau "Đồng ý" tạo đúng bản ghi và `result_ref`
  - quyền bị thu hồi trong lúc chờ → không chạy
  - `set_agent_notes` không chạm khóa khác của `policy`
  - `install_agent` với agent đã cài → "đã có sẵn"
  - `answer_key` không được gửi đi review
- [ ] T055 [P] [US4] Viết `backend/tests/test_class_actions.py` cho API ở contracts/class-actions.md:
  - học sinh chỉ thấy thông báo `students/all`; phụ huynh chỉ thấy `parents/all` của lớp có con
  - `answer_key` chỉ giáo viên thấy
  - chỉ giáo viên của lớp được `POST` thông báo và `DELETE`; người ngoài lớp → 404

### Implementation cho User Story 4: cơ chế xác nhận

- [ ] T056 [US4] Thêm bước 7 vào `run_tool()` trong `backend/app/tools/registry.py`:
  - tool `requires_confirmation` không chạy
  - ghi `tool_calls` với `denied_reason="awaiting_confirmation"`
  - thêm tín hiệu `{type:"confirm_tool", tool, args, summary}`; `summary` dựng từ `confirm_template` và tham số, không do LLM viết
  - trả "Cần người dùng xác nhận trước khi thực hiện; hệ thống sẽ hỏi. Hãy kết thúc phần việc."
  - áp dụng ở mọi `mode`
  - đăng ký `confirm_probe` (`target` ≤ 100, `note` ≤ 300, mọi vai trò, template "Ghi một thông báo thử tới “{target}”: {note}") chỉ khi `enable_test_tools`
- [ ] T057 [P] [US4] Thêm `request_confirmation` (`summary` 10–400 ký tự, `signal=True`) vào `backend/app/tools/impl.py` và đăng ký kèm `ctx` trong `backend/app/tools/server.py`
- [ ] T058 [US4] Thêm `pause_for_confirm()` vào `backend/app/orchestrator/conductor.py`:
  - đọc tín hiệu `confirm_tool` (hoặc `request_confirmation` với `source="interpretation"`, tính vào `clarify_rounds`)
  - đặt `pending.confirm={tool, agent, args, summary, impact, source, preview, audience_count}` (`agent` là slug agent đã gọi tool, dùng khi dựng lại ngữ cảnh ở T059)
  - tạo tin nhắn câu hỏi `meta.ask.kind="confirm"`, phát `ask{kind:"confirm"}`
  - `interactive=false` → ghi ngay `decision="reject"` (FR-041)
  - khi đường nhanh gặp tín hiệu `confirm_tool`: tạo `TurnRun` không có phần việc để dừng hỏi (research R6)
- [ ] T059 [US4] Thêm `apply_decision()` vào `backend/app/orchestrator/conductor.py` (research R18, FR-050):
  - `reply.decision=approve` → khoá dòng `turn_runs` bằng `SELECT … FOR UPDATE` (Postgres), kiểm tra `pending.kind=="confirm"`, ghi `confirmations[i].decision`, đặt `pending=null` rồi commit **trước** khi chạy
  - kiểm tra lại quyền
  - dựng `ToolContext` mới, không dùng lại handle đã hết hạn (research R18):
    - `user_id`, `role`, `class_id`, `conversation_id` lấy từ `turn_runs` và phiên hiện tại
    - `dataset_id`, `grade` đọc lại từ lớp
    - `agent_slug=pending.confirm.agent`, `allowed_tools={tool}`
    - `source="chat"`, `log_calls=True`, `mode="synthesis"`
    - `message_id` là tin nhắn kết quả của request này; `events` là hàng đợi SSE của request này
  - gọi thẳng `IMPLEMENTATIONS[tool](context, args)` với `args` đã lưu (không qua MCP)
  - ghi `tool_calls`, `executed_at`, `result_ref`
  - `reject`, hết hạn, hoặc gõ tin khác khi đang chờ xác nhận → không chạy (research R7)
  - đưa `{"done": true, "summary", "link"}` hoặc `{"done": false, "reason"}` vào bước tổng hợp; `meta.ask.state` `approved` hoặc `rejected`
- [ ] T060 [US4] Thêm chế độ xác nhận vào `web/src/components/chat/AskCard.tsx`:
  - hai nút "Đồng ý" và "Không"
  - hiện `summary`, `impact`, `audience_count`, `preview` (`title`, `body`, `items`, `before` → `after`)
  - gửi `reply.decision` kèm `message` "Đồng ý" hoặc "Không"
  - khoá ngay khi bấm để tránh gửi hai lần
  - nối vào `web/src/components/chat/ChatThread.tsx`

### Implementation cho User Story 4: 5 tool giáo viên (R18)

- [ ] T061 [P] [US4] Tách phần thân của `_installable()` và `install_in_class()` ở `backend/app/agents/router.py` thành `install_in_class()` trong `backend/app/agents/service.py`, giữ cùng quy tắc chứng nhận và hiển thị. Agent đã cài thì trả installation sẵn có. Router gọi lại service; `backend/tests/test_agents.py` vẫn pass
- [ ] T062 [P] [US4] Thêm `create_text_document(db, room, user, title, content)` vào `backend/app/knowledge/service.py`: lưu `.md` như tài liệu tải lên rồi lên lịch `process_document` như ở `backend/app/knowledge/router.py`
- [ ] T063 [P] [US4] Viết `backend/app/class_feed/router.py` theo contracts/class-actions.md:
  - `GET/POST/DELETE /classes/{class_id}/announcements`; GET lọc theo `audience` của người xem, mới nhất trước, tối đa 50; `POST` (`source="ui"`) cùng kiểm duyệt từ khóa với tool
  - `GET /classes/{class_id}/assignments`, `GET /classes/{class_id}/assignments/{id}` (`answer_key` chỉ cho giáo viên), `DELETE /classes/{class_id}/assignments/{id}`
  - schema `AnnouncementOut` và `AssignmentOut`
  - đăng ký router trong `backend/app/main.py`
- [ ] T064 [US4] Viết `backend/app/tools/actions.py` với 5 tool theo bảng ở contracts/mcp-tools.md:
  - Args:
    - `save_class_document`: `title` 3–120, `content` 20–20000
    - `set_agent_notes`: `notes` ≤ 1000, `mode` `replace|append`
    - `install_agent`: `agent`
    - `post_class_announcement`: `title` 3–120, `body` 10–2000, `audience` `students|parents|all`
    - `assign_practice`: `title` 3–120, `instructions` ≤ 1000, `questions` 1–20, `answer_key?`, `due_at?` ISO 8601
  - Mỗi tool có `preview()` không gọi LLM: tiêu đề và 600 ký tự đầu; ghi chú cũ → mới; tên và mô tả agent; danh sách câu hỏi; kèm `audience_count`
  - Mỗi tool có `execute()` trả `result_ref`; dùng T061, T062 và các model ở T008
  - phụ thuộc T061–T063
- [ ] T065 [US4] Đăng ký 5 tool trong `TOOLS` và `IMPLEMENTATIONS` ở `backend/app/tools/registry.py` (`roles={"teacher"}`, `needs_class=True`, `requires_confirmation=True`, `share_review=True` cho `save_class_document`, `post_class_announcement`, `assign_practice`). Thêm vào handler:
  - bước 6a: người dùng là giáo viên của `class_id` trong handle
  - bước 6b: từ khóa cho mọi trường văn bản; với `share_review`, gọi thêm `eduagent-review` với `role="student"`, `no_direct_answers="false"`, không gửi `answer_key`. Bọc lần gọi review trong `asyncio.timeout(orch_share_review_timeout_s)`; quá giờ hoặc lỗi thì fail closed với lỗi "Chưa kiểm duyệt được nội dung, thử lại sau." và `guard_events` `share_blocked`, `detector="timeout"` (research R18)
  - trúng thì lỗi "Nội dung không phù hợp để chia sẻ: <lý do>" và `guard_events` category `share_blocked`
  - đăng ký kèm `ctx` trong `backend/app/tools/server.py`
- [ ] T066 [P] [US4] Thêm tool vào manifest mẫu: `seed/agents/tro-ly-lop.yaml` (`set_agent_notes`, `install_agent`, `post_class_announcement`), `seed/agents/tao-de.yaml` (`assign_practice`, `save_class_document`), `seed/agents/on-tap-tai-lieu.yaml` (`save_class_document`)
- [ ] T067 [US4] Bật `request_confirmation` và 5 tool giáo viên (tham số `ctx` Fixed Value) trong `infra/dify/eduagent-runner.yml` và `infra/dify/eduagent-runner-raw.yml`. Thêm kiểm tra tương ứng vào `backend/tests/test_dify_dsl.py`
- [ ] T068 [US4] Đảm bảo pipeline kiểm định trong `backend/app/certify/pipeline.py` ghi nhận lần gọi tool cần xác nhận nhưng không chạy (luôn "Không", FR-041); cập nhật `backend/tests/test_certify.py`
- [ ] T069 [P] [US4] Thêm hàm `announcements`, `assignments` (list, get, create announcement, delete) vào `web/src/api-client/classes.ts` và kiểu tương ứng vào `web/src/api-client/types.ts`
- [ ] T070 [US4] Tạo `web/src/features/classes/ClassFeedTab.tsx`: thông báo và bài luyện; giáo viên đăng thông báo và có nút xoá qua `web/src/features/shared/ConfirmDialog.tsx`. Thêm tab "Bảng tin" vào `web/src/features/classes/ClassDetailPage.tsx`, hỗ trợ `?tab=feed` cho `link` trả về từ tool
- [ ] T071 [P] [US4] Hiện thông báo và bài luyện của lớp trong `web/src/features/classes/StudentClassesPage.tsx` và `web/src/features/classes/StudentHomePage.tsx`. Nút "Làm cùng gia sư" mở chat lớp với tin soạn sẵn "Mình muốn làm bài luyện “{title}”" kèm câu hỏi, không kèm đáp án
- [ ] T072 [P] [US4] Hiện thông báo `parents/all` của các lớp có con và danh sách bài luyện của con trong `web/src/features/family/ParentPages.tsx`

**Checkpoint**: Quickstart kịch bản 18, 20–29 đạt. 0 tool cần xác nhận chạy khi chưa có "Đồng ý" (SC-005).

---

## Phase 7: User Story 5 — Agent tự nhờ agent khác khi gặp việc ngoài chuyên môn (Priority: P3)

**Goal**: Trong lúc làm, agent báo `request_help` hoặc `ask_user`. Backend thêm phần việc cho agent phù hợp, hoặc hỏi người dùng nếu lượt chưa hỏi, rồi chạy lại phần việc gốc. Độ sâu nhờ tối đa là 1.

**Independent Test**: Quickstart kịch bản 17 với ca nhóm `discover` của `eval/planning_set.jsonl`. Khung tiến trình có thêm phần việc `h1` của agent được nhờ; kết quả cuối có đóng góp của cả hai.

### Tests cho User Story 5 ⚠️

- [ ] T073 [P] [US5] Thêm vào `backend/tests/test_signal_tools.py`, mỗi trường hợp một ca:
  - `request_help` ngoài `mode="step"` bị từ chối (2a)
  - `request_help` ở phần việc `origin="help"` bị từ chối (`may_request_help=false`, FR-024)
  - `runner_step_signal.sse`: `ask_user` dừng hỏi khi còn lượt hỏi, ngược lại ghi giả định
  - `request_help` với slug hợp lệ → phần việc `h1` (`origin="help"`, `requested_by`), rồi phần việc gốc chạy lại (`origin="rerun"`) với ghi chú mới
  - slug lạ → backend tự chọn agent theo `task`; không có agent phù hợp → ghi chú "ngoài khả năng của các agent trong lớp"
  - vượt `orch_max_replans`, `orch_max_steps` hoặc `orch_max_agents` → không thêm phần việc
  - chỉ tín hiệu đầu tiên của mỗi loại trong một phần việc được dùng

### Implementation cho User Story 5

- [ ] T074 [P] [US5] Thêm vào `backend/app/tools/impl.py` (`signal=True`) và đăng ký kèm `ctx` trong `backend/app/tools/registry.py` và `backend/app/tools/server.py`:
  - `request_help`: `agent` là slug, có thể rỗng; `task` 10–1000
  - `ask_user`: `questions` 1–3, mỗi câu `question` ≤ 200 và `options` ≤ 6
  - handler chỉ ghi vào `ToolContext.signals` rồi trả ngay câu ở contracts/mcp-tools.md
- [ ] T075 [US5] Xử lý tín hiệu sau mỗi phần việc trong `backend/app/orchestrator/steps.py` (research R5):
  - `request_help`: tạo phần việc `h<n>` cho agent hợp lệ (slug thuộc roster, hoặc chọn theo `task`), tăng `replans`, phát `plan` mới (`plan_version += 1`), rồi tạo phần việc `rerun` cho agent gốc kèm ghi chú của `h<n>`
  - `ask_user`: gọi `pause_for_clarify()` với `step_key`, hoặc ghi vào `assumptions` khi `can_ask=false`
  - tôn trọng `orch_max_replans`, `orch_max_steps`, `orch_max_agents`
- [ ] T076 [US5] Bật `request_help`, `ask_user` (tham số `ctx` Fixed Value) và tăng số vòng tối đa của agent node từ 5 lên 6 trong `infra/dify/eduagent-runner.yml` và `infra/dify/eduagent-runner-raw.yml`. Cập nhật `backend/tests/test_dify_dsl.py`

**Checkpoint**: Cả 5 story chạy độc lập.

---

## Phase 8: Polish, vận hành và đo lường

**Purpose**: Bước 8–9 của plan: `dev.ps1`, tài liệu, eval, chỉnh prompt.

- [ ] T077 Cập nhật `dev.ps1` (hiến pháp, nguyên tắc III, FR-045):
  - kiểm tra và cảnh báo rõ khi `.env` thiếu `DIFY_PLANNER_KEY` cùng các khóa Dify khác (đường đầy đủ sẽ tắt)
  - xác nhận `alembic upgrade head` áp `0008_orchestration`
  - in trạng thái `orchestrator` từ `/api/health`
  - giữ tính chạy lại an toàn
  - kiểm tra cú pháp bằng `pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content dev.ps1 -Raw))"`, rồi chạy `.\dev.ps1` nếu hạ tầng có sẵn; nếu không chạy được thì ghi rõ là chưa chạy thử
- [ ] T078 [P] Cập nhật `infra/dify/README.md`: import `eduagent-planner.yml` và tạo khóa; cập nhật provider MCP `eduagent-tools` **trước khi** import runner để Dify thấy tool mới; danh sách tool MCP mới; ghi chú về hội thoại Dify mồ côi của phần việc và cách dọn
- [ ] T079 [P] Cập nhật mục chạy local trong `README.md` (biến `DIFY_PLANNER_KEY`, app planner) cho khớp `dev.ps1`
- [ ] T080 [P] Tạo `eval/planning_set.jsonl` khoảng 60 ca, chia 5 nhóm `simple`, `multi`, `ambiguous`, `clear`, `discover`; mỗi ca có `role`, `installed` và kỳ vọng (`path`, tập agent, có hỏi lại không). Thêm kiểm tra định dạng vào `backend/tests/test_eval_datasets.py`
- [ ] T081 Viết `eval/run_planning.py` gọi triage và planner thật, tính SC-002, SC-003, SC-004 và ghi `eval/results/planning.csv`. Cờ `--e2e` chạy trọn lượt qua `run_dify_turn` với `force_path` và ghi `eval/results/planning_e2e.csv` với các cột:
  - `first_progress_ms`: từ lúc gửi tới sự kiện `step(analyze)` hoặc `plan` đầu tiên; SC-006 yêu cầu ≤ 3000 ms
  - `final_ms`: thời gian tới kết quả cuối, báo trung vị và p90 (SC-006)
  - `words`: độ dài kết quả, ≤ 300 từ (SC-007) Thêm test khô vào `backend/tests/test_eval_scripts.py`
- [ ] T082 [P] Thêm khoảng 10 ca "lách chính sách qua phối hợp" vào `eval/redteam_vi.jsonl`, gồm ca "tài liệu lớp bảo agent giao bài hoặc đăng thông báo" (SC-005, SC-008)
- [ ] T083 Chạy `eval/run_planning.py`, `eval/run_planning.py --e2e`, `eval/run_routing.py --latency` (so với mốc ở T001) và `eval/run_redteam.py`. Nếu chưa đạt ngưỡng ở spec, chỉnh prompt planner và triage trong `infra/dify/eduagent-planner.yml`, `infra/dify/eduagent-triage.yml`, và `capabilities` của manifest trong `seed/agents/*.yaml`
- [ ] T084 [P] Ghi kết quả SC-001 đến SC-008 và mô tả kiến trúc điều phối vào `docs/BAO-CAO.md`
- [ ] T085 Chạy toàn bộ test (`cd backend; uv run pytest`, `cd web; npm test`, `npm run build`) và đi hết 29 kịch bản trong `specs/002-multi-agent-orchestration/quickstart.md`; ghi lại kịch bản nào chưa chạy thử

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: không phụ thuộc. T001 phải chạy **trước** T002 để có mốc độ trễ. T002–T004 cần Dify chạy.
- **Foundational (Phase 2)**: sau Setup (fixture ở T002–T004 dùng cho T026). **Chặn mọi story.**
- **US1 (Phase 3)**: sau Foundational. Đây là MVP.
- **US2 (Phase 4)**: sau Foundational. Độc lập với US1, chỉ sửa chung `conductor.py`, nên nếu làm song song thì phải gộp cẩn thận.
- **US3 (Phase 5)**: sau Foundational. Có giá trị nhất khi US2 đã xong (nhiều phần việc), nhưng chạy được với kế hoạch một phần việc.
- **US4 (Phase 6)**: cần cơ chế dừng và làm tiếp của US1 (T030–T033, T036–T037). Phần 5 tool (T061–T072) chỉ cần T056–T060.
- **US5 (Phase 7)**: cần US1 (`pause_for_clarify`) và DAG của US2 (T040).
- **Polish (Phase 8)**: sau các story muốn giao. T077–T079 có thể làm ngay sau Foundational.

### Trong từng story

- Test viết trước và phải fail trước khi cài đặt.
- Model → service → handler/endpoint → web.
- Sửa `conductor.py` theo thứ tự task ID (cùng file).

### Parallel Opportunities

- Setup: T005, T006 song song với nhau và với các spike T002–T004.
- Foundational: T007, T008, T009 song song; T012, T016, T017, T019, T023, T024, T025, T027 song song sau khi model xong.
- US1: T028, T029 (test) song song; T038 song song với T036–T037.
- US2: T043 song song với T040–T042.
- US3: T045, T046, T050 song song.
- US4: T053, T054, T055 (test) song song; T061, T062, T063 song song; T069, T071, T072 song song sau T063.
- Polish: T078, T079, T080, T082, T084 song song.

---

## Parallel Example: User Story 4

```text
# Test viết cùng lúc:
Task: "T053 test_signal_tools.py: confirm_probe"
Task: "T054 test_confirm_tools.py: 5 tool giáo viên"
Task: "T055 test_class_actions.py: API thông báo và bài luyện"

# Phần dùng lại của 5 tool, khác file, làm cùng lúc:
Task: "T061 tách install_in_class() vào agents/service.py"
Task: "T062 create_text_document() trong knowledge/service.py"
Task: "T063 class_feed/router.py"

# Web sau khi có API:
Task: "T069 api-client/classes.ts"
Task: "T071 StudentClassesPage.tsx, StudentHomePage.tsx"
Task: "T072 ParentPages.tsx"
```

## Parallel Example: Foundational

```text
Task: "T007 orchestrator/models.py"
Task: "T008 class_feed/models.py"
Task: "T009 usage_ledger.path trong chat/models.py"
# sau T010–T011:
Task: "T016 dify_client.py: TriageResult.path, run_planner()"
Task: "T017 runtime/prompts.py: planner_roster()"
Task: "T019 orchestrator/prompts.py"
Task: "T024 DSL triage và planner"
Task: "T027 web types và chatStream"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + User Story 1)

1. Phase 1: đo mốc độ trễ, ghi fixture Dify.
2. Phase 2: dữ liệu, rẽ nhánh fast/full, planner, phần việc tuần tự, tổng hợp.
3. Phase 3: hỏi lại và làm tiếp, `AskCard`, công tắc lớp.
4. **Dừng và kiểm chứng**: quickstart kịch bản 1–6, 13–15, 19; `run_routing.py --latency` (SC-001).
5. Demo được: hệ thống biết hỏi lại và có bước phân tích (bước 2 và 3 của plan).

### Incremental Delivery

1. MVP ở trên.
2. US2: nhiều agent song song, contributors (kịch bản 7, 8, 12, 16).
3. US3: khung tiến trình và ghi chú đã kiểm duyệt (kịch bản 9–11).
4. US4: xác nhận và 5 tool giáo viên (kịch bản 18, 20–29). Phần này lớn nhất; có thể giao riêng cơ chế (T053, T056–T060) trước 5 tool (T054–T055, T061–T072).
5. US5: tín hiệu giữa chừng (kịch bản 17).
6. Phase 8: eval, chỉnh prompt, báo cáo.

### Gợi ý commit message (người dùng tự commit)

- `feat(orchestrator): add turn runs, planner and full-path routing` (Phase 2)
- `feat(orchestrator): clarify questions with resume and class toggle` (US1)
- `feat(orchestrator): run plan steps in parallel and credit contributors` (US2)
- `feat(chat): process panel with reviewed step notes` (US3)
- `feat(tools): enforce confirmation and add teacher action tools` (US4)
- `feat(tools): request_help and ask_user signal tools` (US5)
- `chore(dev): check planner key in dev.ps1 and add planning eval` (Phase 8)

---

## Notes

- [P] = khác file và không phụ thuộc task chưa xong.
- `backend/app/orchestrator/conductor.py`, `backend/app/runtime/dify_turn.py` và `backend/app/tools/registry.py` bị nhiều story sửa, nên không đánh [P] cho các task sửa chúng.
- Mỗi checkpoint chạy được và kiểm chứng độc lập; không để thay đổi đường nhanh làm gãy test feature 001.
- Nhánh `002-multi-agent-orchestration` chưa được tạo (đang ở `feat/dify-runtime`); người dùng tự tạo nhánh nếu muốn.

---

## Phase 9: Convergence

- [ ] T086 CRITICAL: Cập nhật hướng dẫn chạy local cho khớp trạng thái code hiện tại. `README.md` mục "Chạy local" vẫn ghi "import 4 DSL" và chưa có `DIFY_PLANNER_KEY`, trong khi repo đã có `infra/dify/eduagent-planner.yml` và `eduagent-triage.yml` có nhánh `path` mới. Sửa README thành 5 DSL kèm khóa `DIFY_PLANNER_KEY` (để trống thì đường đầy đủ tắt). Thêm `eduagent-planner.yml` (Workflow, `DIFY_PLANNER_KEY`) vào bảng "Import ứng dụng" của `infra/dify/README.md`, kèm ghi chú import lại `eduagent-triage.yml` để có output `path`. Làm phần tài liệu của T078/T079 ngay, không đợi Phase 8. per Constitution III (contradicts)
- [ ] T087 Thêm test vào `backend/tests/test_orchestrator.py` khẳng định `query` của bước tổng hợp (lượt ghi vào hội thoại Dify chính) chỉ gồm yêu cầu gốc và "Thông tin bổ sung", không chứa ghi chú làm việc của phần việc nào. Ghi chú chỉ được nằm trong `inputs.system_prompt`. per FR-031 (partial)
- [ ] T088 Thêm test vào `backend/tests/test_orchestrator.py`: tool gọi trong một phần việc (qua `FakeDify.tool_calls`, ví dụ `math_check`) phát sự kiện `tool` có `step_key` của phần việc đó ngay trong luồng SSE, và được lưu vào `run_steps.tools` của phần việc. per FR-032 (partial)
- [ ] T089 Thu hẹp `_close_stale_runs()` trong `backend/app/orchestrator/conductor.py`: hiện hàm huỷ im lặng mọi run mở của hội thoại, kể cả run `awaiting_user`, mà không phát `notice(pending_cancelled)` và không cập nhật `meta.ask.state`. Chỉ dọn run `running` bị bỏ dở; run `awaiting_user` phải đi qua `resume()` hoặc huỷ theo T032/T033. Thêm một ca test tương ứng. per plan: research R7 (unrequested)
