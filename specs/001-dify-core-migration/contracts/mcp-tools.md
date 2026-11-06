# Hợp đồng: MCP tools qua HTTP

- **URL**: `/mcp` trên backend (Dify gọi qua `MCP_PUBLIC_URL`, ví dụ `http://host.docker.internal:8001/mcp`).
- **Transport**: MCP streamable HTTP.
- **Xác thực**: header `Authorization: Bearer <MCP_TOKEN>`. Thiếu hoặc sai → HTTP 401, không gọi tool nào.
- **Tool**: `class_doc_search`, `quiz_generator`, `rubric_grader`, `math_check`, `progress_summary`. Tham số giữ
  như `app/tools/server.py` hiện tại; tham số đầu tiên luôn là `ctx` (turn handle).

## Kiểm tra trong handler (theo thứ tự)

| # | Điều kiện | Kết quả khi sai |
|---|---|---|
| 1 | `ctx` tồn tại và chưa hết hạn | lỗi tool "Ngữ cảnh gọi công cụ không hợp lệ hoặc đã hết hạn." |
| 2 | tool có trong registry | từ chối, ghi `guard_events` (stage `tool`, category `tool_denied`) |
| 3 | tool có trong manifest của agent trong handle | như trên |
| 4 | vai trò trong handle được dùng tool | như trên |
| 5 | tool cần lớp và handle có `class_id` | như trên |
| 6 | tham số hợp lệ | lỗi tool, không ghi `guard_events` |

Mọi lần gọi (kể cả bị từ chối) ghi một dòng `tool_calls`, không lưu `ctx` trong `arguments`, và đẩy sự kiện
`tool` (`start`, rồi `done`/`denied`/`error`) vào hàng đợi của `message_id`.

## Trích dẫn

`class_doc_search` giữ dạng kết quả hiện nay (`{"results": [{title, location, score, content}], "note"}`), thêm
`document_id` vào mỗi kết quả. Nguồn đổi thành API retrieve của Dify trên `dataset_id` của handle. Handler thêm các
kết quả vào `citations` của handle.
