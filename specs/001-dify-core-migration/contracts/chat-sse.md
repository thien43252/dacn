# Hợp đồng: SSE chat giữa backend và web

Endpoint giữ nguyên: `POST /api/chat/stream` (và endpoint sandbox của builder). Request body không đổi
(`message`, `class_id`, `conversation_id`, `agent`). Mỗi sự kiện là một dòng `data: <json>`.

## Thứ tự

```
operation → conversation → [notice redacted] → agent → (text_delta | text_reset | tool)* → [citations] → [suggestions] → done
```

Khi bị chặn: `operation → conversation → notice(guard_blocked) → done(status="blocked")`.
Khi lỗi: `... → error → done(status="error")`.

## Sự kiện giữ nguyên

| `type` | Trường | Ghi chú |
|---|---|---|
| `operation` | `operation_id`, `resume_supported=false` | |
| `conversation` | `conversation_id` | id của nền tảng, không phải của Dify |
| `agent` | `message_id`, `agent`, `name`, `avatar`, `reason` | phát sau triage |
| `notice` | `message_id`, `kind`, `text` | `kind`: `guard_blocked`, `redacted`, `consent_required`, **`context_reset` (mới)** |
| `text_delta` | `message_id`, `generation`, `text_offset` (UTF-16), `delta` | |
| `text_reset` | `message_id`, `generation` | kiểm duyệt đầu ra thay câu trả lời (`message_replace` của Dify) |
| `tool` | `message_id`, `name`, `status` (`start`/`done`/`denied`/`error`) | từ handler MCP |
| `error` | `message_id`, `message` | |
| `done` | `message_id`, `status` (`ok`/`blocked`/`error`/`consent_required`), `agent` | |

## Sự kiện mới

| `type` | Trường | Khi nào |
|---|---|---|
| `citations` | `message_id`, `items: [{document_id, title, location, excerpt}]` | lượt có gọi `class_doc_search` và không bị chặn |
| `suggestions` | `message_id`, `items: string[]` (1–3 câu) | sau câu trả lời `ok`; không phát khi bị chặn hoặc thu hồi |

`chatStream.ts` chuyển tiếp mọi `type` nên không phải sửa; `ChatPanel.tsx` và `MessageBody.tsx` hiển thị hai sự
kiện mới. Lịch sử (`GET /api/chat/conversations/{id}/messages`) trả `meta.citations` và `meta.suggestions` để hiển
thị lại.

## Thay đổi API khác

| API | Thay đổi |
|---|---|
| `GET/PUT /api/classes/{id}/policy` | bỏ trường `blocked_topics` (FR-013) |
| `GET /api/classes/{id}/documents` | `status` phản ánh trạng thái indexing của Dify |
| `POST /mcp` (mới, không thuộc `/api`) | MCP streamable HTTP cho Dify, chỉ nhận `Authorization: Bearer <MCP_TOKEN>`; không dùng cookie |
