---

description: "Danh sách task triển khai: chuyển lõi agent sang Dify"
---

# Tasks: Chuyển lõi agent sang Dify và tích hợp tính năng Dify

**Input**: Tài liệu thiết kế trong `specs/001-dify-core-migration/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Có task test. FR-027 yêu cầu bộ test tự động chạy được không cần Dify, và research R14 chốt cách test
(`httpx.MockTransport` + fixture ghi từ spike, `@pytest.mark.dify` cho test tích hợp tùy chọn). Test viết trước và
phải fail trước khi làm phần tương ứng.

**Organization**: Task gom theo user story để mỗi story làm và kiểm tra độc lập được.

**Lưu ý chung**:
- Không task nào được chạy `git commit`/`push`/`merge` (constitution II). Người dùng tự commit.
- Lệnh kiểm tra backend: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`;
  web: `cd web && npm test && npm run build`.
- Cho tới Phase 9, mặc định vẫn là `runtime_engine="langgraph"`; mọi test hiện có phải tiếp tục pass.

## Format: `[ID] [P?] [Story] Mô tả`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: user story của task (US1…US6)

---

## Phase 1: Setup (hạ tầng dùng chung)

**Purpose**: cấu hình, thư mục và khung test cho Dify

- [X] T001 Thêm vào `Settings` trong `backend/app/config.py`: `runtime_engine: Literal["langgraph", "dify"] = "langgraph"`, `dify_base_url: str = "http://127.0.0.1:8080"`, `dify_triage_key`, `dify_runner_key`, `dify_runner_raw_key`, `dify_dataset_key` (đều `str = ""`), `dify_timeout_s: float = 30.0`, `mcp_token: str = ""`, `mcp_public_url: str = "http://host.docker.internal:8001/mcp"`
- [X] T002 [P] Thêm khối biến môi trường Dify vào `.env.example` đúng như quickstart.md mục 1 (`RUNTIME_ENGINE`, `DIFY_BASE_URL`, `DIFY_TRIAGE_KEY`, `DIFY_RUNNER_KEY`, `DIFY_RUNNER_RAW_KEY`, `DIFY_DATASET_KEY`, `DIFY_TIMEOUT_S`, `MCP_TOKEN`, `MCP_PUBLIC_URL`), mỗi biến có chú thích tiếng Việt một dòng
- [X] T003 [P] Tạo `infra/dify/README.md` với các mục: phiên bản Dify ghim (≥ 1.13.3), lấy `docker/docker-compose.yaml` chính thức, đổi nginx sang `127.0.0.1:8080`, `extra_hosts: host.docker.internal:host-gateway` cho Linux, import 3 DSL, thêm MCP provider `eduagent-tools`, tạo API key, mục trống "Ghi chú spike" (research R13)
- [X] T004 [P] Đăng ký marker `dify` trong cấu hình pytest của `backend/pyproject.toml` và thêm fixture tự skip test `@pytest.mark.dify` khi không có `DIFY_BASE_URL` trong `backend/tests/conftest.py`
- [X] T005 [P] Tạo thư mục `backend/tests/fixtures/dify/` kèm `README.md` mô tả từng fixture sẽ có (research R14) và cách ghi lại từ Dify thật

---

## Phase 2: Foundational (điều kiện tiên quyết, chặn mọi story)

**Purpose**: spike Dify, migration, bộ chọn engine

**⚠️ CRITICAL**: Không bắt đầu story nào trước khi phase này xong. T006 là cổng dừng: nếu spike không đạt, dừng và báo người dùng (research R12).

- [X] T006 Spike Dify (thủ công, cần Dify thật): dựng Dify theo `infra/dify/README.md`, dựng bản thử triage + runner, trả lời 6 câu hỏi của research R12 (Fixed Value nhận `{{#start.ctx#}}`; tên/nội dung sự kiện stream, có `message_replace`, `message_end` có token; giới hạn input paragraph ≥ 12000; độ trễ chữ đầu tiên p95 ≤ 3 s; Agent node với chế độ reasoning; Question Classifier với tiếng Việt không dấu). Ghi kết quả vào mục "Ghi chú spike" của `infra/dify/README.md`. Nếu câu 1 và phương án dự phòng R6 đều không đạt, hoặc câu 4 vượt xa 3 s → DỪNG, báo người dùng
- [ ] T007 Ghi fixture từ spike vào `backend/tests/fixtures/dify/`: `runner_plain.sse`, `runner_tool.sse`, `runner_tool_denied.sse`, `runner_message_replace.sse`, `runner_error_midstream.sse`, `runner_conversation_not_found.json`, `triage_safe.json`, `triage_block.json`, `triage_self_harm_risk.json`, `triage_self_harm_method.json`, `triage_routing.json`, `suggested.json`, `dataset_retrieve.json`, `indexing_status_completed.json`, `indexing_status_error.json`. Thay mọi khóa API và id người dùng thật bằng giá trị giả
- [X] T008 Tạo migration `backend/migrations/versions/0006_dify_runtime.py` (down_revision = 0005): thêm `conversations.dify_conversation_id` `String(64)` nullable; `classes.dify_dataset_id` `String(64)` nullable **unique**; `documents.dify_document_id` `String(64)` nullable; `documents.dify_batch` `String(64)` nullable. Có `downgrade()` xóa đúng 4 cột. Không sửa migration cũ
- [X] T009 [P] Thêm cột `dify_conversation_id: Mapped[str | None] = mapped_column(String(64))` vào `Conversation` trong `backend/app/chat/models.py`
- [X] T010 [P] Thêm cột `dify_dataset_id: Mapped[str | None] = mapped_column(String(64), unique=True)` vào `Class` trong `backend/app/classes/models.py`
- [X] T011 [P] Thêm cột `dify_document_id` và `dify_batch` (`String(64)`, nullable) vào `Document` trong `backend/app/knowledge/models.py`
- [X] T012 Tạo `backend/app/runtime/engine.py`: tách phần thân gọi `GRAPH` khỏi `run_turn()` trong `backend/app/chat/router.py` thành `run_langgraph_turn()`; `engine.run_turn()` chọn `langgraph` hoặc `dify` theo `settings.runtime_engine` (nhánh `dify` tạm raise `NotImplementedError`). `chat/router.py` và `backend/app/agents/sandbox.py` gọi qua `engine`; giữ nguyên chữ ký và thứ tự sự kiện SSE hiện tại
- [X] T013 Ghi khóa `meta.engine` (`"langgraph" | "dify"`) vào tin nhắn `assistant` khi lưu trong `backend/app/chat/router.py`
- [X] T014 [P] `GET /api/health` trong `backend/app/main.py` trả thêm trường `engine` = `settings.runtime_engine`; cập nhật `backend/tests/test_health.py`
- [X] T015 Chạy toàn bộ test backend với `runtime_engine="langgraph"`; mọi test hiện có phải pass sau T008–T014

**Checkpoint**: Spike đạt, schema mới có, engine cũ vẫn chạy qua `engine.run_turn()`.

---

## Phase 3: User Story 1 - Chat với agent trong lớp chạy trên Dify (Priority: P1) 🎯 MVP

**Goal**: một lượt chat đi qua `eduagent-triage` (chọn agent) rồi `eduagent-runner` (trả lời có tool MCP, nhớ ngữ cảnh), SSE giữ nguyên thứ tự.

**Independent Test**: quickstart.md kịch bản 1–3: học sinh demo hỏi toán và tiếng Anh, chữ hiện dần, đúng agent, có thẻ tool `math_check`, hỏi tiếp thì agent nhớ ngữ cảnh.

### Tests for User Story 1 ⚠️

- [X] T016 [P] [US1] Test MCP qua HTTP trong `backend/tests/test_mcp_http.py`: thiếu/sai bearer → 401 và không tool nào chạy; `ctx` không tồn tại → lỗi "Ngữ cảnh gọi công cụ không hợp lệ hoặc đã hết hạn."; handle quá 10 phút → cùng lỗi; tool không thuộc manifest, sai vai trò, tool cần lớp mà handle không có `class_id` → từ chối và có `guard_events` (stage `tool`, category `tool_denied`); tham số sai → lỗi tool, không có `guard_events`; mọi lần gọi có một dòng `tool_calls` và `arguments` không chứa `ctx`; sự kiện `tool` `start` rồi `done`/`denied`/`error` vào hàng đợi đúng `message_id` (contracts/mcp-tools.md)
- [X] T017 [P] [US1] Test client Dify trong `backend/tests/test_runtime_dify.py` bằng `httpx.MockTransport`: triage blocking parse đủ `verdict`, `category`, `reason`, `agent`, `route_reason`; runner `runner_plain.sse` → `text_delta` generation 0 với `text_offset` tính theo UTF-16 (có ký tự tiếng Việt và emoji); `message_end` → `dify_message_id` và usage; `task_id` lấy từ sự kiện đầu tiên
- [X] T018 [P] [US1] Test lượt chat đầy đủ với `runtime_engine="dify"` trong `backend/tests/test_runtime_dify.py`: thứ tự SSE `operation → conversation → agent → (text_delta | tool)* → done` (contracts/chat-sse.md); lượt đầu gửi `conversation_id=""` và lưu `dify_conversation_id`; lượt sau gửi lại mã đó; `user` gửi Dify là `users.id`, không có email/tên (FR-016); `roster` chỉ gồm agent của `available_agents()`; agent triage trả về ngoài `roster` → dùng `tro-ly-lop`; triage lỗi/timeout → `error` rồi `done(status="error")` và runner KHÔNG được gọi (fail closed); học sinh chưa có đồng ý phụ huynh hoặc vừa bị rút đồng ý → `done(status="consent_required")`, KHÔNG gọi triage (FR-015); `requested_agent` không còn trong `roster` (agent bị gỡ khỏi lớp) → không dùng agent đó
- [X] T019 [P] [US1] Test `context_reset` và dừng trong `backend/tests/test_runtime_dify.py`: runner trả lỗi không tìm thấy hội thoại (`runner_conversation_not_found.json`) → gửi lại với `conversation_id=""`, cập nhật mã, phát `notice` kind `context_reset`, lượt vẫn `ok`; ngắt kết nối SSE giữa chừng → gọi `POST /v1/chat-messages/{task_id}/stop`; lỗi giữa stream (`runner_error_midstream.sse`) → giữ phần đã stream, `done(status="error")`

### Implementation for User Story 1

- [X] T020 [US1] Mở rộng `backend/app/tools/context.py`: turn handle là chuỗi ngẫu nhiên 128 bit (`secrets.token_urlsafe(16)`), lưu `user_id`, `role`, `class_id`, `grade`, `conversation_id`, `message_id`, `agent_slug`, `allowed_tools`, `dataset_id` (null nếu ngoài lớp), `events` (hàng đợi `asyncio.Queue` sự kiện `tool`), `citations` (list), `expires_at` = tạo + 10 phút; hàm `create_handle()`, `get_handle()` (None nếu hết hạn), `drop_handle()`
- [X] T021 [US1] Chuyển kiểm tra quyền và ghi log tool vào handler dùng chung trong `backend/app/tools/registry.py`: 6 bước kiểm tra theo thứ tự của contracts/mcp-tools.md, ghi `tool_calls` (không lưu `ctx`), ghi `guard_events` khi từ chối, đẩy sự kiện `tool` vào `handle.events`; `execute()` của engine cũ gọi cùng handler
- [X] T022 [US1] Đổi `backend/app/tools/server.py` sang MCP streamable HTTP: mỗi tool nhận `ctx` làm tham số đầu tiên rồi gọi handler của T021; middleware kiểm `Authorization: Bearer <MCP_TOKEN>` (sai/thiếu → 401, không dùng cookie)
- [X] T023 [US1] Mount MCP app tại `/mcp` (ngoài tiền tố `/api`) trong `backend/app/main.py`, kèm lifespan của session manager MCP
- [X] T024 [P] [US1] Tạo DSL `infra/dify/eduagent-triage.yml` (Workflow): input `query` (paragraph, bắt buộc), `role` (select `teacher`/`student`/`parent`, bắt buộc), `roster` (paragraph JSON, bắt buộc), `requested_agent` (text), `previous_agent` (text); nhánh Code xử lý `requested_agent`/`@mention` → IF → LLM router trả JSON `{"agent","reason"}`; Code cuối kiểm slug thuộc `roster` (sai → `tro-ly-lop`); output `agent`, `route_reason` (`ui`, `mention`, `router: <lý do>`, `fallback`). Nhánh an toàn tạm trả `verdict="allow"`, `category="safe"`, `reason=""` (hoàn thiện ở US2)
- [X] T025 [P] [US1] Tạo DSL `infra/dify/eduagent-runner.yml` (Chatflow): input `system_prompt` (paragraph, max 12000), `ctx` (text), `safety_note` (select `true`/`false`); Agent node chiến lược Function Calling, tối đa 5 vòng, memory 12 tin nhắn, model theo `LLM_MAIN_MODEL`; MCP provider `eduagent-tools` với 5 tool, tham số `ctx` của mọi tool ở chế độ Fixed Value = `{{#start.ctx#}}` (hoặc phương án dự phòng R6 nếu spike T006 thất bại câu 1); tắt lời chào, đánh giá, upload file, giọng nói
- [X] T026 [US1] Tạo `backend/app/runtime/dify_client.py`: class nhận `httpx.AsyncClient` qua tham số; `run_triage(inputs, user)` gọi `POST /v1/workflows/run` blocking với `DIFY_TRIAGE_KEY` và timeout `dify_timeout_s`; `stream_runner(query, inputs, conversation_id, user, raw=False)` gọi `POST /v1/chat-messages` streaming, parse SSE thành sự kiện nội bộ theo bảng research R9; `stop(task_id, user, raw=False)`; `get_suggested(message_id, user)`; lỗi HTTP/timeout/không tìm thấy hội thoại thành exception riêng (`DifyError`, `DifyConversationNotFound`)
- [X] T027 [US1] Tạo `backend/app/runtime/dify_turn.py` với hàm sinh SSE của một lượt: kiểm đồng ý phụ huynh/vai trò/lớp như engine cũ (FR-015) → `redact()` tin nhắn → phát `operation`, `conversation` → dựng `roster` từ `available_agents()` → triage → phát `agent` (`message_id`, `agent`, `name`, `avatar`, `reason`) → tạo handle → `build_system_prompt()` (cắt ≤ 12000 ký tự) → runner stream; trộn sự kiện runner với `handle.events` để `tool` hiện đúng thời điểm; `text_offset` theo UTF-16; lưu tin nhắn `user` (bản đã ẩn) và `assistant` với `meta` (`engine="dify"`, `dify_message_id`, `route_reason`, `tools`, `latency_ms`); `drop_handle()` trong `finally`
- [X] T028 [US1] Xử lý bộ nhớ hội thoại trong `backend/app/runtime/dify_turn.py`: đọc/ghi `conversations.dify_conversation_id`; bắt `DifyConversationNotFound` → gửi lại với `conversation_id=""`, lưu mã mới, phát `notice` kind `context_reset` với `text` "Agent không còn nhớ ngữ cảnh cũ của cuộc trò chuyện này." (research R5)
- [X] T029 [US1] Xử lý dừng trong `backend/app/runtime/dify_turn.py`: khi client ngắt SSE hoặc lượt bị hủy, gọi `dify_client.stop(task_id)` (best effort, ghi log nếu lỗi) (FR-006)
- [X] T030 [US1] Nối nhánh `dify` của `backend/app/runtime/engine.py` vào `dify_turn`; sandbox (`backend/app/agents/sandbox.py`, `agents_override`) truyền `roster` chỉ gồm agent đang thử và `requested_agent` là slug đó
- [X] T031 [US1] Thêm notice `context_reset` vào kiểu `notice.kind` trong `web/src/api-client/types.ts` và hiển thị dạng thông báo nhẹ trong `web/src/components/ChatPanel.tsx`; `chatStream.ts` không cần sửa (đã chuyển tiếp mọi `type`)

**Checkpoint**: Với `RUNTIME_ENGINE=dify`, quickstart kịch bản 1–3 và 14 chạy được; test T016–T019 pass; test cũ vẫn pass với `langgraph`.

---

## Phase 4: User Story 2 - Guardrail của Dify bảo vệ học sinh (Priority: P1)

**Goal**: phân loại an toàn trong triage, kiểm duyệt đầu vào/đầu ra cấp ứng dụng của runner, ẩn thông tin cá nhân ở backend, ghi `guard_events` cho mọi lần chặn/ẩn; bỏ chủ đề cấm theo lớp.

**Independent Test**: quickstart.md kịch bản 4–6, 9, 13; chạy `eval/run_redteam.py` với `RUNTIME_ENGINE=dify` và mọi lần chặn có bản ghi `guard_events` (SC-006).

### Tests for User Story 2 ⚠️

- [X] T032 [P] [US2] Test chặn đầu vào trong `backend/tests/test_runtime_dify.py`: `triage_block.json` → SSE `operation → conversation → notice(guard_blocked) → done(status="blocked")`, runner KHÔNG được gọi (FR-008), có `guard_events` detector `dify_classifier`, stage `input`, category đúng nhãn; `triage_self_harm_method.json` → chặn và text hỗ trợ có "111"; `triage_self_harm_risk.json` → không chặn, runner nhận `safety_note="true"`, có `guard_events` category `self_harm_risk`
- [X] T033 [P] [US2] Test kiểm duyệt cấp ứng dụng trong `backend/tests/test_runtime_dify.py`: `runner_message_replace.sse` → `text_reset` rồi `text_delta` generation 1, `guard_events` detector `dify_moderation` stage `output` category `moderation`, không phát `suggestions`/`citations`; runner trả nguyên văn câu trả lời cài sẵn đầu vào → `status="blocked"`, `guard_events` stage `input` detector `dify_moderation`
- [X] T034 [P] [US2] Test quyền riêng tư trong `backend/tests/test_runtime_dify.py`: tin có `0912 345 678`, email, mật khẩu → body gửi tới triage và runner (bắt qua `MockTransport`) không chứa chuỗi gốc; tin nhắn lưu chỉ có `[số điện thoại đã ẩn]`; có `notice` kind `redacted` và `guard_events` detector `privacy` category `pii`; `excerpt` của mọi `guard_events` đã qua `redact()` (SC-005)
- [X] T035 [P] [US2] Cập nhật `backend/tests/test_classes.py`: `GET/PUT /api/classes/{id}/policy` không còn `blocked_topics`; gửi `blocked_topics` bị bỏ qua; policy cũ có khóa này vẫn đọc được

### Implementation for User Story 2

- [X] T036 [P] [US2] Tạo `infra/dify/moderation-keywords.txt` (mỗi dòng một từ khóa, có cả dạng có dấu và không dấu, nhóm theo chú thích `#`) từ các luật chặn trong `backend/app/guard/rules.py` và `eval/redteam_vi.jsonl`; đây là nguồn duy nhất của bộ từ khóa (research R3)
- [X] T037 [P] [US2] Tạo `infra/dify/preset-responses.json` với khóa `input_blocked`, `output_blocked`, `self_harm_support` (có Tổng đài 111) bằng tiếng Việt thân thiện
- [X] T038 [US2] Tạo `backend/app/guard/dify_rules.py`: đọc `moderation-keywords.txt` và `preset-responses.json` (đường dẫn từ gốc repo, cache khi khởi động); hàm `contains_blocked_keyword(text)` và `is_preset_input_block(text)` dùng cho T041 và US4
- [X] T039 [US2] Hoàn thiện nhánh an toàn trong `infra/dify/eduagent-triage.yml`: Question Classifier với nhãn `safe`, `self_harm_risk`, `self_harm_method`, `jailbreak`, `dangerous`, `age_inappropriate` (mô tả nhãn có ví dụ tiếng Việt có dấu và không dấu); Code gộp ánh xạ `safe`→`allow`, `self_harm_risk`→`support`, còn lại→`block`, kèm `reason` tiếng Việt ngắn
- [X] T040 [US2] Bật kiểm duyệt nội dung đầu vào và đầu ra trong `infra/dify/eduagent-runner.yml`: loại keywords nhúng nguyên nội dung `moderation-keywords.txt`, OpenAI Moderation khi có khóa, câu trả lời cài sẵn lấy từ `preset-responses.json`; viết `infra/dify/sync_keywords.py` chép nội dung `moderation-keywords.txt` vào phần kiểm duyệt của `eduagent-runner.yml` (chế độ `--check` báo lỗi nếu lệch), và test offline `backend/tests/test_dify_dsl.py` khẳng định DSL khớp file từ khóa; ghi lệnh vào `infra/dify/README.md`
- [X] T041 [US2] Xử lý guard trong `backend/app/runtime/dify_turn.py`: `verdict=block` → `notice(guard_blocked)` + `done(status="blocked")`, không gọi runner; `support` → `safety_note="true"`; `self_harm_method` → trả `self_harm_support`; `message_replace` → `text_reset` + generation 1; câu trả lời trùng `input_blocked` → `status="blocked"`, `blocked_stage="input"`; `redact()` có thay đổi → `notice(redacted)`. Ghi `guard_events` với detector `dify_classifier` / `dify_moderation` / `privacy` và category theo data-model.md
- [X] T042 [US2] Thêm chỉ dẫn `safety_note` vào `backend/app/runtime/prompts.py` (khi `true`: trả lời ấm áp, khuyến khích nói với người lớn tin cậy, có Tổng đài 111) và truyền qua input runner
- [X] T043 [US2] Bỏ `blocked_topics` khỏi `backend/app/classes/schemas.py` và `backend/app/classes/models.py` (policy mặc định), bỏ khỏi `build_system_prompt()` trong `backend/app/runtime/prompts.py`; engine cũ (`backend/app/runtime/graph.py`, `backend/app/guard/rules.py`) đọc `policy.get("blocked_topics", [])` để không gãy khi dữ liệu không còn khóa này (FR-013)
- [X] T044 [P] [US2] Bỏ ô "chủ đề cấm" trong `web/src/features/classes/PolicyTab.tsx` và trường `blocked_topics` trong `web/src/api-client/types.ts`; thêm một dòng giải thích "Kiểm duyệt dùng bộ luật chung cho mọi lớp"
- [X] T045 [US2] Xử lý Dify không phản hồi trong `backend/app/runtime/dify_turn.py`: lỗi kết nối/timeout ở triage hoặc runner → `error` với `message` "Hệ thống trợ lý đang bận, em thử lại sau ít phút nhé." rồi `done(status="error")` trong vòng `dify_timeout_s` (quickstart kịch bản 13)

**Checkpoint**: Kịch bản 4–6, 9, 13 đạt; test T032–T035 pass.

---

## Phase 5: User Story 3 - Agent giáo viên chạy trên Dify và qua kiểm định (Priority: P2)

**Goal**: phòng thử và pipeline kiểm định chạy qua Dify; kiểm định dùng `eduagent-runner-raw` và hội thoại mới cho mỗi tình huống.

**Independent Test**: quickstart.md kịch bản 10; 7 agent nền tảng chạy được sau `seed_demo` không cần cấu hình tay.

### Tests for User Story 3 ⚠️

- [ ] T046 [P] [US3] Cập nhật `backend/tests/test_certify.py`: với `runtime_engine="dify"`, mỗi tình huống gọi runner bằng khóa `DIFY_RUNNER_RAW_KEY`, `conversation_id=""` (FR-019), không gọi triage, `requested_agent` cố định; kết quả vẫn là đạt / cần xem lại / không đạt
- [ ] T047 [P] [US3] Test trong `backend/tests/test_runtime_dify.py`: chat thường KHÔNG bao giờ dùng `DIFY_RUNNER_RAW_KEY`; sandbox chỉ gửi `roster` gồm agent đang thử

### Implementation for User Story 3

- [X] T048 [P] [US3] Tạo `infra/dify/eduagent-runner-raw.yml`: bản sao `eduagent-runner.yml`, tắt kiểm duyệt nội dung; ghi trong `infra/dify/README.md` rằng hai file phải giữ giống nhau ngoài phần kiểm duyệt
- [ ] T049 [US3] Trong `backend/app/certify/pipeline.py`, `run_case()` gọi qua `backend/app/runtime/engine.py`: nhánh `dify` dùng `dify_client.stream_runner(raw=True)` với hội thoại mới, handle cho agent đang kiểm định trong lớp mô phỏng, gom câu trả lời rồi đưa giám khảo LLM ở backend như hiện nay; nhánh `langgraph` giữ `guard_mode="prompt_only"`
- [ ] T050 [US3] Kiểm tra `backend/app/agents/sandbox.py` + `backend/app/agents/router.py`: phiên bản agent mới tạo dùng được ngay trên Dify qua `system_prompt` input và `allowed_tools` trong handle (FR-017); học sinh/phụ huynh chỉ thấy phiên bản đã đạt trong `roster` (FR-018); thêm test `@pytest.mark.dify` trong `backend/tests/test_runtime_dify.py` chạy một câu hỏi qua từng agent trong 7 agent nền tảng sau `seed_demo` (US3 kịch bản 4)

**Checkpoint**: Kịch bản 10 đạt; test T046–T047 pass.

---

## Phase 6: User Story 4 - Gợi ý câu hỏi và trích dẫn trên giao diện chat (Priority: P2)

**Goal**: sau câu trả lời `ok`, hiện 1–3 câu hỏi gợi ý (nhấn để gửi) và trích dẫn tài liệu lớp khi agent đã dùng `class_doc_search`.

**Independent Test**: quickstart.md kịch bản 7 (cần tài liệu lớp: dùng engine cũ hoặc làm US5 trước để có kết quả `class_doc_search` từ Dify).

### Tests for User Story 4 ⚠️

- [ ] T051 [P] [US4] Test trong `backend/tests/test_runtime_dify.py`: sau `message_end`, gọi `GET /v1/messages/{message_id}/suggested`, bỏ câu chứa từ khóa của `moderation-keywords.txt`, giữ tối đa 3, phát `suggestions` trước `done`; lượt có `class_doc_search` phát `citations` với `items: [{document_id, title, location, excerpt}]`, `excerpt` ≤ 300 ký tự; lượt bị chặn hoặc có `message_replace` không phát cả hai; `meta.citations` và `meta.suggestions` được lưu
- [ ] T052 [P] [US4] Test web trong `web/src/components/chat/chat.test.tsx`: tin nhắn có `citations` hiện tên tài liệu + đoạn trích; có `suggestions` hiện nút, nhấn nút gọi hàm gửi với đúng nội dung; tin nhắn bị chặn không hiện cả hai

### Implementation for User Story 4

- [ ] T053 [US4] Handler `class_doc_search` trong `backend/app/tools/registry.py` thêm mỗi kết quả vào `handle.citations` dưới dạng `{document_id, title, location, excerpt}` (`excerpt` cắt 300 ký tự, bỏ trùng theo `document_id` + `location`)
- [ ] T054 [US4] Trong `backend/app/runtime/dify_turn.py`: khi lượt `ok`, phát `citations` (nếu có) rồi `suggestions` (lọc bằng `contains_blocked_keyword()` của T038, và qua OpenAI Moderation khi có khóa như kiểm duyệt đầu ra của runner (FR-022); tối đa 3; lỗi API suggested thì bỏ qua) trước `done`; lưu vào `meta.citations` / `meta.suggestions`
- [ ] T055 [US4] `GET /api/chat/conversations/{id}/messages` trong `backend/app/chat/router.py` trả `meta.citations` và `meta.suggestions` để hiển thị lại
- [ ] T056 [P] [US4] Thêm kiểu sự kiện `citations` và `suggestions` (contracts/chat-sse.md) và trường `citations?`, `suggestions?` cho tin nhắn trong `web/src/api-client/types.ts`
- [ ] T057 [US4] Xử lý sự kiện `citations`/`suggestions` trong `web/src/components/ChatPanel.tsx` (gắn vào tin nhắn theo `message_id`, xóa khi có `text_reset`, nhận lại từ lịch sử)
- [ ] T058 [US4] Hiển thị khối trích dẫn (tên tài liệu, vị trí, đoạn trích thu gọn) và hàng nút câu hỏi gợi ý trong `web/src/components/chat/MessageBody.tsx`; chỉ hiện nút gợi ý ở tin nhắn cuối cùng

**Checkpoint**: Kịch bản 7 đạt; test T051–T052 pass.

---

## Phase 7: User Story 5 - Tài liệu lớp trong kho tri thức Dify (Priority: P3)

**Goal**: mỗi lớp một kho Dify; tải lên / xử lý lại / xóa đồng bộ sang Dify; `class_doc_search` và `quiz_generator` tra đúng kho của lớp trong handle.

**Independent Test**: quickstart.md kịch bản 8: tài liệu lớp A trả lời được ở lớp A, không lộ ở lớp B (SC-007).

### Tests for User Story 5 ⚠️

- [ ] T059 [P] [US5] Test `backend/tests/test_dify_datasets.py` bằng `MockTransport`: tạo kho tên `class-<class_id>` khi lớp có tài liệu đầu tiên và lưu `classes.dify_dataset_id`; tải lên lưu `dify_document_id` + `dify_batch`, `status="processing"`; `indexing_status_completed.json` → `ready` và `chunk_count` = số segment; `indexing_status_error.json` → `failed`, `error` cắt 500 ký tự; xử lý lại = xóa tài liệu Dify cũ rồi tạo lại; xóa tài liệu: Dify lỗi → bản ghi giữ nguyên và API báo lỗi
- [ ] T060 [P] [US5] Cập nhật `backend/tests/test_documents_tools.py`: với `runtime_engine="dify"`, `class_doc_search` gọi `POST /v1/datasets/{id}/retrieve` với `id` lấy từ `handle.dataset_id`, không bao giờ từ tham số mô hình; handle lớp B không thể tra kho lớp A; chat cá nhân (không `class_id`) bị từ chối; kết quả giữ dạng `{"results": [{document_id, title, location, score, content}], "note"}`; thêm test `@pytest.mark.dify` cách ly thật: tài liệu ở kho lớp A, handle lớp B hỏi đúng nội dung đó → 0 kết quả (SC-007)

### Implementation for User Story 5

- [ ] T061 [US5] Tạo `backend/app/knowledge/dify_datasets.py` (nhận `httpx.AsyncClient`, khóa `DIFY_DATASET_KEY`): `create_dataset(class_id)`, `upload_document(dataset_id, filename, bytes)` → `(document_id, batch)`, `indexing_status(dataset_id, batch)`, `delete_document(dataset_id, document_id)`, `delete_dataset(dataset_id)`, `retrieve(dataset_id, query, top_k)` theo bảng mục 4 của contracts/dify-apps.md
- [ ] T062 [US5] Trong `backend/app/knowledge/service.py` (khi `runtime_engine="dify"`): tải lên → tạo kho nếu `classes.dify_dataset_id` null, đẩy file, lưu `dify_document_id`/`dify_batch`; xử lý lại → xóa rồi tạo lại từ file đã lưu, `failed → processing`; xóa → xóa trong Dify trước rồi mới xóa bản ghi; cập nhật trạng thái theo sơ đồ chuyển trạng thái của data-model.md
- [ ] T063 [US5] `GET /api/classes/{id}/documents` trong `backend/app/knowledge/router.py`: tài liệu đang `processing` thì hỏi `indexing_status` và cập nhật `status` trước khi trả về (FR-021)
- [ ] T064 [US5] Xóa lớp trong `backend/app/classes/service.py`: gọi `delete_dataset()` best effort (lỗi chỉ ghi log, không chặn việc xóa lớp)
- [ ] T065 [US5] `class_doc_search` và phần tra tài liệu của `quiz_generator` trong `backend/app/tools/impl.py`: nhánh `dify` gọi `retrieve()` trên `handle.dataset_id`, map kết quả sang dạng hiện tại và thêm `document_id`; `dataset_id` null → `{"results": [], "note": ...}` như khi lớp chưa có tài liệu
- [ ] T066 [US5] Điền `dataset_id` vào handle từ `classes.dify_dataset_id` khi tạo handle trong `backend/app/runtime/dify_turn.py`
- [ ] T067 [US5] `backend/scripts/seed_demo.py`: khi `runtime_engine="dify"`, đẩy tài liệu demo của lớp sang kho Dify của lớp và chờ indexing xong (timeout có thông báo)

**Checkpoint**: Kịch bản 8 đạt; test T059–T060 pass.

---

## Phase 8: User Story 6 - Giám sát, chi phí và đo đạc (Priority: P3)

**Goal**: token/chi phí của triage và agent trên trang chi phí; tracing nối hai phía; eval chạy được trên cả hai engine.

**Independent Test**: quickstart.md kịch bản 12 và mục 4 (so sánh), có bảng trong `docs/BAO-CAO.md`.

### Tests for User Story 6 ⚠️

- [ ] T068 [P] [US6] Test trong `backend/tests/test_runtime_dify.py`: một lượt `ok` ghi 2 dòng `usage_ledger` (`purpose="triage"` từ `data.total_tokens`, `purpose="agent"` từ `metadata.usage` của `message_end`), `provider="dify"`; lượt bị chặn ở triage chỉ có dòng `triage`
- [ ] T069 [P] [US6] Cập nhật `backend/tests/test_eval_scripts.py`: `run_redteam.py`, `run_routing.py`, `run_certify.py` nhận `--engine langgraph|dify` và kết quả có cột `engine`

### Implementation for User Story 6

- [ ] T070 [US6] Ghi usage trong `backend/app/runtime/dify_turn.py` qua `record_usage()` của `backend/app/chat/router.py`: purpose `triage` và `agent`, `model` từ metadata Dify, `cost_usd` dùng giá Dify báo nếu có, nếu không tính theo bảng giá hiện có
- [ ] T071 [US6] Đảm bảo trang chi phí (`backend/app/audit/` và `web/src/features/audit/AuditPages.tsx`) hiển thị được purpose `triage` (nhãn "Định tuyến & kiểm duyệt")
- [ ] T072 [US6] Tracing trong `backend/app/runtime/dify_turn.py` qua `backend/app/tracing.py`: span `triage` và `run_agent` bọc lời gọi Dify, gắn `dify_message_id` và `dify_conversation_id` vào metadata; ghi trong `infra/dify/README.md` cách bật Langfuse trong Dify
- [ ] T073 [US6] Thêm `--engine` vào `eval/harness.py`, `eval/run_redteam.py`, `eval/run_routing.py`, `eval/run_certify.py` (đặt `runtime_engine` tương ứng) và cột `engine` + độ trễ chữ đầu tiên trong file kết quả `eval/results/`
- [ ] T074 [US6] Chạy cả ba script với `langgraph` và `dify` (cần Dify thật), điền bảng so sánh (tỉ lệ chặn, chặn nhầm, định tuyến, độ trễ p95, chi phí mỗi lượt) vào `docs/BAO-CAO.md`; `eval/run_redteam.py` đối chiếu mỗi lần chặn với một bản ghi `guard_events` và báo tỉ lệ có bản ghi (SC-006 yêu cầu 100%); nếu vượt ngưỡng SC-002/SC-003/SC-004 thì ghi rõ và báo người dùng trước khi sang Phase 9

**Checkpoint**: Kịch bản 12 đạt; có bảng so sánh (SC-009).

---

## Phase 9: Polish & dọn dẹp

**Purpose**: chuyển hẳn sang Dify sau khi có kết quả so sánh (FR-025), cập nhật tài liệu.

**⚠️ Chỉ bắt đầu khi T074 xong và người dùng đồng ý đổi mặc định.**

- [ ] T075 Đổi mặc định `runtime_engine` sang `"dify"` trong `backend/app/config.py` và `.env.example`; chuyển test chat/certify/documents sang chạy với engine `dify` bằng fixture
- [ ] T076 Xóa engine cũ: `backend/app/runtime/graph.py`, `backend/app/runtime/router.py`, `backend/app/guard/classifier.py`, phần chặn trong `backend/app/guard/rules.py` (giữ `redact()`), nhánh `langgraph` trong `backend/app/runtime/engine.py`, `backend/tests/test_routing.py` và phần test guard cũ trong `backend/tests/test_guard.py` (giữ test `redact()`)
- [ ] T077 Migration `backend/migrations/versions/0007_drop_document_chunks.py` xóa bảng `document_chunks`; xóa model và code embedding pgvector trong `backend/app/knowledge/`
- [ ] T078 Bỏ `langgraph` khỏi `backend/pyproject.toml`, chạy `uv lock`; `grep -ri langgraph backend/app eval web/src` phải rỗng
- [ ] T079 [P] Cập nhật `README.md` (dựng Dify, biến môi trường, sơ đồ kiến trúc mới) ; `docs/DEMO.md` chỉ được thêm ghi chú, không sửa các bước (SC-001)
- [ ] T080 [P] Thay `docs/PLAN-DIFY.md` (đang bị xóa trong working tree) bằng ghi chú ngắn trỏ tới `specs/001-dify-core-migration/`, hoặc xác nhận với người dùng việc xóa hẳn
- [ ] T081 Chạy toàn bộ quickstart.md (mục 1–3 và E2E `cd web && npm run test:e2e`) và đi hết các bước của `docs/DEMO.md` không sửa kịch bản (SC-001) trên máy sạch, đo thời gian dựng (SC-008 ≤ 1 giờ), ghi lệch vào `infra/dify/README.md`
- [ ] T082 Chạy lệnh kiểm tra backend + web ở đầu file; tất cả phải pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: không phụ thuộc
- **Foundational (Phase 2)**: sau Setup; T006 (spike) là cổng dừng; chặn mọi story
- **US1 (Phase 3)**: sau Foundational
- **US2 (Phase 4)**: sau US1 (dùng `dify_turn.py` và DSL triage/runner của US1)
- **US3 (Phase 5)**: sau US1; độc lập với US2 (runner-raw không có kiểm duyệt)
- **US4 (Phase 6)**: sau US1; T054 dùng `contains_blocked_keyword()` của T038 (US2). Trích dẫn từ Dify cần US5 để kiểm tra đầu-cuối
- **US5 (Phase 7)**: sau US1 (handle, MCP handler); độc lập với US2–US4
- **US6 (Phase 8)**: T068–T073 sau US1; T074 cần US1–US5 xong để so sánh có ý nghĩa
- **Polish (Phase 9)**: sau T074 và người dùng đồng ý

### Thứ tự trong US1

T020 → T021 → T022 → T023 (MCP); T024, T025 song song; T026 → T027 → T028, T029 → T030; T031 độc lập.

### Parallel Opportunities

- Phase 1: T002–T005 song song sau T001
- Phase 2: T009–T011 và T014 song song sau T008
- Mỗi story: mọi task test có [P] chạy song song; DSL (`infra/dify/*.yml`) và file web song song với code backend
- Sau US1: US3 và US5 có thể làm song song với US2

---

## Parallel Example: User Story 1

```bash
# Test viết trước, song song:
Task: "Test MCP qua HTTP trong backend/tests/test_mcp_http.py"            # T016
Task: "Test client Dify trong backend/tests/test_runtime_dify.py"         # T017

# DSL song song với code MCP:
Task: "Tạo DSL infra/dify/eduagent-triage.yml"                            # T024
Task: "Tạo DSL infra/dify/eduagent-runner.yml"                            # T025
Task: "Mở rộng turn handle trong backend/app/tools/context.py"            # T020
```

## Parallel Example: User Story 2

```bash
Task: "Tạo infra/dify/moderation-keywords.txt"                            # T036
Task: "Tạo infra/dify/preset-responses.json"                              # T037
Task: "Bỏ ô chủ đề cấm trong web/src/features/classes/PolicyTab.tsx"      # T044
```

## Parallel Example: User Story 5

```bash
Task: "Test backend/tests/test_dify_datasets.py"                          # T059
Task: "Cập nhật backend/tests/test_documents_tools.py"                    # T060
```

---

## Implementation Strategy

### MVP (US1 + US2)

1. Phase 1 + Phase 2 (dừng ở T006 nếu spike không đạt)
2. Phase 3 (US1) → kiểm tra kịch bản 1–3, 14
3. Phase 4 (US2) → kiểm tra kịch bản 4–6, 9, 13

Chỉ US1 thì chạy được nhưng chưa có guard chặn thật. Không cho học sinh dùng engine `dify` trước khi xong US2; vì
vậy MVP tối thiểu để demo là US1 + US2, cả hai đều P1.

### Incremental Delivery

1. MVP (US1 + US2) → demo chat an toàn trên Dify
2. US3 → giáo viên tạo agent, kiểm định qua Dify
3. US5 → tài liệu lớp trong kho Dify
4. US4 → trích dẫn + gợi ý câu hỏi
5. US6 → số liệu so sánh cho báo cáo
6. Phase 9 → bỏ engine cũ

Mỗi bước giữ `RUNTIME_ENGINE=langgraph` làm đường lui cho tới Phase 9.

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- Task cần Dify thật: T006, T007, T074, T081 (và test `@pytest.mark.dify`); mọi task khác làm được offline
- Tránh hai task cùng sửa `backend/app/runtime/dify_turn.py` song song (T027–T029, T041, T045, T054, T066, T070, T072 làm tuần tự)
- Không tự commit; dừng ở mỗi checkpoint để người dùng kiểm tra và commit

---

## Phase 10: Convergence

- [X] T083 Đổi kiểu tham số của 5 tool trong `backend/app/tools/server.py` sang kiểu lỏng (ví dụ `operation: str`, `top_k: int | str`) để mọi kiểm tra tham số chạy trong `registry.run_tool`; hiện tham số sai kiểu (vd `operation="fly"`) bị MCP SDK chặn trước handler nên không có dòng `tool_calls` và không có sự kiện `tool`; thêm ca này vào `backend/tests/test_mcp_http.py` per FR-014 (partial)
- [X] T084 Bật lại chống DNS rebinding cho `/mcp` trong `backend/app/tools/mcp_http.py` với `allowed_hosts` gồm `127.0.0.1:*`, `localhost:*`, `host.docker.internal:*` (và host của test client), thay vì tắt hẳn; nếu giữ quyết định tắt thì ghi lý do vào research R6 và contracts/mcp-tools.md per plan: MCP qua HTTP (unrequested)
- [X] T085 Dọn handle hết hạn chưa từng được tra lại trong `backend/app/tools/context.py` (quét `_live` khi `register()`), để handle của lượt bị gián đoạn không nằm mãi trong bộ nhớ; thêm test per data-model: Turn handle "sống tối đa 10 phút" (partial)
- [X] T086 Viết lại chú thích khối biến Dify trong `.env.example` bằng tiếng Việt, mỗi biến một dòng, như T002 yêu cầu per T002 (partial)
