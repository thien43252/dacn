# Fixture Dify

Phản hồi của Dify 1.19.0 (bản ghim trong `infra/dify/README.md`) để test backend chạy offline qua
`httpx.MockTransport` (FR-027, research R14). Ghi ngày 2026-11-07 trong spike T006 với các DSL trong `infra/dify/`,
model gpt-4o-mini, `user` = `spike-user`. Id hội thoại, tin nhắn và task là UUID ngẫu nhiên của Dify local.

## Danh sách

| File | Nguồn | Dùng cho |
|---|---|---|
| `triage_safe.json` | ghi thật, "giải giúp em phương trình 2x+3=7" | định tuyến bằng LLM router |
| `triage_routing.json` | ghi thật, "@cham-van chấm giúp em bài văn tả mẹ" | định tuyến `mention` |
| `triage_block.json` | ghi thật, câu jailbreak | chặn đầu vào |
| `triage_self_harm_risk.json` | ghi thật, "em muon chet, chang ai hieu em" | `safety_note=true` |
| `triage_self_harm_method.json` | ghi thật, hỏi số viên thuốc ngủ | chặn + trả lời hỗ trợ 111 |
| `runner_plain.sse` | ghi thật, so sánh phân số | stream văn bản (có ký tự LaTeX, tiếng Việt) |
| `runner_tool.sse` | ghi thật, gọi `math_check` với `ctx` giả | stream có `agent_log` của tool; backend bỏ qua |
| `runner_message_replace.sse` | ghi thật, kiểm duyệt đầu ra chặn | `message_replace` → `text_reset` |
| `runner_input_blocked.sse` | ghi thật, kiểm duyệt đầu vào chặn | chỉ có `message` cài sẵn + `message_end` |
| `runner_input_too_long.sse` | ghi thật, `system_prompt` 12001 ký tự | `workflow_finished` lỗi, không có `message` |
| `runner_tool_denied.sse` | ghi thật (2026-11-07, Phase 9): `ctx` là handle không còn sống, MCP handler từ chối `math_check`; `agent_log` mang lỗi, model vẫn trả lời | tool bị từ chối trong Dify |
| `runner_error_midstream.sse` | **dựng tay**: 5 `message` đầu của `runner_plain.sse` + sự kiện `error` theo `core/app/apps/base_app_generate_response_converter.py` | lỗi giữa stream |
| `runner_conversation_not_found.json` | ghi thật (Phase 9): `conversation_id` không tồn tại → 404 `not_found` | `context_reset` |
| `suggested.json` | ghi thật (Phase 9): `GET /v1/messages/{id}/suggested` sau một câu trả lời về phân số | gợi ý câu hỏi |
| `dataset_create.json`, `document_create.json`, `document_delete_missing.json`, `indexing_status_*.json`, `dataset_retrieve.json` | ghi thật (US5) | kho tri thức của lớp |
| `document_segments.json` | ghi thật (Phase 9): 3 đoạn đầu của tài liệu chương 3 | xem trước các đoạn của tài liệu |

Còn dựng tay: `runner_error_midstream.sse`, vì Dify không có cách gây lỗi giữa stream theo ý muốn. Hình dạng sự kiện
lấy từ mã nguồn Dify 1.19.

## Cách ghi

```bash
curl -N -X POST "$DIFY_BASE_URL/v1/chat-messages" \
  -H "Authorization: Bearer $DIFY_RUNNER_KEY" -H "Content-Type: application/json" \
  -d '{"inputs": {...}, "query": "...", "response_mode": "streaming", "conversation_id": "", "user": "fixture-user"}' \
  > runner_plain.sse
```

Trước khi lưu: thay mọi khóa API, id người dùng thật bằng giá trị giả (`fixture-user`, `spike-user`). Không lưu
nội dung có thông tin cá nhân. Giữ mỗi sự kiện một dòng `data: ...`, cách nhau bởi dòng trống.
