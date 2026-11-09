# Hợp đồng: SSE chat và API liên quan (bổ sung cho feature 001)

Nền: [specs/001-dify-core-migration/contracts/chat-sse.md](../../001-dify-core-migration/contracts/chat-sse.md).
Mọi sự kiện cũ giữ nguyên ý nghĩa. Web bỏ qua `type` lạ nên backend mới chạy được với web cũ (chỉ thiếu khung tiến
trình và thẻ câu hỏi).

## Request `POST /api/chat/stream`

`ChatIn` thêm một trường không bắt buộc:

```json
{
  "message": "Em học lớp mấy?\n7\n\nÔn chương nào?\nChương 2",
  "class_id": "…", "conversation_id": "…", "agent": null,
  "reply": {
    "run_id": "…",
    "answers": {"q1": "7", "q2": "Chương 2"},
    "skip_all": false,
    "decision": null
  }
}
```

| Trường của `reply` | Kiểu | Ghi chú |
|---|---|---|
| `run_id` | string | run đang `awaiting_user` của chính hội thoại này; sai hoặc không còn chờ → bỏ qua `reply`, xử lý như tin nhắn thường và phát `notice(pending_expired)` nếu run đã hết hạn |
| `answers` | object `{qid: string ≤ 500}` | cho `kind="clarify"`; câu không trả lời thì bỏ khỏi object |
| `skip_all` | bool | "Cứ làm luôn" |
| `decision` | `approve` \| `reject` \| null | cho `kind="confirm"` |

`message` vẫn bắt buộc: web ghép "câu hỏi\ncâu trả lời" (hoặc "Cứ làm luôn" / "Đồng ý" / "Không") để lưu và để đi
qua ẩn thông tin cá nhân và triage như mọi tin nhắn (FR-037). Backend dùng `answers` sau khi đã ẩn thông tin cá nhân
từng giá trị.

## Thứ tự sự kiện

Đường nhanh: không đổi so với 001.

Đường đầy đủ, chạy hết một mạch:

```
operation → conversation → [notice redacted] → step(analyze, running) → plan
  → (step(sN, running|done|error|blocked|skipped) | tool{step_key})*
  → step(synthesis, running) → agent(lead) → (text_delta | text_reset | tool)* → [citations] → [suggestions]
  → done(ok|blocked|error)
```

Dừng để hỏi (sau `plan` hoặc sau một số phần việc):

```
… → ask → done(status="awaiting_user")
```

Làm tiếp (request có `reply` hợp lệ):

```
operation → conversation → [notice redacted] → plan(resumed=true, steps kèm trạng thái đã có) → step … → … → done
```

Bị chặn ở triage khi đang chờ: `… → notice(guard_blocked) → done(blocked)` và run chuyển `cancelled`.

## Sự kiện mới

| `type` | Trường | Ghi chú |
|---|---|---|
| `plan` | `message_id`, `run_id`, `goal`, `lead: {slug, name, avatar}`, `steps: [{key, title, agent: {slug, name, avatar}, depends_on, status}]`, `resumed` | phát mỗi khi kế hoạch được tạo, tiếp tục hoặc lập lại; client thay toàn bộ danh sách |
| `step` | `message_id`, `key`, `status`, `title?`, `agent?`, `duration_ms?` | `key` đặc biệt: `analyze`, `synthesis`; `status`: `pending` · `running` · `done` · `error` · `blocked` · `skipped` |
| `ask` | `message_id` (id tin nhắn câu hỏi), `run_id`, `kind` (`clarify` · `confirm`), `agent: {slug, name, avatar}`, `intro`, `questions?: [{id, question, options: string[]}]`, `confirm?: {tool, summary, impact, audience_count, preview: {title?, body?, items?, before?, after?}}`, `skippable` | luôn đi ngay trước `done(awaiting_user)` |

## Sự kiện cũ thay đổi

| `type` | Thay đổi |
|---|---|
| `tool` | thêm `step_key` (null ở đường nhanh và bước tổng hợp); client gắn tool vào phần việc tương ứng trong khung tiến trình |
| `notice` | `kind` mới: `pending_expired` ("Câu hỏi trước đã hết hạn, mình xử lý tin nhắn này như yêu cầu mới."), `pending_cancelled` (khi tin nhắn mới thay câu hỏi đang chờ) |
| `done` | `status` thêm `awaiting_user`; thêm `path` (`fast` · `full`) và `contributors` (`[{slug, name, avatar}]`, chỉ ở đường đầy đủ) |

## Lịch sử `GET /api/chat/conversations/{id}/messages`

`MessageOut` không đổi cột; `meta` có thêm các khóa ở [data-model.md](../data-model.md) (`path`, `run_id`,
`contributors`, `process`, `assumptions`, `ask`). Khung tiến trình dựng lại từ `meta.process`; thẻ câu hỏi dựng từ
`meta.ask` và chỉ bấm được khi `ask.state == "open"` và đó là tin nhắn câu hỏi mới nhất.

## API mới: ghi chú làm việc

`GET /api/chat/messages/{message_id}/steps/{step_key}/note`

- Quyền: chủ hội thoại chứa `message_id` (mọi vai trò). Người khác → 404.
- `message_id` là tin nhắn kết quả cuối (có `meta.run_id`).
- Response 200:

```json
{"key": "s1", "title": "Tìm lý thuyết trong tài liệu lớp", "agent": "on-tap-tai-lieu",
 "status": "done", "visibility": "visible", "note": "…", "citations": [ … ]}
```

`visibility`: `visible` (có `note`), `hidden` (`note` = null, kèm `reason_text` "Nội dung này đã được ẩn"),
`unavailable` (phần việc lỗi hoặc bị bỏ qua). Lần gọi đầu có thể chạy review (≤ `DIFY_TIMEOUT_S`); các lần sau trả
kết quả đã lưu. Review lỗi → `hidden`, không lưu (research R9).

## API thay đổi: chính sách lớp

`GET/PUT /api/classes/{id}/policy` thêm `multi_step: bool` (mặc định `true`). Chỉ giáo viên của lớp được sửa, như các
trường khác.

## Health

`GET /api/health` thêm `orchestrator: "on" | "off"` (off khi thiếu `DIFY_PLANNER_KEY`).
