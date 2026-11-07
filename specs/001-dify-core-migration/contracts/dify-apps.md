# Hợp đồng: các ứng dụng Dify

Backend gọi Dify qua Service API (`{DIFY_BASE_URL}/v1`) với khóa của từng ứng dụng. Tên sự kiện và trường cụ thể
phải được kiểm chứng ở spike (research R12) và ghi lại thành fixture trong `backend/tests/fixtures/dify/`.

## 1. `eduagent-triage` (Workflow, blocking)

`POST /v1/workflows/run`, `response_mode="blocking"`, `user=<users.id>`.

### Inputs

| Biến | Kiểu | Bắt buộc | Nội dung |
|---|---|---|---|
| `query` | paragraph | có | Tin nhắn đã ẩn thông tin cá nhân |
| `role` | select (`teacher`, `student`, `parent`) | có | Vai trò của người gửi |
| `roster` | paragraph (JSON) | có | `[{slug, name, description, capabilities, subjects}]`, chỉ gồm agent được phép |
| `requested_agent` | text | không | Agent chọn trên giao diện |
| `previous_agent` | text | không | Agent trả lời lượt trước trong hội thoại |

### Luồng trong workflow

```
Start ─┬─▶ Question Classifier "an toàn" ─────────────▶ ┐
       └─▶ Code (requested / @mention) ─▶ IF có agent?  │
                 ├─ có ─────────────────────────────▶   ├─▶ Code (gộp + kiểm tra slug) ─▶ End
                 └─ không ─▶ LLM router (JSON) ─────▶   ┘
```

### Outputs

| Biến | Kiểu | Giá trị |
|---|---|---|
| `verdict` | string | `allow` \| `block` \| `support` |
| `category` | string | `safe`, `self_harm_risk`, `self_harm_method`, `jailbreak`, `dangerous`, `age_inappropriate` |
| `reason` | string | Lý do ngắn bằng tiếng Việt |
| `agent` | string | Slug thuộc `roster` (mặc định `tro-ly-lop`) |
| `route_reason` | string | `ui`, `mention`, `router: <lý do>` hoặc `fallback` |

Ánh xạ: `safe` → `allow`; `self_harm_risk` → `support`; các nhãn còn lại → `block`. Token lấy từ
`data.total_tokens` → `usage_ledger.purpose="triage"`.

### Lỗi

Triage lỗi hoặc quá `DIFY_TIMEOUT_S`: lượt kết thúc `status="error"`, không gọi runner. Hệ thống không cho tin nhắn
qua khi chưa kiểm duyệt (fail closed).

## 2. `eduagent-runner` (Chatflow, streaming)

`POST /v1/chat-messages`, `response_mode="streaming"`, `user=<users.id>`,
`conversation_id=<conversations.dify_conversation_id hoặc "">`, `query=<tin nhắn đã ẩn>`.

### Inputs

| Biến | Kiểu | Nội dung |
|---|---|---|
| `system_prompt` | paragraph (≤ 12000) | Quy tắc nền tảng + vai trò agent + bối cảnh lớp, do `build_system_prompt()` dựng |
| `ctx` | text | Turn handle; tham số Fixed Value của mọi tool MCP, mô hình không thấy |
| `safety_note` | select (`true`/`false`) | `true` khi triage trả `support` |

### Cấu hình ứng dụng

- Agent node: chiến lược Function Calling, tối đa 5 vòng, memory 12 tin nhắn, model bằng `LLM_MAIN_MODEL`.
- MCP provider `eduagent-tools` → `MCP_PUBLIC_URL`, header `Authorization: Bearer <MCP_TOKEN>`; bật 5 tool.
- Kiểm duyệt nội dung: đầu vào và đầu ra, loại keywords (từ `moderation-keywords.txt`) và OpenAI Moderation nếu có
  khóa. Câu trả lời cài sẵn cho đầu vào và đầu ra lấy từ `infra/dify/preset-responses.json`.
- Suggested questions after answer: bật.
- Lời chào mở đầu, đánh giá thích/không thích, upload file, giọng nói: tắt (ngoài phạm vi).

### Sự kiện stream backend xử lý

Xem bảng ánh xạ trong [research.md](../research.md) mục R9. Backend lưu `task_id` từ sự kiện đầu tiên để gọi
`POST /v1/chat-messages/{task_id}/stop` khi người dùng dừng.

### API phụ

| API | Dùng khi |
|---|---|
| `GET /v1/messages/{message_id}/suggested?user=` | sau `message_end`, nếu lượt không bị chặn |
| `POST /v1/chat-messages/{task_id}/stop` | người dùng bấm dừng hoặc ngắt kết nối SSE |

## 3. `eduagent-runner-raw` (Chatflow, streaming)

Giống hệt `eduagent-runner` nhưng tắt kiểm duyệt nội dung. Chỉ pipeline kiểm định và `eval/run_certify.py` dùng.
Backend MUST NOT dùng khóa này cho chat của người dùng.

## 4. Knowledge API (khóa `DIFY_DATASET_KEY`)

| Thao tác của nền tảng | API Dify |
|---|---|
| Lớp có tài liệu đầu tiên | `POST /v1/datasets` (tên `class-<class_id bỏ dấu gạch>`: Dify giới hạn 40 ký tự) |
| Tải lên tài liệu | `POST /v1/datasets/{id}/document/create-by-file` |
| Xem trạng thái | `GET /v1/datasets/{id}/documents/{batch}/indexing-status` |
| Xử lý lại | xóa tài liệu cũ rồi tạo lại từ file đã lưu |
| Xóa tài liệu | `DELETE /v1/datasets/{id}/documents/{document_id}` |
| Xóa lớp | `DELETE /v1/datasets/{id}` |
| `class_doc_search`, `quiz_generator` | `POST /v1/datasets/{id}/retrieve` với `id` lấy từ turn handle |

## 5. `eduagent-review` (Workflow, blocking)

Thêm sau đánh giá T074 (2026-11-07): chỉ có kiểm duyệt từ khóa ở đầu ra thì lời giải hoàn chỉnh lọt qua chính sách
"không đưa đáp án" (ASR nhóm academic_integrity 5/10). Backend gọi app này với khóa `DIFY_REVIEW_KEY` sau khi runner
trả lời `ok`, cho học sinh và phụ huynh (giáo viên được xem đáp án theo thiết kế). Chạy sau khi stream xong nên không
làm chậm chữ đầu tiên.

| Input | Kiểu | Nội dung |
|---|---|---|
| `question` | paragraph (≤ 4000) | Tin nhắn đã ẩn thông tin cá nhân |
| `reply` | paragraph (≤ 12000) | Câu trả lời của runner |
| `role` | select (`student`, `parent`, `teacher`) | |
| `no_direct_answers` | select (`true`/`false`) | `true` khi lớp bật chính sách và người hỏi là học sinh |

Output: `verdict` (`allow` \| `block`), `category` (`unsafe`, `privacy`, `injection`, `academic_integrity`),
`reason`. `block` → `text_reset` + câu cài sẵn (`answer_withheld` cho `academic_integrity`, `output_blocked` cho
nhóm khác), `status="blocked"`, `guard_events` stage `output` detector `dify_review`; token ghi purpose
`output_guard`. Review lỗi hoặc hết giờ: giữ câu trả lời (đã qua kiểm duyệt từ khóa), ghi log.
