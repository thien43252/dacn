# Contract: Công cụ nền tảng cho agent

Agent gọi các công cụ này như mọi công cụ khác, qua vòng lặp công cụ trong `run_agent`. Điểm khác là runtime tự xử lý
chúng (`meta=True`), không qua MCP server, và chúng không cần khai báo trong manifest. Mọi lời gọi vẫn đi qua tool
guard và được ghi vào `tool_calls`.

## `message_agent`: giao việc cho agent khác (FR-006 đến FR-017)

**Khi nào được mời**: có ít nhất một agent đích hợp lệ theo `data-model.md` §4. Nếu không có agent đích nào hợp lệ,
công cụ không xuất hiện trong danh sách `tools` gửi cho mô hình.

**Tham số** (mô hình điền):

```json
{
  "agent": "on-tap-tai-lieu",
  "task": "Tìm phần lý thuyết định lý Pytago trong tài liệu lớp, kèm trích nguồn.",
  "bounds": "Chỉ dùng tài liệu lớp; tối đa 150 từ; không đưa lời giải bài tập.",
  "good_answer": "Định lý phát biểu đúng, 1 ví dụ, tên tài liệu và trang.",
  "attachments": "Câu hỏi của học sinh: …"
}
```

- `agent`: slug. Được hiển thị cho mô hình dưới dạng `enum` gồm các agent đích hợp lệ.
- `task`, `bounds`, `good_answer`: bắt buộc. Mỗi trường từ 1 đến 1000 ký tự.
- `attachments`: tuỳ chọn, tối đa 4000 ký tự.

**Nền tảng tự điền, mô hình không đặt được** (FR-008): hội thoại gốc, `from_agent`, `depth`, `chain`, người dùng gốc.

**Kết quả trả cho mô hình**: khi đã nhận yêu cầu, công cụ trả ngay, không chờ agent đích trả lời.

```json
{"status": "queued", "handoff_id": "…", "note": "Câu trả lời sẽ được ghi vào hội thoại; bạn sẽ được gọi lại khi mọi yêu cầu đã có kết quả."}
```

Lời từ chối dùng chung cho cả ba trường hợp: không được cấp quyền, agent không tồn tại, agent không được thấy (FR-009).

```json
{"status": "refused", "reason": "Không thể giao việc cho agent này."}
```

Lời từ chối do giới hạn hoặc vòng lặp:

```json
{"status": "refused", "reason": "Đã đạt giới hạn giao việc của lượt này."}
```

**Khi lượt chạy được gọi lại** (FR-017): mỗi `tool_call` `message_agent` nhận một `tool` message có một trong ba dạng
sau, tuỳ kết quả của handoff:

```json
{"status": "answered", "agent": "on-tap-tai-lieu", "answer": "<nguyên văn>"}
{"status": "no_answer", "agent": "tao-de"}
{"status": "hidden", "agent": "tao-de", "note": "Câu trả lời đã bị ẩn theo chính sách lớp."}
```

**Lượt chạy của agent được hỏi**:
- Agent được hỏi nhận một tin `user` duy nhất, dựng từ `task`, `bounds`, `good_answer`, `attachments` và tên agent hỏi.
  Nó không nhận lịch sử hội thoại (FR-007).
- Agent được hỏi có thể gọi `message_agent` tiếp, tuỳ quyền và giới hạn, và có thể gọi `ask_person`.

## `ask_person`: hỏi người (FR-024 đến FR-031)

**Khi nào được mời**: luôn được mời, trừ khi sàng lọc đã chuyển lượt sang luồng hỗ trợ an toàn (FR-053).

**Tham số**:

```json
{
  "recipient": "self | teacher | homeroom | parent | <user_id>",
  "subject": "toan",
  "question": "Em An (9A) xin nộp bài Toán muộn 2 ngày vì bị ốm. Cô có đồng ý không?",
  "kind": "approval | question | choice",
  "options": ["Đồng ý", "Sửa", "Từ chối"]
}
```

- `recipient`:
  - `self` là người đang trò chuyện. Câu hỏi hiện ngay trong hội thoại, không cần duyệt.
  - `teacher` cùng `subject`: nền tảng chọn giáo viên đúng môn. Có nhiều người thì thẻ duyệt cho người dùng chọn.
  - `homeroom`: chủ lớp.
  - `parent`: phụ huynh đã liên kết của chính học sinh.
  - Một `user_id` chỉ được chấp nhận khi người đó thuộc danh sách `allowed_recipients`.
- Mọi người nhận ngoài `allowed_recipients` bị từ chối (FR-025).

**Quy trình**:
1. Ẩn thông tin cá nhân và kiểm duyệt nội dung `question` (FR-031). Không qua thì trả `{"status": "refused", …}`.
2. Gửi tới người khác là hành động `action_kind="send"`, nên đi qua duyệt hành động (contract REST, mục Duyệt).
3. Lượt chạy chuyển sang `waiting`. Kết quả trả cho mô hình khi được gọi lại:

```json
{"status": "answered", "by": "Cô Lan (GV Toán)", "answer": "Sửa: cho nộp muộn 1 ngày"}
{"status": "undeliverable" | "expired" | "cancelled" | "denied_by_user"}
```

## `reply_privately`: trả lời riêng (FR-046)

**Khi nào được mời**: chỉ trong hội thoại `group`.

**Tham số**:

```json
{"reason": "Câu hỏi về điểm của riêng em An."}
```

**Tác dụng**:
1. Ghi vào nhóm một tin ngắn cố định: "Mình sẽ trả lời riêng cho bạn trong chat riêng."
2. Mở hoặc tạo hội thoại `direct` giữa người gọi và agent đó.
3. Chép câu hỏi gốc vào hội thoại riêng, rồi chạy một lượt ở đó.
4. Kết thúc lượt trong nhóm.

**Nhóm công cụ dữ liệu riêng**: `progress_summary` và các công cụ có cờ `personal_data=True`. Các công cụ này **không
được mời** trong hội thoại nhóm, kể cả trong lượt chạy của agent được hỏi khi hội thoại gốc là nhóm.

## Thuộc tính mới của `PlatformTool`

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `meta` | bool | Runtime tự xử lý, không cần có trong manifest. |
| `action_kind` | `none \| change \| send \| share \| post \| delete \| settings \| money` | Đầu vào của duyệt hành động (FR-032). |
| `personal_data` | bool | Không mời trong nhóm (FR-046). |
| `group_only` | bool | Chỉ mời trong nhóm (`reply_privately`). |
