---

description: "Danh sách task triển khai feature 003: tạo agent, nhóm chat, giao việc và hỏi người"
---

# Tasks: Tạo agent, nhóm chat nhiều agent và người, agent hỏi agent và hỏi người

**Input**: tài liệu thiết kế trong `specs/003-agent-group-delegation/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: có task test. FR-058 yêu cầu bộ kịch bản kiểm thử, plan liệt kê sẵn các file test, và dự án luôn chạy
`pytest`, `vitest` trước khi coi việc là xong. Test dùng LLM `fake` (script lời gọi công cụ bằng `Scripted(tool_calls=…)`
hoặc `respond_with`) và gọi `worker.drain()` để chạy hàng đợi đồng bộ.

**Organization**: task được nhóm theo user story để làm và kiểm tra từng story độc lập.

## Format: `[ID] [P?] [Story] Mô tả`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong).
- **[Story]**: user story của task (US1 đến US7, theo spec.md).
- Đường dẫn tính từ gốc repo: `backend/app/…`, `backend/tests/…`, `web/src/…`.

---

## Phase 1: Setup (hạ tầng dùng chung)

**Purpose**: cấu hình và khung thư mục mới.

- [X] T001 Thêm các biến cấu hình vào `Settings` trong `backend/app/config.py`. Tất cả có mặc định:
  - `handoff_max_depth: int = 2` (0 là tắt hẳn giao việc)
  - `handoff_max_per_run: int = 6`
  - `handoff_max_attempts: int = 2`
  - `handoff_lease_seconds: int = 120`
  - `person_request_hours: int = 72`
  - `approval_card_hours: int = 24`
  - `worker_poll_seconds: float = 1.0`
  - `worker_enabled: bool = True` (test đặt `False` rồi gọi `drain()`)
- [X] T002 [P] Thêm các biến của T001 (ở dạng comment, kèm giá trị mặc định) vào `.env.example`.
- [X] T003 [P] Tạo package `backend/app/orchestration/__init__.py` cùng các file rỗng `models.py`, `handoffs.py`,
  `people.py`, `approvals.py`, `runs.py`, `worker.py`, `router.py`. Tạo `backend/app/chat/groups.py`,
  `backend/app/chat/events.py`, `backend/app/chat/visibility.py`.
- [X] T004 [P] Tạo thư mục `web/src/features/chat/`, `web/src/features/inbox/`, `web/src/features/settings/` và các
  file API client rỗng `web/src/api-client/chat.ts`, `web/src/api-client/inbox.ts`, `web/src/api-client/approvals.ts`.

---

## Phase 2: Foundational (điều kiện tiên quyết cho mọi story)

**Purpose**:
- dữ liệu mới;
- hội thoại kiểu Messenger, gồm chat riêng với từng agent (FR-048, FR-049);
- stream sự kiện có `seq`;
- khung lượt chạy cùng worker;
- công cụ nền tảng;
- lõi duyệt hành động;
- seed lũy đẳng cùng `dev.ps1`.

**⚠️ CRITICAL**: chưa xong phase này thì chưa bắt đầu story nào.

### Dữ liệu

- [X] T005 Sửa model trong `backend/app/chat/models.py` theo data-model.md §1.
  - `Conversation`:
    - `kind` thuộc `direct | group | sandbox`
    - `direct_agent_slug: String(48) nullable`, bắt buộc khi `kind=direct`
    - `default_agent_slug: String(48) nullable`
    - `last_seq: Integer default 0`
    - `archived_at: DateTime nullable`
  - `ChatMessage`:
    - `seq: Integer`, duy nhất trên (`conversation_id`, `seq`)
    - `role` thêm giá trị `system`
    - `sender_user_id` (FK users, nullable)
    - `handoff_id` (FK handoffs, nullable, duy nhất khi khác null)
    - `reply_to_agent: String(48) nullable`
    - `person_request_id`, `approval_card_id`, `run_id` (FK, nullable)
    - `visible_to: JSON nullable`
    - `status` thêm `hidden`
  - Thêm model `ConversationMember` với các cột: `conversation_id`, `user_id` nullable, `agent_slug` nullable,
    `is_admin`, `joined_seq`, `can_see_history` default false, `last_read_seq` default 0, `left_at`.
    - CHECK: đúng một trong hai cột `user_id` và `agent_slug` khác null.
    - Duy nhất trên (`conversation_id`, `user_id`) và (`conversation_id`, `agent_slug`).
- [X] T006 [P] Tạo các model trong `backend/app/orchestration/models.py`, đủ cột và ràng buộc như data-model.md §2:
  - `AgentRun`: `status` thuộc `running | waiting | resumable | done | failed | cancelled`, `source` thuộc
    `chat | sandbox | certify`.
  - `Handoff`: duy nhất trên (`run_id`, `tool_call_id`); `status` thuộc
    `refused | queued | running | answered | failed`; `refusal_reason String(200)`.
  - `PersonRequest`: duy nhất trên (`run_id`, `tool_call_id`); `kind` thuộc
    `question | approval | choice | install_agent`; `status` thuộc
    `draft | open | answered | expired | cancelled | undeliverable`.
  - `ApprovalCard`: duy nhất trên (`run_id`, `tool_call_id`); `status` thuộc `open | allowed | denied | expired`;
    `choices` là tập con của `once | conversation | always | deny | did_it | dont`.
  - `ApprovalRule`: `scope` thuộc `user | class | admin | conversation`; `effect` thuộc `allow | deny | ask`;
    `source` thuộc `card | typed | admin | class`.
  - `ApprovalKindMode`: khoá chính (`action_kind`, `role`); `mode` thuộc
    `members_choose | ask_every_time | do_it_yourself`.
  - `UserSettings`: `extra_vigilant` default false.
- [X] T007 [P] Sửa các model đang có:
  - `backend/app/classes/models.py`: thêm `ClassMember.subject: String(16) nullable`. Thêm vào `DEFAULT_POLICY` các khoá
    `allow_handoffs: True`, `members_can_create_groups: True`, `allow_member_agents: True`.
  - `backend/app/agents/models.py`: thêm `Installation.handoff_allow: JSON nullable`.
  - `backend/app/audit/models.py`: thêm `GuardEvent.private_space: Boolean default True`.
- [X] T008 Đăng ký các model mới trong `backend/app/models.py`.
- [X] T009 Viết migration `backend/migrations/versions/0006_groups_handoffs_approvals.py`. Migration phải:
  - tạo mọi bảng và cột của T005 đến T007;
  - đổi `conversations.kind='chat'` thành `direct`;
  - điền `direct_agent_slug` bằng `agent_slug` của tin assistant gần nhất, hoặc `tro-ly-lop` nếu chưa có;
  - tạo một `conversation_members` cho người tạo;
  - đánh `seq` theo `created_at` cho tin cũ và đặt `last_seq`;
  - chạy được trên cả Postgres và SQLite (dùng `batch_alter_table`).
- [X] T010 Thêm `handoff_to: list[str]` vào `AgentManifest` trong `backend/app/agents/manifest.py`. Ràng buộc:
  `Field(default_factory=list, max_length=8)`, mỗi phần tử khớp `SLUG` và khác `slug` của chính agent.

### Hội thoại kiểu Messenger và quyền xem

- [X] T011 Viết `backend/app/chat/visibility.py`:
  - `can_view_conversation(db, user, conversation)`: là thành viên chưa rời; với `direct` thì chỉ `user_id` của hội thoại.
  - `visible_messages_query(user, conversation)`: lọc theo `seq > joined_seq` (trừ khi `can_see_history`), theo
    `left_at`, và theo `visible_to` (null hoặc chứa user).

  Không xem được thì trả 404 (FR-047, FR-050).
- [X] T012 Viết `next_seq(db, conversation)` trong `backend/app/chat/models.py`, hoặc trong service mới
  `backend/app/chat/service.py`. Hàm tăng `last_seq` theo cách nguyên tử (`UPDATE … RETURNING`, có phương án dự phòng cho
  SQLite). Mọi chỗ tạo `ChatMessage` phải dùng hàm này.
- [X] T013 Viết bus sự kiện và SSE trong `backend/app/chat/events.py`:
  - `publish(conversation_id, event, visible_to=None)`;
  - `subscribe(conversation_id, user)`;
  - endpoint `GET /api/chat/conversations/{id}/events?after=` phát bù từ DB theo người xem, rồi phát trực tiếp, kèm
    `ping` mỗi 20 giây.

  Định dạng sự kiện theo `contracts/conversation-events.md`.
- [X] T014 Viết lại các endpoint hội thoại trong `backend/app/chat/router.py` theo `contracts/rest-api.md` mục Hội thoại:
  - `GET /chat/conversations` trả `ConversationOut` với `last_message`, `unread`, `waiting_for`, kèm tìm theo `q`, sắp
    theo tin mới nhất;
  - `POST /chat/direct` mở hoặc tạo chat riêng, mỗi người, agent và phạm vi chỉ có một chat đang mở;
  - `POST /chat/direct/{id}/restart`;
  - `GET /chat/conversations/{id}/messages?before=&limit=` trả `MessageOut` mới (`seq`, `sender`, `reply_to_agent`,
    `handoffs`, `person_request`, `approval_card`);
  - `POST /chat/conversations/{id}/read`.

  `own_conversation` được thay bằng `visibility.can_view_conversation`.
- [X] T015 Trước khi sửa, ghi mốc thời gian tới chữ đầu tiên vào `eval/results/latency_baseline.json` (chạy bộ câu hỏi
  đơn giản qua runtime hiện tại; dùng lại ở T086 cho SC-001). Sau đó sửa `POST /chat/stream` và `run_turn` trong
  `backend/app/chat/router.py`:
  - `conversation_id` là bắt buộc;
  - với `direct`, agent cố định là `direct_agent_slug` (bỏ trường `agent` của `ChatIn`);
  - tin người và tin agent dùng `next_seq` và được `publish` lên bus;
  - lượt chạy được ghi `AgentRun(status=done)` cùng `run_id` trên tin;
  - khi dựng lịch sử cho mô hình, tin `assistant` của agent khác (có `handoff_id` hoặc `agent_slug` khác agent đang chạy)
    được đưa vào ở dạng `user` với nội dung `[Tên agent]: …`, không phải lời của chính agent (FR-054).

  Hành vi hiện có của lượt không giao việc phải giữ nguyên (SC-001).

### Lượt chạy, worker và công cụ nền tảng

- [X] T016 Thêm vào `PlatformTool` trong `backend/app/tools/registry.py` các thuộc tính: `meta: bool = False`,
  `action_kind: str = "none"` (một trong `none | change | send | share | post | delete | settings | money`),
  `personal_data: bool = False`, `group_only: bool = False`. Đặt `progress_summary.personal_data=True`. Đổi
  `specs_for(manifest, role, room, *, conversation_kind, meta_offers)`:
  - công cụ `meta` được mời không cần có trong manifest;
  - bỏ công cụ `personal_data` khi `conversation_kind="group"`;
  - bỏ công cụ `group_only` ngoài nhóm.

  `guard()` kiểm thêm các luật này.
- [X] T017 Viết `backend/app/orchestration/runs.py`:
  - `save_waiting(ctx, agent, messages, pending)`: lưu `transcript` và `pending` vào `AgentRun(status=waiting)`;
  - `mark_resolved(run_id, tool_call_id, result)`: khi mọi pending có kết quả thì chuyển sang `resumable`;
  - `build_context(run)`: dựng lại `RunContext` theo người dùng gốc, `role` và `room` của run;
  - `resume(run)`: thêm `tool` message và gọi vòng công cụ dùng chung.
- [X] T018 Tách vòng lặp công cụ trong `backend/app/runtime/graph.py` thành hàm dùng lại được,
  `tool_loop(ctx, agent, system, messages, specs, emit)`, dùng cho cả lượt mới lẫn `runs.resume`. Hàm trả thêm trạng thái
  `waiting` khi một công cụ `meta` báo cần chờ. `run_agent` gọi `runs.save_waiting` khi `waiting`. `RunContext` thêm các
  trường `run`, `depth`, `chain`, `root_run_id`, `conversation_kind`, `origin_conversation_id`, `stream: bool` (false với
  luồng nháp của agent được hỏi và với lượt làm tiếp chạy nền).
- [X] T019 Viết `backend/app/orchestration/worker.py`:
  - vòng `asyncio` chạy mỗi `worker_poll_seconds`, gồm ba việc:
    1. lấy `handoffs` đang `queued`, hoặc `running` đã hết lease (Postgres dùng `FOR UPDATE SKIP LOCKED`), để chạy;
    2. lấy `agent_runs` đang `resumable` bằng `UPDATE … WHERE status='resumable'`, để `resume`;
    3. quét `person_requests` và `approval_cards` quá `expires_at` để chuyển sang `expired`.
  - `drain()` chạy hết việc một cách đồng bộ, dùng cho test.
  - `start()` và `stop()`.
- [X] T020 Khởi động và dừng worker trong `lifespan` ở `backend/app/main.py`:
  - chỉ khi `worker_enabled`;
  - khi khởi động, quét việc bị dở: handoff `running` hết lease quay về `queued`, run `running` quá hạn chuyển `failed`.
- [X] T021 Sửa fixture trong `backend/tests/conftest.py`: đặt `worker_enabled=False`, thêm fixture `drain`. Thêm helper
  vào `backend/tests/helpers.py`:
  - `scripted_tool_call(name, args)`;
  - `make_class_with_members(...)`, tạo giáo viên có `subject`, hai học sinh, hai phụ huynh có liên kết và đồng ý;
  - `grant(agent_slug, to=[...])`.

### Lõi duyệt hành động (US3, US5, US6 dùng chung)

- [X] T022 Viết hàm thuần `decide(action_kind, user, role, conversation, room, agent_slug, tool, target, rules,
  kind_mode, extra_vigilant) -> Decision(effect, choices)` trong `backend/app/orchestration/approvals.py`, theo FR-032
  đến FR-035 và research R8:
  - loại luôn phải hỏi (mọi loại trừ `none` và `change`);
  - rồi quy tắc: deny xét trước, quy tắc chặt nhất thắng, không có quy tắc khớp thì không cho, quy tắc hỏng thì deny;
  - chỉ quy tắc `source='card'` mở được một loại luôn phải hỏi;
  - rồi `extra_vigilant` (hỏi với `change`);
  - `choices` theo chế độ: `members_choose` là cả 4, `ask_every_time` là `once` và `deny`, `do_it_yourself` là
    `did_it` và `dont`.
- [X] T023 Viết vòng đời thẻ duyệt trong `backend/app/orchestration/approvals.py`:
  - `open_card(ctx, call, preview)`: luôn ghi vào **hội thoại gốc** cho người dùng gốc (FR-037), là tin `system` có
    `approval_card_id`, `expires_at = now + approval_card_hours`;
  - `answer_card(card_id, user, choice)`: chỉ người dùng gốc, `choice` phải nằm trong `card.choices`, cập nhật có điều
    kiện `status='open'`;
  - `allowed` thì chạy hành động đúng một lần (đặt `executed_at` trong cùng giao dịch);
  - `conversation` và `always` tạo `ApprovalRule(source='card')`;
  - ở chế độ không có người thật (`source` là `sandbox` hoặc `certify`) thì deny ngay (FR-038).
- [X] T024 Viết endpoint `POST /api/approvals/{card_id}/answer` trong `backend/app/orchestration/router.py` và đăng ký
  router trong `backend/app/main.py`.
- [X] T025 [P] Viết bảng chân trị đầy đủ cho `decide()` trong `backend/tests/test_approvals.py`: mọi `action_kind`, mọi
  chế độ, deny trước allow, quy tắc `typed`, `class`, `admin` không mở được loại luôn phải hỏi, `extra_vigilant`.

### Seed và vận hành (nguyên tắc III)

- [X] T026 Sửa `backend/scripts/seed_demo.py`:
  - thêm cờ `--ensure` để chạy lũy đẳng (không tạo trùng);
  - thêm tài khoản `toan@demo.edu.vn` (GV Toán 9A, `subject=toan`), `student2@demo.edu.vn`, `parent2@demo.edu.vn` cùng
    liên kết và đồng ý;
  - đặt `subject` cho giáo viên demo;
  - seed `ApprovalKindMode`: học sinh là `ask_every_time` cho mọi loại, giáo viên và phụ huynh là `members_choose`.
- [X] T027 Sửa `dev.ps1`: sau `alembic upgrade head`, luôn chạy `uv run python -m scripts.seed_demo --ensure`; khi
  `-Setup` hoặc database mới thì giữ seed đầy đủ như hiện nay. Kiểm tra cú pháp bằng
  `pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content dev.ps1 -Raw)) | Out-Null"`. Trong **cùng thay đổi này**,
  cập nhật mục "Chạy local" của `README.md` (lệnh `seed_demo --ensure`, tài khoản demo mới), theo nguyên tắc III.
- [X] T028 [P] Viết test trong `backend/tests/test_events.py`:
  - `seq` tăng dần và duy nhất;
  - phát bù theo `after`;
  - lọc theo `visible_to` và `joined_seq`;
  - người ngoài nhận 404;
  - migration chuyển hội thoại cũ thành `direct` (dùng một hội thoại `kind=chat` tạo trước).
- [X] T029 Viết `web/src/api-client/chat.ts` (hàm gọi các endpoint ở T014, `openEvents(conversationId, after)`) và thêm
  kiểu vào `web/src/api-client/types.ts`: `ConversationOut`, `MessageOut` mới, `HandoffNode`, `PersonRequestOut`,
  `ApprovalCardOut`. Mở rộng `web/src/api-client/chatStream.ts` để nhận các sự kiện mới (`message`, `message_update`,
  `handoff`, `handoff_answer`, `run`, `approval_card`, `person_request`, `ping`).
- [X] T030 Viết hook `web/src/features/chat/useConversationEvents.ts`: nối lại tự động bằng `after = seq` lớn nhất, bỏ tin
  có `seq` nhỏ hơn hoặc bằng `seq` đã nhận (SC-005), gộp `message_update`.
- [X] T031 Viết trang Messenger hai cột `web/src/features/chat/ChatHomePage.tsx` và `web/src/features/chat/ConversationList.tsx`:
  - danh sách gồm chat riêng với từng agent và các nhóm, xem trước tin cuối, số tin chưa đọc, ô tìm;
  - nút "Chat với agent" (chọn agent dùng được) và nút "Nhóm mới" (để trống tới US4);
  - cột phải dùng `ChatThread`.

  Thêm route `/{role}/chat` trong `web/src/app/router.ts` và mục menu trong `web/src/components/AppShell.tsx`.
- [X] T032 Sửa `web/src/components/chat/ChatThread.tsx` và `web/src/components/chat/MessageBody.tsx`:
  - người gửi có nhiều loại (người, agent, hệ thống), có `role_label`;
  - sắp theo `seq`;
  - tin `hidden` hiện "Nội dung đã được ẩn";
  - nhận sự kiện từ `useConversationEvents`;
  - giữ nguyên luồng `text_delta` của lượt đang chạy.

**Checkpoint**:
- Chat riêng với từng agent chạy như trước, trên giao diện Messenger.
- Hội thoại cũ hiển thị đúng.
- Stream sự kiện phát bù đúng.
- `decide()` xanh toàn bộ bảng chân trị.

---

## Phase 3: User Story 1 - Agent hỏi một hoặc nhiều agent khác trong chat riêng (Priority: P1) 🎯 MVP

**Goal**:
- Agent chính giao việc cho các agent được cấp quyền, bất đồng bộ.
- Câu trả lời được ghi nguyên văn vào thanh "▸ Đã hỏi …" mở/đóng được.
- Agent chính có một lượt làm tiếp để viết kết luận (FR-013 đến FR-022).

**Independent Test**: cấp cho Gia sư Toán quyền giao việc tới `on-tap-tai-lieu` và `tao-de`. Gửi câu hỏi phức tạp: phải
có hai thanh "Đã hỏi" với đúng nguyên văn câu trả lời, và một tin kết luận. Gửi câu hỏi đơn giản: không có thanh nào
(quickstart kịch bản 1).

### Tests for User Story 1

- [X] T033 [P] [US1] Viết test luồng đầy đủ trong `backend/tests/test_handoffs.py`:
  - script cho A gọi `message_agent` tới B và C;
  - `drain()` chạy hàng đợi;
  - kiểm tra hai `Handoff` ở trạng thái `answered`, mỗi cái đúng một `ChatMessage` có `handoff_id` và nội dung nguyên văn;
  - run của A từ `waiting` sang `resumable` sang `done`;
  - có đúng một tin kết luận, và tin này không chứa nguyên văn câu trả lời (FR-014, FR-017);
  - câu hỏi đơn giản không tạo `Handoff`.
- [X] T034 [P] [US1] Viết test lỗi và tính một lần trong `backend/tests/test_handoffs.py`:
  - B ném lỗi thì được thử lại tới `handoff_max_attempts`, rồi `failed`; A nhận `no_answer` và không có mã lỗi kỹ thuật
    trong nội dung (FR-016, SC-006);
  - chạy `drain()` hai lần, hoặc giả lập hết lease rồi chạy lại, thì không có câu trả lời thứ hai (FR-015, SC-005);
  - câu trả lời bị kiểm duyệt ẩn thì A nhận `hidden`;
  - câu trả lời về sau khi A đã làm tiếp thì được đánh dấu `late` và không đánh thức A lần nữa.
- [X] T035 [P] [US1] Viết test component `web/src/components/chat/HandoffBar.test.tsx`: thanh mở và đóng được, hiển thị
  yêu cầu và nguyên văn câu trả lời, trạng thái `queued | running | answered | no_answer | refused | hidden | late`, lồng
  được, mặc định đóng khi đã có tin kết luận.

### Implementation for User Story 1

- [X] T036 [US1] Viết `effective_grants(resolved_agent, installation)` trong `backend/app/agents/service.py`, trả
  `manifest.handoff_to ∩ (installation.handoff_allow or manifest.handoff_to)`. Viết `handoff_targets(ctx, agent)` trong
  `backend/app/orchestration/handoffs.py`, trả các agent đích hợp lệ theo data-model.md §4 (trong US1 chỉ cần kiểm quyền
  và `available_agents` của người dùng gốc; US2 bổ sung phần còn lại).
- [X] T037 [US1] Đăng ký công cụ meta `message_agent` trong `backend/app/tools/registry.py`, tham số theo
  `contracts/platform-tools.md`: `agent` (enum gồm các đích hợp lệ), `task`, `bounds`, `good_answer` (mỗi trường 1 đến
  1000 ký tự), `attachments` (tối đa 4000). Chỉ mời khi `handoff_targets` không rỗng.
- [X] T038 [US1] Viết `request_handoff(ctx, agent, call)` trong `backend/app/orchestration/handoffs.py`. Nền tảng tự điền
  `from_agent`, `conversation_id` (hội thoại gốc), `depth`, `chain` (FR-008). Hàm tạo `Handoff(status=queued)`, tăng
  `handoff_count` của root, trả kết quả `{"status":"queued",…}` cho mô hình, và báo `tool_loop` là cần chờ. Hàm `publish`
  sự kiện `handoff`.
- [X] T039 [US1] Viết `execute_handoff(handoff)` trong `backend/app/orchestration/handoffs.py`, được worker gọi:
  - dựng `RunContext` cho agent được hỏi theo người dùng gốc (vai trò, quyền, chính sách lớp; FR-010), với `stream=False`,
    `depth+1`, `chain+[from_agent]`;
  - tin `user` duy nhất dựng từ `task`, `bounds`, `good_answer`, `attachments`, không có lịch sử (FR-007);
  - chạy `screen`, `run_agent`, `review` theo người dùng gốc;
  - ghi `answer` và tạo `ChatMessage(role=assistant, agent_slug=to_agent, handoff_id, reply_to_agent=from_agent)` trong
    một giao dịch, dựa vào ràng buộc duy nhất;
  - gọi `runs.mark_resolved`, rồi `publish` `handoff_answer` và `handoff`;
  - lỗi thì tăng `attempts` và quay về `queued`, hoặc chuyển `failed`.
- [X] T040 [US1] Viết lượt làm tiếp trong `backend/app/orchestration/runs.py`:
  - `resume(run)` tạo đúng một tin kết luận mới của agent hỏi qua `review`, rồi `publish` `message` và `run`;
  - prompt bổ sung yêu cầu dẫn tới các câu trả lời, không chép lại, và ghi tên các agent đã đóng góp (FR-017).
- [X] T041 [US1] Thêm hướng dẫn giao việc vào `backend/app/runtime/prompts.py`:
  - danh sách agent đích (tên, mô tả, năng lực);
  - chỉ giao khi cần;
  - báo người dùng là đang hỏi ai;
  - không tự trả lời thay agent kia.

  Không thêm gì khi không có đích.
- [X] T042 [US1] Trả cây `handoffs` trong `MessageOut` ở `backend/app/chat/router.py`, gồm `children` cho tầng sâu hơn,
  để vẽ các thanh lồng nhau (FR-020 đến FR-022).
- [X] T043 [P] [US1] Viết `web/src/components/chat/HandoffBar.tsx` theo T035 (avatar `Mascot`, tên, trạng thái tiếng
  Việt: "Đang hỏi", "Đã trả lời", "Không nhận được câu trả lời", "Bị từ chối", "Nội dung đã được ẩn", "Về muộn"). Gắn
  component vào `ChatThread.tsx` dưới tin của agent hỏi, và cập nhật theo sự kiện `handoff` cùng `handoff_answer`.
- [X] T044 [US1] Thêm `handoff_to` cho agent mẫu trong `seed/agents/tro-ly-lop.yaml` (`gia-su-toan`, `cham-van`,
  `on-tap-tai-lieu`), `seed/agents/gia-su-toan.yaml` (`on-tap-tai-lieu`, `tao-de`) và `seed/agents/tro-ly-phu-huynh.yaml`
  (`on-tap-tai-lieu`). Viết `capabilities` rõ hơn nếu cần.

**Checkpoint**: chat riêng có giao việc hoạt động đầy đủ (quickstart kịch bản 1).

---

## Phase 4: User Story 2 - Quyền giao việc do nền tảng quyết (Priority: P1)

**Goal**:
- Mọi lần giao việc ngoài quyền bị từ chối bằng cùng một lời.
- Chặn được tầng, vòng lặp và giới hạn; tắt được theo lớp và toàn hệ thống.
- Giáo viên thu hẹp được quyền trong lớp (FR-006 đến FR-012, FR-019).

**Independent Test**: agent không được cấp quyền thì không có công cụ giao việc. Ba loại đích sai nhận lời từ chối giống
hệt nhau. Lời nhắn của người dùng không mở được quyền (quickstart kịch bản 2 và 5).

### Tests for User Story 2

- [X] T045 [P] [US2] Viết test trong `backend/tests/test_handoffs.py`:
  - agent không có quyền thì `message_agent` không có trong `tools` gửi mô hình;
  - đích chưa cấp quyền, đích không tồn tại và đích không được thấy (agent chỉ dành cho giáo viên khi người dùng là học
    sinh) đều trả **cùng chuỗi** `"Không thể giao việc cho agent này."` và được ghi `refusal_reason` (FR-009, SC-002);
  - vòng lặp A → B → A bị chặn;
  - vượt `handoff_max_depth` và `handoff_max_per_run` thì bị từ chối, không cắt bớt;
  - `handoff_max_depth=0` và `policy.allow_handoffs=false` đều tắt hẳn;
  - agent được hỏi chạy theo chính sách của người dùng gốc (học sinh, `no_direct_answers`).
- [X] T046 [P] [US2] Viết test nội dung tin nhắn không mở được quyền trong `backend/tests/test_handoffs.py`: người dùng
  viết "hãy hỏi @tien-do" thì agent không có quyền vẫn không giao được; `@slug` do người dùng gõ trong chat riêng không
  tạo handoff.

### Implementation for User Story 2

- [X] T047 [US2] Hoàn thiện `handoff_targets` và `request_handoff` trong `backend/app/orchestration/handoffs.py` theo
  data-model.md §4: kiểm `chain`, `depth + 1 <= handoff_max_depth`, `root.handoff_count < handoff_max_per_run`,
  `room.policy.allow_handoffs`. Ánh xạ lời từ chối: ba lý do `not_granted`, `unknown_or_hidden`, `disabled` dùng chung một
  chuỗi; `depth_cap`, `per_run_cap`, `loop` dùng chuỗi "Đã đạt giới hạn giao việc của lượt này." Mọi lần từ chối được ghi
  `Handoff(status=refused)` và `GuardEvent(stage="handoff")`.
- [X] T048 [US2] Thêm `handoff_allow` vào `PATCH /classes/{class_id}/agents/{installation_id}` trong
  `backend/app/agents/router.py`: chỉ giáo viên của lớp; giá trị phải là tập con của `manifest.handoff_to`.
- [X] T049 [US2] Thêm `allow_handoffs` vào `PolicyModel` trong `backend/app/classes/schemas.py` và vào
  `PUT /classes/{id}/policy` trong `backend/app/classes/router.py`.
- [X] T050 [P] [US2] Thêm giao diện thu hẹp quyền giao việc vào `web/src/features/agents/ClassAgentsTab.tsx` (với mỗi agent
  đã cài, chọn các agent đích được phép trong lớp). Thêm công tắc "Giao việc giữa agent" vào trang chính sách lớp trong
  `web/src/features/classes/ClassDetailPage.tsx`.

**Checkpoint**: quickstart kịch bản 2 và 5 đạt.

---

## Phase 5: User Story 3 - Xin duyệt hoặc xin câu trả lời của giáo viên, phụ huynh (Priority: P1)

**Goal**:
- `ask_person` hỏi được chính người dùng, giáo viên đúng môn, chủ lớp hoặc phụ huynh.
- Gửi cho người khác phải qua thẻ duyệt.
- Có hộp yêu cầu.
- Câu trả lời về đúng hội thoại gốc, kể cả từ tầng sâu (FR-024 đến FR-031).

**Independent Test**: quickstart kịch bản 3, 3b và 3c.

### Tests for User Story 3

- [X] T051 [P] [US3] Viết test trong `backend/tests/test_people.py`:
  - `allowed_recipients` của học sinh gồm giáo viên của lớp (có môn), chủ lớp và phụ huynh của chính em đó; không có
    phụ huynh của học sinh khác; `user_id` lạ bị từ chối (FR-025);
  - hỏi `self` không cần thẻ duyệt;
  - hỏi giáo viên thì tạo thẻ `send` với `choices=["once","deny"]` cho học sinh; `deny` thì không tạo `PersonRequest`
    `open`;
  - `once` thì có một `PersonRequest(open)` và có trong inbox của giáo viên;
  - trả lời hai lần thì lần hai nhận 409 (FR-029);
  - câu trả lời được ghi vào hội thoại gốc và đánh thức run, kể cả khi `ask_person` được gọi từ lượt chạy của agent được
    hỏi ở tầng 2 (SC-004);
  - hết hạn và huỷ đều báo cho agent;
  - người nhận rời lớp thì câu hỏi thành `undeliverable`;
  - nội dung vi phạm thì không đưa ra duyệt; câu trả lời vi phạm của người nhận bị ẩn trước khi tới agent và học sinh
    (FR-031);
  - chế độ không có người thật thì `undeliverable` (FR-038).
- [X] T052 [P] [US3] Viết test component `web/src/components/chat/PersonRequestCard.test.tsx` và
  `web/src/components/chat/ApprovalCard.test.tsx`: chỉ người được phép mới thấy nút; đã trả lời thì khoá nút; hiển thị
  các lựa chọn của agent cùng ô trả lời tự do.

### Implementation for User Story 3

- [X] T053 [US3] Viết `allowed_recipients(db, user, room, conversation)` trong `backend/app/orchestration/people.py`, dựa
  trên `class_members` (`role`, `subject`), `ClassRoom.owner_id` (chủ lớp) và `parent_links`. Với giáo viên và phụ huynh,
  người nhận là thành viên cùng lớp hoặc cùng nhóm.
- [X] T054 [US3] Đăng ký công cụ meta `ask_person` trong `backend/app/tools/registry.py` với `action_kind="send"` (riêng
  `recipient=self` thì `action_kind="none"`). Tham số: `recipient` (`self | teacher | homeroom | parent | <user_id>`),
  `subject`, `question`, `kind` (`approval | question | choice`), `options`. Công cụ luôn được mời, trừ khi lượt đã sang
  luồng hỗ trợ an toàn.
- [X] T055 [US3] Viết `request_person(ctx, agent, call)` trong `backend/app/orchestration/people.py`:
  - ẩn thông tin cá nhân và kiểm duyệt `question` bằng `rules.screen_output` và `classifier`;
  - giải `recipient` ra người cụ thể; nhiều giáo viên cùng môn thì đưa danh sách vào preview của thẻ duyệt để người dùng
    chọn;
  - gọi `approvals.decide("send", …)`: `ask` thì `open_card`; `allow` thì tạo `PersonRequest(open,
    expires_at=now+person_request_hours)`;
  - ghi tin `system` có `person_request_id` vào hội thoại gốc (trong nhóm thì chỉ khi `private_to_recipient` là false);
  - báo `tool_loop` là cần chờ, và `publish` `person_request` cùng `run`.
- [X] T056 [US3] Viết `answer_request(request_id, user, choice, text)` và `cancel_request(...)` trong
  `backend/app/orchestration/people.py`:
  - cập nhật có điều kiện `status='open'`;
  - chạy câu trả lời qua `screen_input` (ẩn thông tin cá nhân) **và** kiểm duyệt nội dung (`rules.screen_output` cùng
    `classifier.review_output` theo người dùng gốc); không qua thì câu trả lời được lưu ở trạng thái `hidden` và agent
    nhận "Câu trả lời đã bị ẩn" (FR-031);
  - ghi tin câu trả lời dưới tên người trả lời vào hội thoại gốc;
  - gọi `runs.mark_resolved` với kết quả theo `contracts/platform-tools.md`.
- [X] T057 [US3] Viết endpoint trong `backend/app/orchestration/router.py`: `GET /api/inbox`, `GET /api/inbox/count`,
  `POST /api/person-requests/{id}/answer`, `POST /api/person-requests/{id}/cancel`. Thêm `inbox_open` vào
  `GET /api/auth/me` trong `backend/app/auth/router.py`.
- [X] T058 [US3] Thêm hướng dẫn hỏi người vào `backend/app/runtime/prompts.py`:
  - khi cần quyết định của người thì hỏi, không đoán, không đẩy cho agent khác;
  - hỏi lại người dùng khi thiếu thông tin;
  - không tự gửi khi học sinh chưa đồng ý.
- [X] T059 [P] [US3] Viết `web/src/components/chat/ApprovalCard.tsx` (tóm tắt, xem trước, người nhận, các nút theo
  `choices`) và `web/src/components/chat/PersonRequestCard.tsx` (lựa chọn, ô trả lời tự do, trạng thái, "Đang chờ … trả
  lời", nút huỷ cho người hỏi). Gắn hai component vào `ChatThread.tsx`. Viết API client trong
  `web/src/api-client/approvals.ts` và `web/src/api-client/inbox.ts`.
- [X] T060 [US3] Viết `web/src/features/inbox/InboxPage.tsx` (lọc theo trạng thái và lớp, trả lời ngay trong trang với
  tối đa 2 thao tác; SC-011). Thêm route `/{role}/inbox` vào `web/src/app/router.ts` và huy hiệu số câu hỏi đang mở vào
  `web/src/components/AppShell.tsx`.

**Checkpoint**: quickstart kịch bản 3, 3b, 3c đạt; câu trả lời về đúng hội thoại gốc.

---

## Phase 6: User Story 4 - Nhóm chat có nhiều agent và nhiều người (Priority: P2)

**Goal**:
- Nhóm riêng tư thuộc một lớp; học sinh chỉ thêm được người theo quy tắc.
- Mọi thành viên thấy tin gần như ngay.
- Định tuyến có lựa chọn "không ai".
- Câu trả lời giao việc là tin riêng có nhãn.
- Dữ liệu riêng được chuyển sang chat riêng (FR-039 đến FR-047).

**Independent Test**: quickstart kịch bản 6, 7 và 8.

### Tests for User Story 4

- [X] T061 [P] [US4] Viết test trong `backend/tests/test_groups.py`:
  - giáo viên, học sinh, phụ huynh đều tạo được nhóm; `members_can_create_groups=false` chặn học sinh và phụ huynh;
  - học sinh thêm được học sinh cùng lớp, giáo viên của lớp, phụ huynh của chính mình, agent của lớp; thêm phụ huynh của
    học sinh khác bị 422; `candidates` không chứa người đó (FR-039);
  - người ngoài nhóm, kể cả chủ lớp, nhận 404 với nhóm, tin và events (FR-040);
  - thành viên mới không thấy lịch sử trừ khi `can_see_history`; thành viên bị bớt không nhận tin mới (FR-047).
- [X] T062 [P] [US4] Viết test định tuyến và giao việc trong nhóm trong `backend/tests/test_groups.py`:
  - `@agent` thì agent đó nhận; tin chỉ gọi `@người` hoặc trò chuyện giữa người với người thì không agent nào lên tiếng;
    độ tin cậy thấp thì agent mặc định nhận (FR-043);
  - agent viết `@Tên` thì tạo `Handoff` (FR-044);
  - câu trả lời là tin riêng có `reply_to_agent` và chỉ xuất hiện một lần;
  - agent theo chính sách của người gửi (FR-045);
  - `progress_summary` không được mời trong nhóm;
  - `reply_privately` ghi câu báo trong nhóm và tạo hoặc mở chat riêng cho người hỏi; thành viên khác không thấy câu trả
    lời (FR-046);
  - phản hồi hỗ trợ an toàn trong nhóm có `visible_to=[người nhắn]`.

### Implementation for User Story 4

- [X] T063 [US4] Viết service và endpoint nhóm trong `backend/app/chat/groups.py`, đăng ký trong `backend/app/main.py`:
  - `POST /chat/groups`, `PATCH /chat/groups/{id}`, `POST /chat/groups/{id}/members`,
    `DELETE /chat/groups/{id}/members/{member_id}`, `GET /chat/groups/{id}/candidates`;
  - quy tắc thành viên theo data-model.md `conversation_members`;
  - `is_admin` cho người tạo và cho giáo viên trong nhóm;
  - nhóm tối đa 50 thành viên người và 8 agent.
- [X] T064 [US4] Viết `route_group(text, agents, members, sender, model, mode)` trong `backend/app/runtime/router.py`:
  - `@agent`;
  - `@người` (không có `@agent`) thì `none`;
  - router LLM có thêm lựa chọn `"none"` trong prompt JSON;
  - router từ khoá trả `none` khi điểm dưới `MIN_KEYWORD_SCORE`;
  - độ tin cậy thấp thì `default_agent_slug`.

  Thứ tự trong danh sách không được ảnh hưởng tới kết quả.
- [X] T065 [US4] Sửa `run_turn` trong `backend/app/chat/router.py` cho nhóm:
  - lưu và `publish` tin người trước;
  - xếp hàng lượt theo thứ tự đến (khoá theo hội thoại);
  - `route_group` trả `none` thì kết thúc lượt mà không có tin agent;
  - ngữ cảnh lấy tin nhóm người gửi được xem: tin agent khác hiện là `[Tên]: …`, bỏ tin `hidden` (FR-045, research R7);
  - `RunContext.conversation_kind="group"`.
- [X] T066 [US4] Chuyển `@Tên` do agent viết trong nhóm thành `request_handoff` trong `backend/app/runtime/graph.py`, sau
  `run_agent` và trước `review`, theo đúng quyền và giới hạn của US2.
- [X] T067 [US4] Đăng ký công cụ meta `reply_privately` (`group_only=True`) trong `backend/app/tools/registry.py`. Viết
  phần xử lý trong `backend/app/orchestration/runs.py`:
  - ghi câu cố định "Mình sẽ trả lời riêng cho bạn trong chat riêng." vào nhóm;
  - `POST /chat/direct` nội bộ cho người gửi và agent;
  - chép câu hỏi rồi chạy lượt ở chat riêng;
  - `PersonRequest` phát sinh từ nhóm có dữ liệu riêng thì đặt `private_to_recipient=True`.
- [X] T068 [US4] Đặt `visible_to=[người nhắn]` cho phản hồi hỗ trợ an toàn trong nhóm, trong `backend/app/runtime/graph.py`
  (`_blocked`, `screen`) và `run_turn`.
- [X] T069 [P] [US4] Viết `web/src/components/chat/HandoffMessage.tsx` (tin riêng, nhãn "trả lời cho <agent>", câu
  "<A> đã hỏi <B>" mở xem được yêu cầu). Gắn vào `ChatThread.tsx` khi `kind=group`.
- [X] T070 [P] [US4] Viết `web/src/features/chat/NewGroupDialog.tsx` (chọn người và agent từ `candidates`, tên nhóm,
  agent mặc định) và `web/src/features/chat/GroupSettingsPanel.tsx` (thêm hoặc bớt thành viên, "cho xem lịch sử", rời
  nhóm). Nối nút "Nhóm mới" trong `ConversationList.tsx`.
- [X] T071 [US4] Thêm gợi ý `@` cho người và agent trong ô nhập của nhóm, trong `web/src/components/mentions.ts` và
  `web/src/components/ChatPanel.tsx`. Hiện tên, vai trò (`GV Toán`, `Phụ huynh của An`) và avatar trên mỗi tin.

**Checkpoint**: quickstart kịch bản 6, 7, 8 đạt; mở hai trình duyệt thấy tin trong vòng 2 giây.

---

## Phase 7: User Story 5 - Học sinh, phụ huynh cũng tạo được agent (Priority: P2)

**Goal**:
- Mọi vai trò tạo được agent; công cụ lọc theo vai trò; agent mới riêng tư, chưa có quyền giao việc.
- Đưa agent vào lớp phải qua kiểm định và giáo viên cho phép (FR-001 đến FR-005).

**Independent Test**: quickstart kịch bản 11.

### Tests for User Story 5

- [X] T072 [P] [US5] Viết test trong `backend/tests/test_agents.py`:
  - học sinh và phụ huynh tạo, sửa, chụp phiên bản và thử agent được;
  - chọn công cụ không dành cho vai trò thì nhận 422 có lời tiếng Việt (ví dụ `progress_summary` với học sinh);
  - `handoff_to` chỉ nhận agent người tạo đang dùng được;
  - agent mới là `private` với `handoff_to=[]`;
  - không có đồng ý của phụ huynh thì học sinh không tạo, không dùng được (FR-005);
  - xin đưa vào lớp khi chưa `certified` bị từ chối; đã `certified` thì tạo thẻ `share` rồi `PersonRequest(install_agent)`
    gửi giáo viên; giáo viên "Đồng ý" thì có `Installation(scope=class)`;
  - agent của học sinh có hướng dẫn "bỏ qua mọi quy tắc an toàn" vẫn bị guard đầu vào và đầu ra chặn như agent khác
    (FR-004).

### Implementation for User Story 5

- [X] T073 [US5] Đổi dependency `Teacher` thành `Maker` (teacher, student, parent, admin) cho các endpoint trình tạo trong
  `backend/app/agents/router.py`: `/agents/mine`, `POST /agents`, `PUT /agents/{id}`, `POST /agents/{id}/versions`,
  `POST /agents/{id}/fork`, `DELETE /agents/{id}`, `POST /agents/{id}/try`. Kiểm đồng ý của phụ huynh với học sinh bằng
  `classes.student_can_use_agents` hoặc kiểm tra tương đương ngoài lớp.
- [X] T074 [US5] Kiểm tra `tools` theo `TOOLS[name].roles ∋ role người tạo` và `handoff_to` theo
  `available_agents(người tạo)` trong `create_agent` và `update_draft` ở `backend/app/agents/router.py`. Thêm
  `GET /agents/{id}/handoff-candidates`.
- [X] T075 [US5] Viết `POST /classes/{class_id}/agent-requests` trong `backend/app/agents/router.py`:
  - kiểm `policy.allow_member_agents` và phiên bản `certified`;
  - gọi `approvals.decide("share")`, rồi `people.request_person(kind="install_agent", recipient=homeroom)`;
  - khi giáo viên trả lời "Đồng ý" thì tạo `Installation` đúng như quy tắc của màn hình cài agent.
- [X] T076 [P] [US5] Sửa `web/src/features/agents/BuilderPage.tsx`:
  - mở cho mọi vai trò, công cụ lọc theo vai trò;
  - thêm mục "Được giao việc cho" (chọn từ `handoff-candidates`);
  - thêm nút "Xin đưa vào lớp" cho học sinh và phụ huynh.

  Thêm route builder cho `student` và `parent` trong `web/src/app/router.ts` và menu trong `AppShell.tsx`.

**Checkpoint**: quickstart kịch bản 11 đạt.

---

## Phase 8: User Story 6 - Duyệt hành động theo kiểu OpenBot (Priority: P2)

**Goal**:
- Đủ bốn lựa chọn, quy tắc theo hội thoại và "luôn cho phép".
- Có công tắc "Cực kỳ cẩn thận" và chế độ theo vai trò do admin đặt.
- Thẻ hiện ở hội thoại gốc (FR-032 đến FR-038).

Phần lõi đã làm ở Phase 2.

**Independent Test**: quickstart kịch bản 10; học sinh chỉ thấy hai lựa chọn.

### Tests for User Story 6

- [X] T077 [P] [US6] Viết test luồng trong `backend/tests/test_approvals.py`:
  - "Cho phép trong hội thoại này" làm lần thứ hai trong cùng hội thoại không hỏi lại, sang hội thoại khác thì hỏi lại;
    tắt thì hỏi lại;
  - "Luôn cho phép ở đây" tạo quy tắc và xoá được;
  - `do_it_yourself` thì hành động không bao giờ chạy;
  - thẻ hết hạn thì không chạy; bấm lại không chạy lần hai (SC-013);
  - hành động phát sinh ở lượt chạy của agent được hỏi thì thẻ nằm ở hội thoại gốc; không đưa về được thì deny.

### Implementation for User Story 6

- [X] T078 [US6] Viết endpoint trong `backend/app/orchestration/router.py`: `GET/PATCH /api/settings/approvals`
  (`extra_vigilant`, danh sách quy tắc và cho phép theo hội thoại), `DELETE /api/settings/approvals/rules/{id}`,
  `GET/PUT /api/admin/approvals/modes`, `GET/POST/DELETE /api/admin/approvals/rules`. Quy tắc của admin, lớp và quy tắc
  gõ tay chỉ được `deny` hoặc `ask` với loại luôn phải hỏi (FR-034).
- [X] T079 [US6] Gọi `approvals.decide` cho mọi lời gọi công cụ có `action_kind` khác `none` trong `tool_loop` ở
  `backend/app/runtime/graph.py`, kể cả `change` khi `extra_vigilant` bật. Khi `ask` thì `open_card` rồi dừng chờ; khi
  `deny` thì trả cho mô hình "Người dùng đã từ chối".
- [X] T080 [P] [US6] Viết `web/src/features/settings/ApprovalSettings.tsx` (công tắc "Cực kỳ cẩn thận", danh sách quy tắc
  và cho phép theo hội thoại, nút xoá hoặc tắt) và trang admin chọn chế độ theo loại và vai trò (thêm vào khu admin hiện
  có). Thêm route `/{role}/settings/approvals` vào `web/src/app/router.ts`.

**Checkpoint**: quickstart kịch bản 10 đạt; bảng chân trị và luồng xanh.

---

## Phase 9: User Story 7 - Theo dõi hoạt động, kèm quyền riêng tư (Priority: P3)

**Goal**:
- Có trang hoạt động agent và nhật ký giao việc, câu hỏi gửi người, quyết định duyệt.
- Giáo viên chỉ thấy các nhóm mình là thành viên.
- Không cảnh báo nào từ không gian riêng tư tới giáo viên hay phụ huynh (FR-050, FR-051, FR-055 đến FR-057).

**Independent Test**: quickstart kịch bản 9; trang hoạt động của Trợ lý lớp có đủ các lần giao việc và từ chối kèm lý do.

### Tests for User Story 7

- [X] T081 [P] [US7] Viết test trong `backend/tests/test_privacy.py`:
  - giáo viên không thấy chat riêng của học sinh, không thấy nhóm mình không tham gia, không thấy sự kiện an toàn từ các
    nơi đó, kể cả dấu hiệu tự làm hại; học sinh vẫn nhận phản hồi kèm Tổng đài 111 (FR-051);
  - phụ huynh không xem được chat riêng của con; báo cáo học tập vẫn ra số đếm tổng hợp nhưng không còn từ khoá lấy từ
    tin nhắn (cả báo cáo phụ huynh, tab "Tiến độ" của giáo viên và `progress_summary`);
  - admin thấy sự kiện nhưng `excerpt` rỗng khi `private_space=true`;
  - chủ agent xem được hoạt động của agent mình nhưng không có nội dung hội thoại của người khác;
  - `/admin/usage` tách được lượt có và không có giao việc.

### Implementation for User Story 7

- [X] T082 [US7] Sửa `RunContext.log` trong `backend/app/runtime/graph.py` để điền `private_space`. Sửa
  `GET /classes/{class_id}/audit` trong `backend/app/audit/router.py`: chỉ trả sự kiện của nhóm mà giáo viên là thành viên.
  Sửa `GET /audit/events`: bỏ `excerpt` khi `private_space`. Bỏ mọi đường cảnh báo tới giáo viên hoặc phụ huynh cho sự
  kiện từ không gian riêng tư. Trong `backend/app/reports/service.py` và công cụ `progress_summary`
  (`backend/app/tools/impl.py`), bỏ `frequent_keywords` lấy từ tin nhắn của chat riêng và nhóm; báo cáo chỉ còn số đếm
  (số lượt hỏi, agent đã dùng) (FR-050).
- [X] T083 [US7] Đưa giao việc, câu hỏi gửi người và quyết định duyệt vào nhật ký, trong `backend/app/audit/router.py`
  cùng một hàm truy vấn mới trong `backend/app/orchestration/handoffs.py`. Mỗi dòng có đủ trạng thái, kèm quy tắc hoặc
  giới hạn đã chặn (FR-055, FR-056).
- [X] T084 [US7] Viết `GET /agents/{id}/activity` trong `backend/app/agents/router.py` (lần chạy, giao việc, từ chối, tệp
  đã lưu chỉ có tên và kích thước) và `GET /me/activity` trong `backend/app/orchestration/router.py`. Thêm
  `turns_with_handoff` và `turns_without_handoff` vào `GET /admin/usage` trong `backend/app/audit/router.py`.
- [X] T085 [P] [US7] Viết `web/src/features/agents/AgentActivityPage.tsx`. Sửa `web/src/features/audit/AuditLogView.tsx`
  để hiện các loại sự kiện mới và ghi rõ "Chỉ gồm các nhóm bạn tham gia".

**Checkpoint**: quickstart kịch bản 9 đạt.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T086 [P] Viết `eval/delegation_scenarios.yaml` và `eval/run_delegation.py` (FR-058), gồm năm nhóm ca tương đương
  OpenBot (luồng nhiều tầng, dữ liệu ngoài phạm vi, không gửi ra ngoài khi chưa duyệt, không bịa, quyền bị chặn ở tầng
  nền tảng), thêm ca lách quyền, chèn lỗi mạng và riêng tư nhóm.
  - Chế độ `fake` kiểm tra hàng rào (SC-002 đến SC-006, SC-013).
  - `--live` đo SC-007 và SC-014.
  - `--latency` đo thời gian tới chữ đầu tiên (trung vị) của bộ câu hỏi đơn giản và so với tệp mốc
    `eval/results/latency_baseline.json` (ghi trước khi đổi runtime, ở bước T015) để kiểm SC-001.
  - Mô tả cách chạy trong `eval/README.md`.
- [X] T087 [P] Thêm ca red-team lách chính sách qua giao việc và qua nhóm vào bộ dữ liệu trong `eval/`, cho SC-012.
- [X] T088 [P] Viết test e2e `web/e2e/delegation.spec.ts` cho kịch bản 1 và 3 của quickstart (hai tài khoản, LLM `fake`),
  kèm phép đo độ trễ tin nhóm giữa hai trình duyệt, kỳ vọng dưới 2 giây (SC-008).
- [X] T089 Cập nhật `README.md` (mục "Chạy local" đã sửa ở T027):
  - mục "Kiểm tra": `run_delegation.py`;
  - mục "Trạng thái": feature 003.

  Thêm hướng dẫn demo vào `docs/DEMO.md`.
- [X] T090 Chạy toàn bộ kiểm tra:
  - `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`;
  - cùng bộ test trên Postgres với `TEST_DATABASE_URL`;
  - `cd web && npm test && npm run build`.
- [X] T091 Chạy `.\dev.ps1` hai lần trên database đã có dữ liệu cũ và xác nhận theo quickstart §4. Nếu hạ tầng không có
  sẵn thì ghi rõ là chưa chạy thử (nguyên tắc III).
- [ ] T092 Đi qua 11 kịch bản tay trong `specs/003-agent-group-delegation/quickstart.md` và ghi kết quả.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: chạy được ngay.
- **Foundational (Phase 2)**: cần Phase 1 xong, và **chặn mọi story**. Thứ tự bên trong:
  1. T005 đến T010 (dữ liệu);
  2. T011 đến T015 (hội thoại);
  3. T016 đến T021 (lượt chạy, worker);
  4. T022 đến T025 (duyệt);
  5. T026, T027 (seed, `dev.ps1`);
  6. T028 đến T032 (test và web).
- **US1 (Phase 3)**: cần Phase 2. Đây là MVP.
- **US2 (Phase 4)**: cần US1 (dùng `handoff_targets` và `request_handoff`).
- **US3 (Phase 5)**: cần Phase 2 (lõi duyệt, lượt chạy). Không cần US1, US2, trừ ca "hỏi người từ tầng 2" của T051, ca
  này cần US1.
- **US4 (Phase 6)**: cần Phase 2. Phần giao việc trong nhóm (T062, T066) cần US1 và US2. Phần thẻ câu hỏi trong nhóm cần
  US3.
- **US5 (Phase 7)**: cần Phase 2. T075 cần US3 (`request_person`).
- **US6 (Phase 8)**: cần Phase 2 (lõi) và US3 (để có hành động `send` thật mà thử).
- **US7 (Phase 9)**: cần US1, US3, US4 để có dữ liệu cho nhật ký. Phần lọc quyền riêng tư (T082) làm được ngay sau Phase 2.
- **Polish (Phase 10)**: sau các story muốn giao.

### Thứ tự gợi ý khi làm một mình

```text
Phase 1 → Phase 2 → US1 → US2 → US3 → US6 → US4 → US5 → US7 → Polish
```

### Within Each User Story

Test trước, rồi model và service, rồi endpoint, rồi giao diện. Mỗi story chạy xanh `pytest` trước khi sang story sau.

### Parallel Opportunities

- Phase 1: T002, T003, T004.
- Phase 2: T006 và T007 song song với nhau (khác file với T005); T025 và T028 viết song song với phần còn lại; T029 đến
  T032 (web) song song với backend sau khi chốt contract.
- Mỗi story: các task test có `[P]` song song với nhau; task web có `[P]` song song với backend của cùng story.
- US3 và US1 làm song song được sau Phase 2 (khác package: `people.py` và `handoffs.py`), nhưng cùng sửa
  `tools/registry.py` và `prompts.py`, nên cần ghép thay đổi cẩn thận.

---

## Parallel Example: User Story 1

```bash
# Test viết song song:
Task: "T033 test luồng đầy đủ trong backend/tests/test_handoffs.py"
Task: "T035 test HandoffBar trong web/src/components/chat/HandoffBar.test.tsx"

# Backend và web song song sau T038:
Task: "T039 execute_handoff trong backend/app/orchestration/handoffs.py"
Task: "T043 HandoffBar.tsx trong web/src/components/chat/"
```

## Parallel Example: User Story 4

```bash
Task: "T061 test thành viên và quyền riêng tư nhóm trong backend/tests/test_groups.py"
Task: "T069 HandoffMessage.tsx"
Task: "T070 NewGroupDialog.tsx + GroupSettingsPanel.tsx"
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 và Phase 2: giao diện Messenger cho chat riêng, stream sự kiện, worker, lõi duyệt.
2. Phase 3 (US1): giao việc trong chat riêng, có thanh "Đã hỏi" và lượt làm tiếp.
3. **Dừng lại kiểm tra**: quickstart kịch bản 1, `pytest` xanh, `.\dev.ps1` chạy được.

### Giao dần

1. US2: hàng rào quyền. Nên làm ngay sau MVP, trước khi demo cho người khác.
2. US3 rồi US6: hỏi giáo viên, phụ huynh và duyệt đủ kiểu OpenBot.
3. US4: nhóm chat.
4. US5: học sinh, phụ huynh tạo agent.
5. US7: nhật ký và quyền riêng tư.
6. Polish: bộ eval, e2e, README, `dev.ps1`.

---

## Notes

### Ghi nhận khi triển khai (2026-11-15)

- T092 chưa đánh dấu: 11 kịch bản tay chưa được đi qua đủ bằng tay. Phần lớn đã được phủ tự động: test backend
  (`test_handoffs`, `test_people`, `test_approvals`, `test_groups`, `test_privacy`, `test_events`, `test_agents`),
  `eval/run_delegation.py` (7/7 hàng rào) và e2e `web/e2e/delegation.spec.ts` (3/3 trên stack chạy bằng `dev.ps1`).
- T015: mốc độ trễ không ghi được trước khi đổi runtime. `run_delegation.py --latency` đã ghi mốc đầu tiên sau thay đổi
  (LLM `fake`, trung vị khoảng 49 ms); SC-001 cần đo lại với mô hình thật trên nhánh trước feature để so sánh.
- Khác plan:
  - Kết quả các việc đang chờ được đưa lại cho agent bằng một tin nhắn nền tảng (không phải `tool` message), vì công cụ
    giao việc trả "queued" ngay; agent hỏi vẫn có đúng một lượt viết kết luận.
  - Chat không gửi `conversation_id` vẫn tạo chat riêng "tự chọn agent" (`direct_agent_slug` rỗng) như trước feature, để
    giữ tương thích; hội thoại cũ được chuyển thành loại này.
  - API client gộp trong `web/src/api-client/chat.ts` (không tách `inbox.ts`, `approvals.ts`).
  - Seed `--ensure` chuyển lượt cài agent nền tảng của lớp demo sang phiên bản mới nhất (để có quyền giao việc);
    lớp thật vẫn giữ phiên bản đã cài, giáo viên cài lại để nhận quyền mới.

- `[P]`: khác file, không phụ thuộc task chưa xong.
- Theo hiến pháp, nguyên tắc II: agent **không** tự commit; người dùng tự commit sau mỗi task hoặc nhóm task, commit
  message bằng tiếng Anh.
- Theo nguyên tắc III: T026, T027, T091 là bắt buộc vì feature thêm migration và seed.
- Mọi nội dung hiển thị cho người dùng MUST qua kiểm duyệt đầu ra theo người xem. Khi sửa code hiển thị, kiểm tra không
  có đường tắt nào bỏ qua `review`.

---

## Phase 11: Convergence

- [X] T093 Khi lượt đã sang luồng hỗ trợ an toàn (`ctx.support`), không mời `message_agent` trong `meta.offers()` và bỏ qua `meta.mentions_to_handoffs()` trong `backend/app/orchestration/meta.py`; lời gọi bị ép thì nhận lời từ chối chung và được ghi nhật ký; thêm test trong `backend/tests/test_handoffs.py` per FR-053 (contradicts)
- [X] T094 Trong nhóm, kiểm duyệt đầu ra theo người xem: khi nhóm có học sinh hoặc phụ huynh, câu trả lời của agent (kể cả câu trả lời nguyên văn của giao việc) cho lượt do giáo viên gọi vẫn phải qua `classifier.review_output` theo vai trò và chính sách chặt nhất trong số người xem, hoặc được ẩn với những người xem đó, trong `backend/app/runtime/graph.py` (`review`) và `backend/app/orchestration/handoffs.py` (`complete`); thêm test trong `backend/tests/test_groups.py` per FR-052 (contradicts)
- [X] T095 Chỉ cho thêm vào nhóm các agent đã cài trong lớp (`Installation.scope == "class"`) hoặc agent nền tảng; agent cá nhân, agent tự tạo chưa kiểm định và agent chưa được giáo viên cho vào lớp MUST bị loại khỏi `addable_agents()` và `candidates` trong `backend/app/chat/groups.py`, và thêm vào thì nhận 422; thêm test trong `backend/tests/test_groups.py` per FR-003, US5/AC4 (contradicts)
- [X] T096 Áp cổng đồng ý của phụ huynh cho mọi lượt chạy của học sinh, không chỉ trong lớp: chat ở không gian cá nhân (`run_turn` trong `backend/app/chat/router.py` khi `room is None`), `POST /agents/{id}/try` trong `backend/app/agents/router.py`, cùng lượt làm tiếp và giao việc chạy nền (`backend/app/runtime/run.py`, `backend/app/orchestration/handoffs.py`); thêm test trong `backend/tests/test_agents.py` per FR-005, US5/AC5 (partial)
- [X] T097 Trong `people.answer()` ở `backend/app/orchestration/people.py`, thêm `classifier.review_output` theo vai trò và chính sách của người dùng gốc sau bước kiểm bằng luật; không qua thì lưu `answer_hidden=True` và báo agent "Câu trả lời đã bị ẩn"; thêm test trong `backend/tests/test_people.py` per FR-031 (partial)
- [X] T098 Câu hỏi gửi người phát sinh trong nhóm mà mang nội dung riêng của học sinh (lời xin phép, điểm, tiến độ; mặc định mọi `ask_person` tới người khác do lượt của học sinh tạo) MUST đặt `private_to_recipient=True` và không hiện thẻ trong nhóm, chỉ hiện trong hộp yêu cầu của người nhận và cho người hỏi, trong `backend/app/orchestration/people.py` (`card_visibility`, `open_request`, `answer`); thêm test trong `backend/tests/test_groups.py` per FR-046 (partial)
- [X] T099 Gọi `people.undeliver_for_member_loss` khi gỡ thành viên khỏi lớp (`DELETE /classes/{class_id}/members/{member_id}` trong `backend/app/classes/router.py`), khi bỏ liên kết phụ huynh, và khi khoá tài khoản. Đồng thời đánh `left_at` cho người đó ở các nhóm của lớp, và kiểm người nhận còn hợp lệ trong `people.answer()`. Agent báo người dùng gốc qua lượt làm tiếp. Thêm test trong `backend/tests/test_people.py` per Edge Cases, US3/AC6 (missing)
- [X] T100 Khi phụ huynh rút đồng ý (`set_consent` trong `backend/app/classes/service.py`), huỷ các câu hỏi đang `open` hoặc `draft` của học sinh đó; trong nhóm, học sinh vẫn gửi được tin cho người (lưu và phát tin, không định tuyến tới agent) nếu chính sách lớp cho phép, thay vì bị chặn toàn bộ ở `run_turn` trong `backend/app/chat/router.py`; thêm test per Edge Cases (rút đồng ý) (missing)
- [X] T101 Ghi mỗi quyết định duyệt (cho phép hoặc từ chối do thẻ, do quy tắc nào, do chế độ nào) kèm `rule_id` hoặc chế độ đã quyết: trả `rule_id` trong `Decision` của `backend/app/orchestration/approvals.py`, ghi `GuardEvent(stage="approval")` hoặc một bản ghi tương đương ở `meta.gate_action` và `people.request_person`, và đưa vào `scope_activity` trong `backend/app/orchestration/activity.py` per FR-056 (partial)
- [X] T102 [P] Viết `web/src/features/agents/AgentActivityPage.tsx` (gọi `GET /agents/{id}/activity`, mở từ trang "Agent của tôi"); sửa `web/src/features/audit/AuditLogView.tsx` để hiện các dòng `activity` (giao việc, câu hỏi gửi người, quyết định duyệt kèm lý do chặn), nhãn cho `stage` `handoff`, và `scope_note` "Chỉ gồm các nhóm bạn tham gia"; thêm mục "Hoạt động của tôi" cho học sinh và phụ huynh gọi `GET /me/activity`; thêm route vào `web/src/app/routes.ts` per FR-057, US7 (missing)
- [X] T103 [P] Thêm trang admin "Duyệt hành động" trong khu admin của web (route `/admin/approvals` trong `web/src/app/routes.ts` và `web/src/pages/WorkspacePage.tsx`): chọn chế độ cho từng loại luôn phải hỏi và từng vai trò (`GET/PUT /api/admin/approvals/modes`), quản lý quy tắc admin (`GET/POST/DELETE /api/admin/approvals/rules`), và xem các quyết định đã cho phép, bị từ chối, bị lỗi trên toàn hệ thống (cần thêm một endpoint admin dùng `scope_activity` không kèm nội dung chat riêng) per FR-035, FR-057 (missing)
- [X] T104 Trong `handoffs.claim()` và `handoffs.execute()` ở `backend/app/orchestration/handoffs.py`, khi việc `running` hết lease mà `attempts >= handoff_max_attempts` thì gọi `fail(final=True)` (thành "không nhận được câu trả lời") thay vì chạy lại; thêm test chèn lỗi trong `backend/tests/test_handoffs.py` per FR-016, Edge Cases (partial)
- [ ] T105 Đo mốc thời gian tới chữ đầu tiên với mô hình thật trên commit trước feature 003, ghi vào `eval/results/latency_baseline.json`, rồi chạy `eval/run_delegation.py --latency` trên code hiện tại để so sánh; ghi kết quả vào `eval/README.md` per SC-001 (partial)
