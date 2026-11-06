# Fixture Dify

Phản hồi ghi từ Dify thật (bản ghim trong `infra/dify/README.md`) để test engine `dify` chạy offline qua
`httpx.MockTransport` (FR-027, research R14).

## Danh sách

| File | Nguồn | Dùng cho |
|---|---|---|
| `triage_safe.json` | `POST /v1/workflows/run`, câu hỏi toán | định tuyến thường |
| `triage_block.json` | câu hỏi nguy hiểm | chặn đầu vào |
| `triage_self_harm_risk.json` | câu có dấu hiệu tự làm hại | `safety_note=true` |
| `triage_self_harm_method.json` | câu hỏi cách tự làm hại | chặn + trả lời hỗ trợ 111 |
| `triage_routing.json` | câu hỏi tiếng Anh, không chọn agent | LLM router |
| `runner_plain.sse` | `POST /v1/chat-messages`, trả lời thường | stream văn bản |
| `runner_tool.sse` | câu cần `math_check` | stream có tool |
| `runner_tool_denied.sse` | tool không được cấp | tool bị từ chối |
| `runner_message_replace.sse` | kiểm duyệt đầu ra chặn | `text_reset` |
| `runner_error_midstream.sse` | dừng Dify giữa lượt | lỗi giữa stream |
| `runner_conversation_not_found.json` | `conversation_id` không tồn tại | `context_reset` |
| `suggested.json` | `GET /v1/messages/{id}/suggested` | gợi ý câu hỏi |
| `dataset_retrieve.json` | `POST /v1/datasets/{id}/retrieve` | `class_doc_search` |
| `indexing_status_completed.json` | `GET .../indexing-status` | tài liệu sẵn sàng |
| `indexing_status_error.json` | file lỗi | tài liệu lỗi |

## Cách ghi

```bash
curl -N -X POST "$DIFY_BASE_URL/v1/chat-messages" \
  -H "Authorization: Bearer $DIFY_RUNNER_KEY" -H "Content-Type: application/json" \
  -d '{"inputs": {...}, "query": "...", "response_mode": "streaming", "conversation_id": "", "user": "fixture-user"}' \
  > runner_plain.sse
```

Trước khi lưu: thay mọi khóa API, id người dùng, id hội thoại thật bằng giá trị giả (`fixture-user`,
`00000000-...`). Không lưu nội dung có thông tin cá nhân.
