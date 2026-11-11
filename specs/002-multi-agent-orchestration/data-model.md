# Data Model: Xử lý yêu cầu nhiều bước với nhiều agent phối hợp

Phase 1 của [plan.md](plan.md). Migration mới: `backend/migrations/versions/0008_orchestration.py`. Quyết định
nền ở [research.md](research.md).

## Bảng mới

### `turn_runs` — Lượt xử lý

Một lượt đi đường đầy đủ. Đường nhanh không tạo dòng nào; chỉ ghi `path="fast"` vào `chat_messages.meta` và
`usage_ledger.path`. Ngoại lệ: agent ở đường nhanh gọi tool cần xác nhận. Khi đó backend tạo một run (`path` đầy đủ,
không có phần việc) để dừng xin xác nhận (research R6).

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | String(36) | PK | |
| `conversation_id` | String(36) | FK `conversations.id` ON DELETE CASCADE, index | |
| `user_id` | String(36) | FK `users.id` ON DELETE CASCADE | |
| `class_id` | String(36) | FK `classes.id` ON DELETE SET NULL, nullable | null ở không gian cá nhân |
| `status` | String(16) | | `running` · `awaiting_user` · `done` · `error` · `cancelled` · `expired` |
| `request_message_id` | String(36) | | tin nhắn người dùng mở đầu run |
| `reply_message_id` | String(36) | nullable | kết quả cuối (tin nhắn trợ lý) |
| `lead_agent` | String(48) | nullable | slug agent chính |
| `goal` | Text | default "" | |
| `request_text` | Text | | yêu cầu gốc đã ẩn thông tin cá nhân; dùng khi làm tiếp |
| `plan` | JSON | default `{}` | kế hoạch hiện tại đã kiểm tra (định dạng ở contracts/dify-apps.md §2) |
| `plan_version` | Integer | default 1 | tăng khi lập lại kế hoạch |
| `pending` | JSON | nullable | yêu cầu chờ người dùng (bên dưới); null khi không chờ |
| `clarify_rounds` | Integer | default 0 | ≤ `ORCH_MAX_CLARIFY_ROUNDS` (FR-008) |
| `replans` | Integer | default 0 | ≤ `ORCH_MAX_REPLANS` (FR-025) |
| `assumptions` | JSON | default `[]` | giả định được ghi khi bỏ qua hỏi lại hoặc hết lần hỏi |
| `resume_answers` | JSON | default `[]` | `[{question, answer}]` đã nhận, đưa vào tổng hợp và vào `query` |
| `confirmations` | JSON | default `[]` | `[{tool, args, summary, decision, result}]` |
| `interactive` | Boolean | default true | false ở chế độ không có người thật (FR-041) |
| `expires_at` | DateTime(tz) | nullable | đặt khi chuyển sang `awaiting_user` |
| `created_at`, `updated_at` | DateTime(tz) | | |

Index: unique một phần trên `conversation_id` với điều kiện `status IN ('running','awaiting_user')`
(`postgresql_where` và `sqlite_where`) — mỗi hội thoại tối đa một run đang mở (R7).

**`pending`** (JSON):

```json
{
  "kind": "clarify | confirm",
  "ask_message_id": "<chat_messages.id của câu hỏi>",
  "step_key": "s2 | null",
  "questions": [{"id": "q1", "question": "Em học lớp mấy?", "options": ["6", "7", "8", "9"]}],
  "confirm": {"tool": "confirm_probe", "agent": "tro-ly-lop", "args": {...}, "summary": "…", "impact": "…", "source": "tool | interpretation"}
}
```

`questions` chỉ có khi `kind="clarify"` (1–`ORCH_MAX_QUESTIONS` câu, mỗi câu tối đa 6 lựa chọn, lựa chọn ≤ 60 ký tự);
`confirm` chỉ có khi `kind="confirm"`. `source="interpretation"` là xác nhận cách hiểu của agent (tính như hỏi lại,
FR-017); `source="tool"` là xác nhận hành động (không tính, FR-016).

#### Chuyển trạng thái

```
            ┌──────────── kế hoạch có missing/confirm, hoặc tín hiệu ask_user / request_confirmation / tool cần xác nhận
            ▼
running ──▶ awaiting_user ──(trả lời qua thẻ; hoặc gõ tự do và planner xác nhận là trả lời)──▶ running
   │             │──(gõ yêu cầu khác; từ chối xác nhận rồi không còn gì làm; giáo viên tắt multi_step;
   │             │   tin nhắn trả lời bị chặn; consent bị rút)─────────────────────────────▶ cancelled
   │             └──(tin nhắn tới sau expires_at)──────────────────────────────────────────▶ expired
   ├──(tổng hợp xong, kể cả kết quả bị review chặn)──────────────────────────────────────────▶ done
   ├──(mọi phần việc lỗi; bước tổng hợp lỗi trước khi có chữ)────────────────────────────────▶ error
   └──(client ngắt kết nối)──────────────────────────────────────────────────────────────────▶ cancelled
```

Quy tắc:
- Vào `awaiting_user` chỉ khi `interactive=true`; với hỏi lại còn cần `clarify_rounds < ORCH_MAX_CLARIFY_ROUNDS`
  (khi vào, `clarify_rounds += 1`). Xác nhận hành động (`source="tool"`) không xét giới hạn này.
- Khi rời `awaiting_user` theo bất kỳ hướng nào: `pending = null`, `expires_at = null`, và cập nhật
  `chat_messages.meta.ask.state` của tin nhắn câu hỏi.
- `done`, `error`, `cancelled`, `expired` là trạng thái cuối.

### `run_steps` — Phần việc

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | String(36) | PK | |
| `run_id` | String(36) | FK `turn_runs.id` ON DELETE CASCADE, index | |
| `key` | String(16) | unique (`run_id`, `key`) | `s1`…; phần việc thêm từ `request_help` có dạng `h1`… |
| `agent_slug` | String(48) | | phải thuộc danh sách agent dùng được (FR-039) |
| `agent_version_id` | String(36) | nullable | |
| `title` | String(80) | | tiêu đề hiển thị, đã lọc từ khóa (R9) |
| `task` | Text | | mô tả phần việc gửi cho agent |
| `depends_on` | JSON | default `[]` | danh sách `key`; đồ thị không vòng |
| `origin` | String(16) | | `plan` · `help` (từ `request_help`) · `rerun` (chạy lại sau khi có trợ giúp) |
| `requested_by` | String(16) | nullable | `key` phần việc đã gọi `request_help` |
| `status` | String(16) | | `pending` · `running` · `done` · `error` · `blocked` · `skipped` |
| `note` | Text | default "" | ghi chú làm việc (≤ 6000 ký tự) |
| `note_review` | String(12) | default `unreviewed` | `unreviewed` · `visible` · `hidden` (R9) |
| `signals` | JSON | default `[]` | tín hiệu agent đã báo (R5) |
| `citations` | JSON | default `[]` | như `meta.citations` |
| `tools` | JSON | default `[]` | `[{name, status}]` |
| `error` | String(300) | nullable | |
| `started_at`, `finished_at` | DateTime(tz) | nullable | |

Quy tắc:
- Số dòng mỗi run ≤ `ORCH_MAX_STEPS`; số `agent_slug` khác nhau (cộng `lead_agent`) ≤ `ORCH_MAX_AGENTS`.
- Phần việc `origin="help"` không được tạo thêm phần việc (độ sâu 1, FR-024).
- Phụ thuộc vào phần việc `error`/`blocked`/`skipped` thì vẫn chạy, với ghi chú "phần X không có kết quả" (FR-026).
- `skipped`: không chạy vì hết giới hạn hoặc hết `ORCH_DEADLINE_S`.

## Bảng hiện có thay đổi

### `chat_messages`

- `status` thêm giá trị `awaiting_user` (tin nhắn câu hỏi hoặc xác nhận). Không đổi kiểu cột.
- `meta` của tin nhắn trợ lý thêm:

| Khóa | Khi nào | Nội dung |
|---|---|---|
| `path` | mọi tin nhắn trợ lý | `fast` · `full` |
| `run_id` | đường đầy đủ | id `turn_runs` |
| `contributors` | kết quả cuối đường đầy đủ | `[{slug, name, avatar}]` các agent có phần việc `done` (trừ agent chính) |
| `process` | kết quả cuối đường đầy đủ | `{duration_ms, agents: n, steps: [{key, title, agent, status}]}` |
| `assumptions` | khi có | `string[]` |
| `ask` | tin nhắn `awaiting_user` | `{run_id, kind, questions?, confirm?, state, answers?}`; `state`: `open` · `answered` · `skipped` · `approved` · `rejected` · `expired` · `cancelled` |

- `meta` của tin nhắn người dùng trả lời thêm `reply_to: {run_id, ask_message_id}`.

### `usage_ledger`

- Thêm cột `path` String(8), nullable (`fast` · `full`).
- Giá trị `purpose` mới: `planner`, `step`, `synthesis`, `note_review` (cột đã là String(24)).

### `guard_events`

- Giá trị `stage` mới: `step` (kiểm duyệt của runner thay ghi chú của phần việc) và `step_note` (review ghi chú khi
  hiển thị). `agent_slug` là agent của phần việc (FR-043). Không đổi kiểu cột.

### `tool_calls`

- Không đổi cột. Lần chạy tool sau khi người dùng xác nhận ghi `arguments` đúng như đã trình bày; lần agent gọi tool
  cần xác nhận mà chưa có xác nhận ghi `denied_reason="awaiting_confirmation"`.

### `classes.policy` (JSON)

- Thêm khóa `multi_step: bool`, mặc định `true` (FR-046). `PolicyModel` thêm trường tương ứng; lớp cũ không có khóa
  được hiểu là `true`.

## Cấu trúc trong bộ nhớ (không lưu DB)

### `ToolContext` (app/tools/registry.py)

Thêm: `step_key: str | None`, `mode: "fast" | "step" | "synthesis"`, `signals: list[dict]`, `may_request_help: bool`.

Khi chạy tool sau xác nhận, backend dựng một `ToolContext` mới thay vì dùng lại handle đã hết hạn (research R18,
"Dựng lại ngữ cảnh lúc chạy").

### `PlatformTool`

Thêm: `requires_confirmation: bool = False`, `signal: bool = False`, `confirm_template: str = ""` (mô tả tác động,
điền tham số; không do LLM viết), `preview: Callable | None` (dựng phần xem trước của FR-048), `share_review: bool`
(nội dung học sinh sẽ đọc → chạy thêm `eduagent-review` trước khi xin xác nhận, FR-049).

`pending.confirm` (của `turn_runs`) thêm `preview: {title?, body?, items?, before?, after?}` và `audience_count`.
`confirmations[]` thêm `executed_at` và `result_ref` (id tài liệu, installation, thông báo hoặc bài luyện đã tạo).

## Bảng mới cho tool cần xác nhận (R18)

### `class_announcements` — Thông báo lớp

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | String(36) | PK | |
| `class_id` | String(36) | FK `classes.id` ON DELETE CASCADE, index | |
| `author_id` | String(36) | FK `users.id` ON DELETE SET NULL, nullable | giáo viên đăng |
| `title` | String(120) | | |
| `body` | Text | ≤ 2000 ký tự | Markdown đơn giản |
| `audience` | String(16) | | `students` · `parents` · `all` |
| `source` | String(16) | | `agent` (qua tool) · `ui` |
| `run_id` | String(36) | nullable | lượt xử lý đã tạo, nếu qua tool |
| `created_at` | DateTime(tz) | index | |

Ai được xem: giáo viên của lớp (tất cả); học sinh trong lớp (`students`, `all`); phụ huynh có con trong lớp
(`parents`, `all`). Xoá: giáo viên của lớp.

### `assignments` — Bài luyện được giao

| Cột | Kiểu | Ràng buộc | Ghi chú |
|---|---|---|---|
| `id` | String(36) | PK | |
| `class_id` | String(36) | FK `classes.id` ON DELETE CASCADE, index | |
| `author_id` | String(36) | FK `users.id` ON DELETE SET NULL, nullable | |
| `title` | String(120) | | |
| `instructions` | Text | ≤ 1000 ký tự, default "" | |
| `questions` | JSON | 1–20 phần tử | `[{question ≤ 500, options?: string[] ≤ 6}]` |
| `answer_key` | JSON | nullable | `[{index, answer, explanation?}]`; **chỉ giáo viên thấy** |
| `due_at` | DateTime(tz) | nullable | |
| `source` | String(16) | | `agent` · `ui` |
| `run_id` | String(36) | nullable | |
| `created_at` | DateTime(tz) | index | |

Ai được xem: giáo viên của lớp (kèm `answer_key`); học sinh trong lớp (không có `answer_key`). Phụ huynh xem được
danh sách bài của con (không có `answer_key`). Xoá: giáo viên của lớp. Chưa có bài nộp và chấm điểm (ngoài phạm vi).

## Liên hệ giữa các thực thể

```
conversations 1 ──── * chat_messages
      │                     ▲ request_message_id / reply_message_id / pending.ask_message_id
      └── 1 ──── * turn_runs (≤ 1 đang mở) 1 ──── * run_steps
                      │ confirmations[].result_ref
                      ▼
classes 1 ──── * class_announcements, * assignments, * documents, * installations, policy.notes_for_agents
usage_ledger.path, guard_events.agent_slug ── phân tích theo đường xử lý và theo agent của phần việc
```
