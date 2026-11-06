# Data Model: Chuyển lõi agent sang Dify

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Tất cả thay đổi schema nằm trong một migration Alembic mới `0006_dify_runtime.py`. Không sửa migration cũ. Mọi cột
mới đều cho phép null để engine cũ vẫn chạy trên cùng database (R10).

## Bảng thay đổi

### `conversations` (Hội thoại)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `dify_conversation_id` | `String(64)`, null | Mã hội thoại của `eduagent-runner`. Null khi chưa có lượt nào qua Dify. |

- Một hội thoại nền tảng gắn với tối đa một hội thoại Dify tại một thời điểm (FR-005a).
- Khi Dify báo không tìm thấy hội thoại: thay bằng mã mới, phát `notice` `context_reset` (R5).
- Hội thoại `kind="sandbox"` và hội thoại kiểm định cũng có mã riêng; kiểm định tạo hội thoại mới cho mỗi tình huống.

### `classes` (Lớp)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `dify_dataset_id` | `String(64)`, null, unique | Kho tri thức Dify của lớp (quan hệ 1–1). Tạo khi lớp có tài liệu đầu tiên. |

- `policy` (JSON) bỏ khóa `blocked_topics`: API không nhận và không trả khóa này nữa; dữ liệu cũ bị bỏ qua khi đọc
  (FR-013). Giữ `no_direct_answers`, `allowed_subjects`, `notes_for_agents`.
- Xóa lớp: backend xóa kho Dify tương ứng (best effort, lỗi được ghi log, không chặn việc xóa lớp).

### `documents` (Tài liệu lớp)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `dify_document_id` | `String(64)`, null | Mã tài liệu trong kho Dify của lớp. |
| `dify_batch` | `String(64)`, null | Mã batch indexing để hỏi trạng thái. |

**Chuyển trạng thái** (`status`):

```
processing ──(Dify indexing completed)──▶ ready
     │
     └──(Dify indexing error / upload lỗi)──▶ failed ──(Xử lý lại)──▶ processing
```

- `ready` chỉ khi Dify báo `completed`. `error` lấy từ thông báo lỗi của Dify (cắt 500 ký tự).
- Xóa tài liệu: xóa trong Dify trước, rồi xóa bản ghi. Nếu Dify lỗi, tài liệu giữ nguyên và giao diện báo lỗi.
- `chunk_count` lấy từ số segment Dify trả về.

### `chat_messages` (Lượt chat)

Không thêm cột. Bổ sung khóa trong `meta` (JSON) của tin nhắn `assistant`:

| Khóa | Kiểu | Ghi chú |
|---|---|---|
| `engine` | `"langgraph" \| "dify"` | Engine đã xử lý lượt, để so sánh và lọc. |
| `dify_message_id` | string | Dùng để lấy gợi ý câu hỏi và tra log Dify. |
| `citations` | list `{document_id, title, location, excerpt}` | Trích dẫn đã hiển thị (R8). `excerpt` ≤ 300 ký tự. |
| `suggestions` | list string | Câu hỏi gợi ý đã hiển thị, tối đa 3. |

Các khóa hiện có (`route_reason`, `tools`, `guard`, `latency_ms`) giữ nguyên.

### `guard_events` (Sự kiện guardrail)

Không đổi schema. Giá trị mới:

| Cột | Giá trị mới |
|---|---|
| `detector` | `dify_classifier` (triage), `dify_moderation` (kiểm duyệt cấp ứng dụng), `privacy` (ẩn thông tin cá nhân ở backend) |
| `category` | nhãn của triage: `self_harm_risk`, `self_harm_method`, `jailbreak`, `dangerous`, `age_inappropriate`; `moderation` cho kiểm duyệt cấp ứng dụng; `pii`; `tool_denied` (giữ nguyên) |
| `stage` | `input`, `tool`, `output` (giữ nguyên) |

`excerpt` vẫn qua `redact()` trước khi lưu.

### `tool_calls` (Lần gọi tool)

Không đổi schema. Từ nay do handler MCP ghi (R6), cho cả hai engine. `arguments` không bao giờ chứa `ctx`.

### `usage_ledger`

Không đổi schema. `purpose` thêm giá trị `triage` (token của `eduagent-triage`). `provider="dify"`, `model` lấy
từ metadata Dify trả về; `cost_usd` dùng giá Dify báo nếu có, nếu không thì tính theo bảng giá hiện có.

## Thực thể không lưu trong database

### Turn handle (ngữ cảnh gọi tool)

Dữ liệu trong bộ nhớ, sống tối đa 10 phút hoặc tới khi lượt kết thúc.

| Trường | Ghi chú |
|---|---|
| `handle` | chuỗi ngẫu nhiên 128 bit, gửi sang Dify làm input `ctx` |
| `user_id`, `role`, `class_id`, `grade`, `conversation_id`, `message_id` | lấy từ phiên đăng nhập và lớp |
| `agent_slug`, `allowed_tools` | agent triage đã chọn và tool trong manifest của agent đó |
| `dataset_id` | kho tri thức của lớp, null nếu ngoài lớp |
| `events` | hàng đợi sự kiện `tool` cho SSE |
| `citations` | kết quả `class_doc_search` gom trong lượt |
| `expires_at` | hết hạn thì mọi lần gọi tool bị từ chối |

### Ứng dụng Dify (cấu hình trong repo)

| Ứng dụng | Loại | File DSL | Khóa `.env` |
|---|---|---|---|
| `eduagent-triage` | Workflow | `infra/dify/eduagent-triage.yml` | `DIFY_TRIAGE_KEY` |
| `eduagent-runner` | Chatflow | `infra/dify/eduagent-runner.yml` | `DIFY_RUNNER_KEY` |
| `eduagent-runner-raw` | Chatflow, tắt kiểm duyệt | `infra/dify/eduagent-runner-raw.yml` | `DIFY_RUNNER_RAW_KEY` |

Input/output chi tiết: [contracts/dify-apps.md](contracts/dify-apps.md).

## Quy tắc kiểm tra dữ liệu

- `roster` gửi triage chỉ gồm agent có trong `available_agents()` của người dùng và lớp (FR-003); học sinh và phụ
  huynh chỉ thấy phiên bản đã đạt kiểm định (FR-018).
- `agent` triage trả về phải thuộc `roster`; nếu không, dùng `tro-ly-lop`.
- Nội dung gửi Dify (`query`, `system_prompt`) đã qua `redact()` (FR-011).
- `user` gửi Dify là `users.id` (FR-016).
