# Implementation Plan: Tạo agent, nhóm chat nhiều agent và người, agent hỏi agent và hỏi người

**Branch**: `main` (thư mục spec `003-agent-group-delegation`) | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-agent-group-delegation/spec.md`

## Summary

Feature biến chat một người một agent thành một hệ "Messenger" có ba thành phần:

- **Chat riêng và nhóm:**
  - Mỗi người có chat riêng với từng agent.
  - Người dùng tạo được nhóm gồm cả người lẫn agent của lớp.
  - Chat riêng và nhóm đều riêng tư hoàn toàn.
- **Giao việc giữa agent** theo cơ chế `message_bot` của OpenBot:
  - Quyền giao việc được cấp cho từng agent.
  - Nền tảng, không phải mô hình, quyết định đích, nơi nhận và tầng.
  - Việc chạy bất đồng bộ qua hàng đợi.
  - Câu trả lời được ghi nguyên văn, đúng một lần.
  - Agent hỏi có một lượt làm tiếp để viết kết luận.
- **Hỏi người và duyệt hành động** theo `ask_person` và Approvals của OpenBot:
  - Agent hỏi được chính người dùng, giáo viên đúng môn hoặc phụ huynh.
  - Gửi cho người khác là hành động luôn phải hỏi.
  - Thẻ duyệt có tối đa 4 lựa chọn; chế độ hiện lựa chọn nào do admin đặt theo vai trò.
  - Câu trả lời luôn quay về hội thoại gốc.

Cách làm kỹ thuật:
- Giữ graph LangGraph hiện có cho từng lượt (`screen → classify/select_agent → gate → run_agent → review`).
- Thêm ba công cụ nền tảng do runtime tự xử lý: `message_agent`, `ask_person`, `reply_privately`.
- Lượt chạy dừng chờ thì lưu vào `agent_runs`. Một worker `asyncio` trong tiến trình backend chạy hàng đợi `handoffs` và
  đánh thức các lượt chạy.
- Thêm stream SSE theo hội thoại, có `seq` để phát bù.
- Mở trình tạo agent cho học sinh và phụ huynh.

Chi tiết các quyết định ở [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 7 với React 19.3 (web)

**Primary Dependencies**:
- Backend, đã có: FastAPI, SQLAlchemy 2 async, Alembic, LangGraph, adapter LLM (Anthropic, OpenAI, Gemini, fake), MCP.
- Web, đã có: Vite 8, CSS thuần.
- Không thêm dependency mới.

**Storage**:
- PostgreSQL với pgvector, chạy local cổng 5433.
- Một migration mới `0006_groups_handoffs_approvals` (xem [data-model.md](data-model.md)).
- Test dùng SQLite trong bộ nhớ, và Postgres khi đặt `TEST_DATABASE_URL`.

**Testing**:
- pytest cùng pytest-asyncio và LLM `fake` (script được lời gọi công cụ, `respond_with`).
- `worker.drain()` chạy hàng đợi đồng bộ trong test.
- vitest cho web; Playwright cho e2e (đã có cấu hình).
- Script eval `eval/run_delegation.py`.

**Target Platform**: chạy local trên Windows bằng `dev.ps1`. Backend chạy một tiến trình uvicorn.

**Project Type**: web application (`backend/` cộng `web/`).

**Performance Goals**:
- SC-001: lượt không giao việc chậm thêm tối đa 10%, vì chỉ thêm việc tra quyền trong bộ nhớ và ghi `seq`.
- SC-008: tin nhóm tới các thành viên trong vòng 2 giây khi chạy local.

**Constraints**:
- Không thêm service hay container (nguyên tắc III).
- Worker phải chịu được reload của uvicorn: dùng lease, và quét việc bị dở khi khởi động.
- Một hội thoại chỉ có một lượt chạy `running` cho mỗi agent tại một thời điểm.
- Lượt người khởi tạo trong nhóm được xếp hàng theo thứ tự đến.
- Mọi nội dung phát ra phải qua kiểm duyệt đầu ra theo người xem.

**Scale/Scope**:
- Một trường demo: vài lớp, khoảng 50 người dùng, nhóm tối đa 50 thành viên, tối đa 8 agent mỗi nhóm.
- Giới hạn giao việc mặc định: tầng 2, 6 lần mỗi lượt, thử lại 2 lần.
- Khoảng 12 màn hình hoặc component mới, khoảng 20 endpoint mới hoặc sửa.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Nguyên tắc | Đánh giá | Ghi chú |
|---|---|---|
| I. Tài liệu và spec bằng tiếng Việt | PASS | Mọi file trong `specs/003-…` viết bằng tiếng Việt. Tên định danh, endpoint và khoá cấu hình giữ tiếng Anh. |
| II. Không tự commit | PASS | Plan không có bước commit. Commit message chỉ được đề xuất bằng tiếng Anh. |
| III. `dev.ps1` luôn chạy được bản mới nhất | PASS, có việc phải làm | Feature thêm migration (`dev.ps1` đã chạy `alembic upgrade head`) và thêm seed demo. Hiện seed chỉ chạy khi database mới, nên `tasks.md` MUST có task sửa `dev.ps1` để luôn chạy seed lũy đẳng (`seed_demo --ensure`). Worker chạy trong tiến trình backend nên không thêm cửa sổ hay cổng. Thêm biến cấu hình không bắt buộc (`HANDOFF_MAX_DEPTH`, `HANDOFF_MAX_PER_RUN`, `HANDOFF_MAX_ATTEMPTS`, `PERSON_REQUEST_HOURS`, `APPROVAL_CARD_HOURS`) vào `.env.example`, có giá trị mặc định nên không phá `.env` cũ. Mục "Chạy local" và "Kiểm tra" trong README được cập nhật cùng lúc. |
| Governance: ghi ngoại lệ | Không có ngoại lệ | |

**Re-check sau Phase 1**: PASS. Thiết kế không thêm service, cổng hay bước thủ công nào ngoài seed lũy đẳng đã nêu.

## Project Structure

### Documentation (this feature)

```text
specs/003-agent-group-delegation/
├── spec.md
├── plan.md              # File này
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── platform-tools.md        # message_agent, ask_person, reply_privately
│   ├── conversation-events.md   # SSE theo hội thoại
│   └── rest-api.md              # Hội thoại, nhóm, hộp yêu cầu, duyệt, agent, nhật ký
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── agents/
│   │   ├── manifest.py        # + handoff_to
│   │   ├── router.py          # Teacher → Maker; handoff-candidates; agent-requests; activity
│   │   └── service.py         # effective_grants(); available_agents giữ nguyên quy tắc
│   ├── chat/
│   │   ├── models.py          # Conversation (+kind, direct_agent_slug…), ConversationMember, ChatMessage (+seq…)
│   │   ├── router.py          # Danh sách Messenger, direct, stream (lượt người khởi tạo)
│   │   ├── groups.py          # MỚI: tạo/sửa nhóm, thành viên, candidates
│   │   ├── events.py          # MỚI: bus trong bộ nhớ + SSE /events?after=
│   │   └── visibility.py      # MỚI: quyền xem tin/hội thoại (FR-047, FR-050)
│   ├── orchestration/         # MỚI
│   │   ├── models.py          # AgentRun, Handoff, PersonRequest, ApprovalCard, ApprovalRule, ApprovalKindMode, UserSettings
│   │   ├── handoffs.py        # validate/enqueue/execute handoff, ghi câu trả lời nguyên văn một lần
│   │   ├── people.py          # allowed_recipients, tạo/trả lời/hết hạn câu hỏi, inbox
│   │   ├── approvals.py       # decide() thuần + thẻ duyệt + quy tắc
│   │   ├── runs.py            # lưu/dựng lại lượt chạy, resume (lượt làm tiếp)
│   │   ├── worker.py          # vòng asyncio: handoffs, runs resumable, hết hạn; drain() cho test
│   │   └── router.py          # /inbox, /person-requests, /approvals, /settings/approvals, /admin/approvals
│   ├── runtime/
│   │   ├── graph.py           # run_agent: meta tools, dừng chờ, chế độ group; review theo người xem
│   │   ├── router.py          # + route_group (lựa chọn "none")
│   │   └── prompts.py         # + hướng dẫn giao việc/hỏi người/trả lời riêng, danh sách agent đích
│   ├── tools/registry.py      # PlatformTool + meta, action_kind, personal_data, group_only; 3 meta tools
│   ├── classes/models.py      # DEFAULT_POLICY + khoá mới; ClassMember.subject
│   ├── audit/                 # lọc theo thành viên, private_space, sự kiện mới
│   └── main.py                # lifespan: khởi động/dừng worker, quét việc dở
├── migrations/versions/0006_groups_handoffs_approvals.py
├── scripts/seed_demo.py       # + tài khoản mới, môn GV, nhóm demo; --ensure lũy đẳng
└── tests/
    ├── test_handoffs.py       # quyền, từ chối giống nhau, tầng, vòng lặp, giới hạn, thử lại, một lần, làm tiếp
    ├── test_people.py         # người nhận hợp lệ, inbox, trả lời một lần, về đúng hội thoại gốc, hết hạn
    ├── test_approvals.py      # bảng chân trị decide(), 4 lựa chọn, chế độ theo vai trò, thẻ ở hội thoại gốc
    ├── test_groups.py         # thành viên, quy tắc thêm của học sinh, định tuyến, tin riêng, reply_privately
    ├── test_privacy.py        # chat riêng/nhóm riêng tư, nhật ký giáo viên, không cảnh báo
    ├── test_events.py         # seq, phát bù, lọc người xem, không trùng
    └── test_agents.py         # (sửa) học sinh/phụ huynh tạo agent, lọc công cụ, handoff_to

web/src/
├── features/chat/             # MỚI
│   ├── ChatHomePage.tsx       # Messenger 2 cột
│   ├── ConversationList.tsx
│   ├── NewGroupDialog.tsx
│   ├── GroupSettingsPanel.tsx
│   └── useConversationEvents.ts
├── components/chat/
│   ├── ChatThread.tsx         # (sửa) người gửi nhiều loại, tin hệ thống, thứ tự theo seq
│   ├── HandoffBar.tsx         # MỚI: "▸ Đã hỏi …" mở/đóng, lồng nhau
│   ├── HandoffMessage.tsx     # MỚI: tin riêng trong nhóm "trả lời cho …"
│   ├── ApprovalCard.tsx       # MỚI
│   └── PersonRequestCard.tsx  # MỚI
├── features/inbox/InboxPage.tsx        # MỚI: hộp yêu cầu + huy hiệu
├── features/settings/ApprovalSettings.tsx  # MỚI
├── features/agents/BuilderPage.tsx     # (sửa) mở cho mọi vai trò, chọn handoff_to
├── features/agents/ClassAgentsTab.tsx  # (sửa) thu hẹp handoff_allow
├── features/agents/AgentActivityPage.tsx # MỚI
├── api-client/{chat,inbox,approvals}.ts, types.ts, chatStream.ts  # (sửa/mới)
└── app/router.ts              # /{role}/chat, /{role}/inbox, /{role}/settings/approvals

seed/agents/*.yaml             # + handoff_to cho agent mẫu
eval/delegation_scenarios.yaml, eval/run_delegation.py   # MỚI
dev.ps1, README.md, .env.example                          # (sửa, nguyên tắc III)
```

**Structure Decision**:
- Giữ cấu trúc web application hiện có (`backend/app/<domain>`, `web/src/features/<domain>`).
- Thêm package `backend/app/orchestration/` cho phần điều phối có trạng thái (lượt chạy, giao việc, hỏi người, duyệt),
  để `runtime/graph.py` chỉ lo một lượt chạy và `chat/` chỉ lo hội thoại cùng hiển thị.

## Thiết kế luồng chính

### Lượt chat riêng có giao việc (story 1)

```text
POST /chat/stream ─▶ screen ─▶ classify ∥ select_agent(direct: agent cố định) ─▶ gate ─▶ run_agent
  run_agent: mô hình gọi message_agent(B), message_agent(C)
    ─▶ validate (quyền ∩ available ∩ chain ∩ giới hạn) ─▶ handoffs B, C = queued; tool result "queued"
    ─▶ mô hình viết câu báo "đang hỏi B và C" ─▶ review ─▶ lưu tin A + AgentRun(waiting, transcript)
worker: lấy handoff B ─▶ dựng RunContext(user gốc, depth+1, chain+[A]) ─▶ graph cho B (luồng nháp, không stream)
    ─▶ review theo người dùng gốc ─▶ ghi chat_messages(handoff_id=B, nguyên văn) đúng một lần ─▶ events: handoff_answer
worker: khi B, C đều xong ─▶ run A resumable ─▶ resume: thêm tool messages ─▶ vòng công cụ ─▶ review
    ─▶ tin kết luận mới của A ─▶ events: message
```

### Hỏi người và duyệt (story 3, story 6)

```text
mô hình gọi ask_person(teacher, toan, …) ─▶ ẩn thông tin cá nhân và kiểm duyệt nội dung
  ─▶ decide(send) = ask ─▶ ApprovalCard trong hội thoại gốc ─▶ AgentRun waiting
người dùng bấm "Cho phép lần này" ─▶ tạo PersonRequest(open), đúng một lần ─▶ inbox người nhận
người nhận trả lời ─▶ UPDATE … WHERE status='open' ─▶ ghi tin vào hội thoại gốc ─▶ run resumable ─▶ lượt làm tiếp
```

### Nhóm (story 4)

```text
tin của người ─▶ lưu và phát `message` cho thành viên ─▶ route_group: @agent | none | llm | default
  ─▶ agent chạy theo vai trò và chính sách của người gửi; ngữ cảnh là tin người gửi được xem
  ─▶ agent gọi @Tên hoặc message_agent ─▶ handoff ─▶ câu trả lời thành tin riêng (reply_to_agent=A)
  ─▶ câu hỏi về dữ liệu riêng ─▶ reply_privately ─▶ chat riêng giữa người gửi và agent
```

## Thứ tự triển khai đề xuất

Mỗi bước đi theo một user story để có thể demo độc lập.

1. **Nền dữ liệu và hội thoại kiểu Messenger:**
   - Migration 0006.
   - Chuyển hội thoại cũ thành `direct`.
   - Danh sách hội thoại, `seq`, stream events.
   - Giao diện ChatHome.

   Phần này phục vụ FR-048, FR-049 và là nền cho mọi story.
2. **Story 2 và 1, giao việc:**
   - `handoff_to`, `effective_grants`, `message_agent`, `handoffs`, worker, `agent_runs`, lượt làm tiếp.
   - `HandoffBar`.
3. **Story 6 và 3, duyệt và hỏi người:**
   - `decide()`, thẻ duyệt, `ask_person`, `person_requests`, hộp yêu cầu.
   - Trả lời quay về hội thoại gốc.
4. **Story 4, nhóm:**
   - Tạo nhóm, thành viên, quy tắc thêm thành viên của học sinh.
   - `route_group`, tin riêng có nhãn, `reply_privately`.
5. **Story 5, tạo agent cho mọi vai trò:**
   - `Maker`, lọc công cụ theo vai trò, xin đưa agent vào lớp.
6. **Story 7 và quyền riêng tư:**
   - Nhật ký lọc theo thành viên, `private_space`, trang hoạt động agent.
7. **Đánh giá và vận hành:**
   - `eval/run_delegation.py`.
   - `dev.ps1` có seed `--ensure`; cập nhật README và `.env.example`.

## Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| Worker và lượt chạy làm tiếp đụng nhau, tạo câu trả lời trùng | Ràng buộc duy nhất (`handoff_id`, `run_id`+`tool_call_id`), cập nhật có điều kiện trạng thái, test chèn lỗi (SC-005). |
| Reload uvicorn giết worker giữa chừng | Dùng lease cùng quét khi khởi động; việc `running` hết lease thì quay lại `queued`. |
| Ngữ cảnh nhóm dài làm chậm và đắt | Giới hạn `HISTORY_MESSAGES`. Agent chỉ thấy tin người gọi được xem. Ghi usage theo agent và theo bước. |
| Lách chính sách qua giao việc (nhờ agent khác làm hộ bài) | Agent được hỏi chạy theo vai trò và chính sách của người dùng gốc. Câu trả lời nguyên văn vẫn qua `review`. Thêm ca red-team (SC-012). |
| Quyền riêng tư làm mất cảnh báo an toàn cho giáo viên | Đây là quyết định đã chốt khi làm rõ spec và được ghi trong Assumptions. Sự kiện vẫn được ghi cho admin, không kèm nội dung. |

## Complexity Tracking

Không có vi phạm hiến pháp cần biện minh.
