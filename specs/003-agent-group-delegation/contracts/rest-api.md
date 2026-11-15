# Contract: REST API

Quy ước chung:
- Mọi endpoint nằm dưới `/api`.
- Xác thực bằng cookie httpOnly hiện có.
- Lỗi trả về `{"detail": "<tiếng Việt>"}`.
- Không có quyền xem một hội thoại thì trả `404`, không trả `403`, để không lộ hội thoại tồn tại (FR-040, FR-050).

## Hội thoại (Messenger)

| Method và đường dẫn | Mô tả | Yêu cầu |
|---|---|---|
| `GET /chat/conversations?class_id=&q=` | Danh sách hội thoại của người dùng (chat riêng và nhóm), sắp theo tin mới nhất. | FR-049 |
| `POST /chat/direct` | Body `{class_id?, agent}`. Mở chat riêng đang có với agent, hoặc tạo mới. | FR-048, FR-049 |
| `POST /chat/direct/{id}/restart` | Lưu trữ chat riêng hiện tại và mở chat mới với cùng agent. | FR-049 |
| `POST /chat/groups` | Body `{class_id, title, members: [user_id], agents: [slug], default_agent?}`. Tạo nhóm. | FR-039, FR-040 |
| `PATCH /chat/groups/{id}` | Body `{title?, default_agent?}`. Chỉ quản trị nhóm. | FR-041 |
| `POST /chat/groups/{id}/members` | Body `{users?: [], agents?: [], can_see_history?: bool}`. Áp quy tắc thêm thành viên của học sinh. | FR-039, FR-047 |
| `DELETE /chat/groups/{id}/members/{member_id}` | Bớt thành viên hoặc tự rời nhóm. | FR-047 |
| `GET /chat/groups/{id}/candidates` | Danh sách người và agent mà người gọi được phép thêm. | FR-039 |
| `GET /chat/conversations/{id}/messages?before=&limit=` | Danh sách tin đã lọc theo người xem. | FR-047, FR-050 |
| `POST /chat/conversations/{id}/read` | Body `{seq}`. Đánh dấu đã đọc tới `seq`. | FR-049 |
| `GET /chat/conversations/{id}/events?after=` | Stream SSE, xem conversation-events.md. | |
| `POST /chat/stream` | Đã có. `ChatIn` bỏ trường `agent`, thêm `conversation_id` bắt buộc. Chat riêng thì agent cố định; nhóm thì định tuyến theo FR-043. | |

**`ConversationOut`**:

```json
{
  "id": "…",
  "kind": "direct | group",
  "class_id": "… | null",
  "title": "Gia sư Toán | Ôn thi HK1 – 9A",
  "agent": {"slug": "gia-su-toan", "name": "…", "avatar": "owl"},
  "members_preview": [{"name": "…", "role_label": "GV Toán"}],
  "last_message": {"seq": 41, "sender": "…", "text": "…", "at": "…"},
  "unread": 3,
  "waiting_for": ["Cô Lan"]
}
```

- `agent` chỉ có khi `kind` là `direct`.
- `members_preview` chỉ có khi `kind` là `group`.

**`MessageOut`**: các trường đang có, thêm các trường sau:

```json
{
  "seq": 42,
  "sender": {"kind": "user | agent | system", "id": "…", "name": "…", "role_label": "GV Toán | Phụ huynh của An | Học sinh", "avatar": "…"},
  "reply_to_agent": "tro-ly-lop | null",
  "handoffs": [{"id": "…", "to_agent": "…", "status": "…", "task": "…", "answer": "… | null", "children": []}],
  "person_request": "PersonRequestOut | null",
  "approval_card": "ApprovalCardOut | null"
}
```

- `handoffs` chỉ có ở tin của agent hỏi trong chat riêng. Đây là cây dùng để vẽ các thanh "Đã hỏi" lồng nhau
  (FR-020 đến FR-022).

## Agent và quyền giao việc

| Method và đường dẫn | Thay đổi | Yêu cầu |
|---|---|---|
| `POST /agents`, `PUT /agents/{id}`, `POST /agents/{id}/versions`, `POST /agents/{id}/try`, `GET /agents/mine`, `POST /agents/{id}/fork`, `DELETE /agents/{id}` | Mở cho học sinh và phụ huynh (`Maker`). `ManifestIn` thêm `handoff_to`. Công cụ và `handoff_to` được kiểm theo vai trò người tạo. Lỗi `422` có lời tiếng Việt. | FR-001 đến FR-006 |
| `GET /agents/{id}/handoff-candidates` | Danh sách agent mà người tạo được cấp quyền giao việc tới. | FR-006 |
| `PATCH /classes/{class_id}/agents/{installation_id}` | Thêm `handoff_allow: [slug] \| null`. Chỉ giáo viên của lớp. | FR-006 |
| `POST /classes/{class_id}/agent-requests` | Body `{agent_id}`. Học sinh hoặc phụ huynh xin đưa agent tự tạo vào lớp: đi qua duyệt (`share`), cần phiên bản `certified`, rồi tạo `person_request` loại `install_agent` gửi giáo viên. | FR-003 |
| `PUT /classes/{class_id}/policy` | `PolicyModel` thêm `allow_handoffs`, `members_can_create_groups`, `allow_member_agents`. | FR-019, FR-040 |
| `PATCH /classes/{class_id}/members/{member_id}` | Body `{subject}` cho giáo viên. | FR-025 |

## Hộp yêu cầu (hỏi người)

| Method và đường dẫn | Mô tả | Yêu cầu |
|---|---|---|
| `GET /inbox?status=open\|answered\|all&class_id=` | Các câu hỏi gửi tới người dùng. | FR-028 |
| `GET /inbox/count` | `{"open": 2}`. Cũng trả trong `GET /auth/me` dưới tên `inbox_open`. | FR-028 |
| `POST /person-requests/{id}/answer` | Body `{choice?: "Đồng ý", text?: "…"}`. Chỉ `recipient_id` trả lời được, và chỉ một lần. Lần thứ hai nhận `409` "Câu hỏi đã được trả lời". | FR-029 |
| `POST /person-requests/{id}/cancel` | Chỉ người dùng gốc huỷ được. | FR-030 |

**`PersonRequestOut`**:

```json
{
  "id": "…", "kind": "approval", "status": "open",
  "requester": {"name": "Nguyễn An", "class": "9A"}, "agent": {"slug": "tro-ly-lop", "name": "Trợ lý lớp"},
  "recipient": {"name": "Cô Lan", "role_label": "GV Toán"},
  "body": "…", "options": ["Đồng ý", "Sửa", "Từ chối"],
  "answer": null, "answered_by": null, "expires_at": "…", "can_answer": true
}
```

## Duyệt hành động

| Method và đường dẫn | Mô tả | Yêu cầu |
|---|---|---|
| `POST /approvals/{card_id}/answer` | Body `{choice: "once" \| "conversation" \| "always" \| "deny" \| "did_it" \| "dont"}`. Chỉ người dùng gốc, và chỉ khi `choice` nằm trong `card.choices`. Hành động được chạy đúng một lần trong cùng giao dịch, rồi lượt chạy được đánh thức. | FR-033, FR-036 |
| `GET /settings/approvals` | `{extra_vigilant, rules: [...], conversation_allowances: [...]}` | FR-032 |
| `PATCH /settings/approvals` | Body `{extra_vigilant}` | FR-032 |
| `DELETE /settings/approvals/rules/{id}` | Xoá một quy tắc "Luôn cho phép ở đây" hoặc tắt một lựa chọn "Cho phép trong hội thoại này". | FR-033 |
| `GET/PUT /admin/approvals/modes` | Chế độ duyệt theo từng `action_kind` và `role` (admin). | FR-035 |
| `GET/POST/DELETE /admin/approvals/rules` | Quy tắc của admin. Quy tắc này chỉ làm chặt hơn, không mở được loại luôn phải hỏi. | FR-034 |

**`ApprovalCardOut`**:

```json
{
  "id": "…", "status": "open", "agent": "tro-ly-lop", "tool": "ask_person", "action_kind": "send",
  "summary": "Gửi câu hỏi cho Cô Lan (GV Toán)",
  "preview": {"body": "…", "targets": [{"name": "Cô Lan", "role_label": "GV Toán"}]},
  "choices": ["once", "deny"], "expires_at": "…"
}
```

## Hoạt động và nhật ký

| Method và đường dẫn | Thay đổi | Yêu cầu |
|---|---|---|
| `GET /agents/{id}/activity` | Mới. Chủ agent xem được: lần chạy, giao việc, từ chối kèm lý do, tệp đã lưu (tên và kích thước). Không có nội dung hội thoại của người khác. | FR-057 |
| `GET /classes/{class_id}/audit` | Chỉ trả sự kiện của các nhóm mà giáo viên là thành viên. Thêm dòng giao việc, câu hỏi gửi người và quyết định duyệt. | FR-051, FR-057 |
| `GET /me/activity?conversation_id=` | Mới. Học sinh, phụ huynh xem hoạt động trong hội thoại của chính mình. | FR-057 |
| `GET /audit/events` (admin) | Thêm các loại sự kiện mới. Bỏ `excerpt` khi `private_space=true`. | FR-051, FR-057 |
| `GET /admin/usage` | Tách `turns_with_handoff` và `turns_without_handoff`. | FR-055 |
