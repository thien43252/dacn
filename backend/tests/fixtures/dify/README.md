# Fixture Dify

Phản hồi của Dify 1.19.0 (bản ghim trong `infra/dify/README.md`) để test engine `dify` chạy offline qua
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
| `runner_error_midstream.sse` | **dựng tay**: 5 `message` đầu của `runner_plain.sse` + sự kiện `error` theo `core/app/apps/base_app_generate_response_converter.py` | lỗi giữa stream |
| `runner_conversation_not_found.json` | **dựng tay** theo `controllers/service_api/app/completion.py` (404 `not_found`, "Conversation Not Exists.") | `context_reset` |
| `suggested.json` | **dựng tay** theo `SimpleResultStringListResponse` của `GET /v1/messages/{id}/suggested` | gợi ý câu hỏi |

Chưa có (cần backend chạy engine `dify` với Dify thật, hoặc thuộc US4/US5): `runner_tool_denied.sse`,
`dataset_retrieve.json`, `indexing_status_completed.json`, `indexing_status_error.json`. Ba file dựng tay ghi lại
từ Dify thật khi có dịp.

## Cách ghi

```bash
curl -N -X POST "$DIFY_BASE_URL/v1/chat-messages" \
  -H "Authorization: Bearer $DIFY_RUNNER_KEY" -H "Content-Type: application/json" \
  -d '{"inputs": {...}, "query": "...", "response_mode": "streaming", "conversation_id": "", "user": "fixture-user"}' \
  > runner_plain.sse
```

Trước khi lưu: thay mọi khóa API, id người dùng thật bằng giá trị giả (`fixture-user`, `spike-user`). Không lưu
nội dung có thông tin cá nhân. Giữ mỗi sự kiện một dòng `data: ...`, cách nhau bởi dòng trống.
