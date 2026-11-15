# Contract: Stream sự kiện hội thoại (SSE)

## Hai kênh

| Kênh | Dùng cho | Thay đổi |
|---|---|---|
| `POST /api/chat/stream` | Lượt chat do chính người gửi khởi tạo | Đã có. Thêm các sự kiện ở bảng dưới. |
| `GET /api/chat/conversations/{id}/events?after=<seq>` | Mọi thứ đến sau hoặc đến từ người khác: tin của thành viên nhóm, câu trả lời giao việc, lượt làm tiếp, thẻ câu hỏi và thẻ duyệt, câu trả lời của người nhận | Mới (R2) |

**Kênh events**:
- Chỉ thành viên chưa rời nhóm mới mở được. Người khác nhận 404, để không lộ hội thoại tồn tại.
- Khi mở kênh, server phát lại mọi tin có `seq > after` mà người xem được thấy, rồi giữ kết nối mở.
- Server gửi `ping` mỗi 20 giây.

## Định dạng

Mỗi sự kiện là `data: <json>\n\n`. Các sự kiện đang có giữ nguyên định dạng: `operation`, `conversation`, `agent`,
`text_delta`, `text_reset`, `tool`, `notice`, `error`, `done`.

## Sự kiện mới

| `type` | Trường | Khi nào |
|---|---|---|
| `message` | `seq`, `message` (`MessageOut`, xem rest-api.md) | Có tin mới đã lưu: tin người, tin agent, tin hệ thống. |
| `message_update` | `seq`, `message` | Tin có thay đổi trạng thái. Ví dụ: thẻ đã được trả lời, nội dung bị ẩn, handoff đổi trạng thái. |
| `handoff` | `handoff_id`, `run_message_id`, `from_agent`, `to_agent`, `parent_handoff_id`, `status` (`queued \| running \| answered \| no_answer \| refused \| hidden \| late`) | Một handoff đổi trạng thái. Dùng để vẽ thanh "Đã hỏi" (FR-020, FR-022). |
| `handoff_answer` | `handoff_id`, `seq`, `text` | Nguyên văn câu trả lời đã qua kiểm duyệt. Trong chat riêng, nội dung nằm trong thanh; trong nhóm, nó là tin riêng có `reply_to_agent`. |
| `run` | `run_id`, `agent`, `status` (`waiting \| running \| done`), `waiting_for` (list) | Trạng thái lượt chạy, ví dụ "Đang chờ cô Lan trả lời" (FR-030). |
| `approval_card` | `card` (`ApprovalCardOut`) | Có thẻ duyệt mới cho chính người xem. |
| `person_request` | `request` (`PersonRequestOut`) | Có thẻ câu hỏi mới trong hội thoại. Chỉ người nhận có nút trả lời (FR-028). |
| `read` | `user_id`, `last_read_seq` | Một thành viên đã đọc tới đâu. Tuỳ chọn, dùng cho dấu "đã xem". |
| `ping` | | Giữ kết nối. |

## Ánh xạ trạng thái handoff (DB → client)

| DB (`handoffs`) | Client (`handoff.status`) |
|---|---|
| `queued` | `queued` |
| `running` | `running` |
| `answered`, `answer_visible=true` | `answered` |
| `answered`, `answer_visible=false` | `hidden` |
| `answered`, `late=true` | `late` |
| `failed` | `no_answer` |
| `refused` | `refused` |

## Bất biến

- **Một lần, đúng thứ tự**: `seq` tăng dần trong mỗi hội thoại. Client bỏ qua tin có `seq` nhỏ hơn hoặc bằng `seq` lớn
  nhất đã nhận, nên phát lại không tạo bản trùng (SC-005).
- **Đã kiểm duyệt trước khi phát**: nội dung trong `message`, `handoff_answer` và `person_request` đều đã qua kiểm duyệt
  đầu ra theo người xem. Nội dung bị ẩn được phát với `status="hidden"` và `content` là "Nội dung đã được ẩn" (FR-052).
- **Lọc theo người xem**: tin có `visible_to` chỉ phát cho đúng những người đó.
- **Không lộ luồng nháp**: transcript của agent được hỏi không bao giờ được phát; chỉ câu trả lời nguyên văn cuối cùng
  được phát.
