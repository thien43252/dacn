# Data Model: Tạo agent, nhóm chat, giao việc và hỏi người

Tài liệu này mô tả các thay đổi dữ liệu trên `main`. Tất cả nằm trong một migration mới,
`backend/migrations/versions/0006_groups_handoffs_approvals.py`.

Quy ước dùng chung:
- Kiểu dữ liệu theo SQLAlchemy hiện có.
- `id` là `String(36)`, sinh bằng `new_id`.
- `JSON` được dùng cho cả SQLite và Postgres.

## 1. Bảng sửa đổi

### `agents` và `AgentManifest` (FR-001 đến FR-006)

| Thay đổi | Chi tiết |
|---|---|
| `AgentManifest.handoff_to: list[str]` | Slug các agent được giao việc tới, tối đa 8, mặc định `[]`. Nằm trong `agent_versions.manifest`, nên được lưu theo từng phiên bản. |
| Ràng buộc khi lưu draft | Mỗi slug phải là agent mà người tạo đang dùng được (`available_agents` theo vai trò của người tạo), và không được là chính agent đó. |
| `agents.owner_id` | Không đổi. Giờ có thể là học sinh hoặc phụ huynh. |
| `agents.visibility` | Không đổi. Agent mới luôn là `private`. |

### `installations` (FR-006, FR-020)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `handoff_allow` | JSON, nullable | Giáo viên thu hẹp quyền giao việc trong lớp. `null` nghĩa là theo đúng manifest; một danh sách nghĩa là lấy giao với `manifest.handoff_to`. |

### `classes.policy` (thêm khoá vào `DEFAULT_POLICY`)

| Khoá | Mặc định | Yêu cầu |
|---|---|---|
| `allow_handoffs` | `true` | FR-020. `false` tương đương số tầng = 0 trong lớp. |
| `members_can_create_groups` | `true` | FR-040 |
| `allow_member_agents` | `true` | FR-003. Học sinh, phụ huynh được xin đưa agent tự tạo vào lớp. |

### `class_members`

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `subject` | String(16), nullable | Môn của giáo viên trong lớp (FR-025). Học sinh để `null`. Seed đặt môn cho giáo viên demo. |

### `conversations` (FR-039 đến FR-050)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `kind` | String(16) | Một trong `direct`, `group`, `sandbox`. Migration đổi `chat` thành `direct`. |
| `user_id` | giữ | Người tạo. Với `direct`, đây là người duy nhất. |
| `direct_agent_slug` | String(48), nullable | Agent của chat riêng. Bắt buộc khi `kind=direct`. |
| `default_agent_slug` | String(48), nullable | Agent mặc định của nhóm (FR-041). |
| `title` | giữ | Tên nhóm. Chat riêng hiện tên agent. |
| `last_seq` | Integer, mặc định 0 | `seq` của tin cuối, dùng để sắp danh sách và cấp `seq`. |
| `archived_at` | DateTime, nullable | Đặt khi người dùng "bắt đầu cuộc trò chuyện mới" với agent đó (FR-049). |

- Chỉ mục duy nhất một phần: mỗi bộ (`user_id`, `class_id`, `direct_agent_slug`) có tối đa một hội thoại `direct` chưa
  lưu trữ. SQLite dùng chỉ mục thường cùng kiểm tra trong service.

### `chat_messages`

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `seq` | Integer, có chỉ mục (`conversation_id`, `seq`), duy nhất | Thứ tự trong hội thoại, dùng cho phát bù sự kiện (R2). |
| `role` | giữ, thêm giá trị | Một trong `user`, `assistant`, `system`. `system` dùng cho thẻ duyệt, thẻ câu hỏi và trạng thái. |
| `sender_user_id` | FK users, nullable | Người gửi tin `user`. |
| `agent_slug` | giữ | Agent gửi tin `assistant`. |
| `handoff_id` | FK handoffs, nullable, duy nhất khi khác null | Tin là câu trả lời nguyên văn của một handoff (FR-014). Ràng buộc duy nhất đảm bảo FR-015. |
| `reply_to_agent` | String(48), nullable | Nhãn "trả lời cho <agent hỏi>" (FR-023). |
| `person_request_id` | FK person_requests, nullable | Tin là thẻ câu hỏi hoặc câu trả lời của người. |
| `approval_card_id` | FK approval_cards, nullable | Tin là thẻ duyệt. |
| `run_id` | FK agent_runs, nullable | Lượt chạy đã tạo ra tin. |
| `visible_to` | JSON, nullable | `null` nghĩa là mọi thành viên. Một danh sách `user_id` nghĩa là chỉ những người đó, ví dụ phản hồi hỗ trợ an toàn trong nhóm. |
| `status` | giữ, thêm giá trị | Thêm `hidden`: nội dung bị kiểm duyệt ẩn (FR-052). |

### `guard_events` (FR-051, FR-057)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `private_space` | Boolean, mặc định `true` | Sự kiện từ chat riêng hoặc nhóm. Nhật ký lớp của giáo viên chỉ hiện các sự kiện có `conversation_id` thuộc một nhóm mà giáo viên là thành viên. Admin thấy bản ghi, nhưng `excerpt` bị xoá khi `private_space=true`. |

## 2. Bảng mới

### `conversation_members`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | String(36) PK | |
| `conversation_id` | FK conversations, cascade | |
| `user_id` | FK users, nullable | Đúng một trong hai cột `user_id` và `agent_slug` khác null (CHECK). |
| `agent_slug` | String(48), nullable | |
| `is_admin` | Boolean | Người tạo nhóm và giáo viên trong nhóm (FR-041). |
| `joined_seq` | Integer | Tin có `seq` nhỏ hơn hoặc bằng giá trị này bị ẩn nếu `can_see_history=false` (FR-047). |
| `can_see_history` | Boolean, mặc định `false` | |
| `last_read_seq` | Integer, mặc định 0 | Dùng tính số tin chưa đọc (FR-049). |
| `left_at` | DateTime, nullable | Bị bớt khỏi nhóm. Từ thời điểm này không nhận và không xem được tin mới. |

- Ràng buộc duy nhất trên (`conversation_id`, `user_id`) và (`conversation_id`, `agent_slug`).
- Quy tắc thêm thành viên (FR-039):
  - Người dùng phải thuộc lớp của nhóm.
  - Khi người thêm là học sinh, người được thêm chỉ là học sinh cùng lớp, giáo viên của lớp, phụ huynh trong
    `parent_links` của chính học sinh đó, và agent dùng được trong lớp.

### `agent_runs` (R3)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | String(36) PK | |
| `conversation_id` | FK | Hội thoại gốc, luôn là nơi kết quả về (FR-008). |
| `user_id` | FK users | Người dùng gốc. Lượt chạy luôn dựng lại theo người này (FR-010). |
| `role` | String(16) | Vai trò của người dùng gốc trong lớp. |
| `class_id` | FK, nullable | |
| `agent_slug`, `agent_version_id` | | Agent chạy lượt này. |
| `handoff_id` | FK handoffs, nullable | Có giá trị khi lượt chạy là của agent được hỏi (luồng nháp). |
| `depth` | Integer | 0 là lượt của agent được người gọi. Handoff ở tầng d tạo lượt chạy ở tầng d+1. |
| `chain` | JSON list[str] | Slug các agent đã có trong chuỗi, để chặn vòng lặp (FR-012). |
| `handoff_count` | Integer | Số handoff đã tạo trong cả lượt gốc (FR-011). Tính chung qua `root_run_id`. |
| `root_run_id` | FK agent_runs, nullable | |
| `trigger_message_id` | FK chat_messages | Tin của người đã gọi lượt chạy. |
| `transcript` | JSON | Danh sách message của mô hình (system tách riêng), gồm tool_calls đang chờ. |
| `pending` | JSON | Các tool_call id đang chờ, kèm loại chờ (`handoff`, `person`, `approval`) và id tương ứng. |
| `status` | String(16) | Xem vòng đời bên dưới. |
| `source` | String(16) | Một trong `chat`, `sandbox`, `certify` (FR-038). |
| `created_at`, `updated_at` | | |

**Vòng đời**:

```text
running ──(gửi handoff / ask_person / cần duyệt)──▶ waiting
waiting ──(mọi pending có kết quả)──▶ resumable ──(worker lấy)──▶ running
running ──(kết thúc vòng công cụ, qua review)──▶ done
running ──(lỗi không thử lại được)──▶ failed
waiting ──(người dùng gốc huỷ, hội thoại bị xoá)──▶ cancelled
```

- Mỗi lần chuyển từ `resumable` sang `running` là một lượt làm tiếp, chạy một lần cho mỗi đợt chờ (FR-017).
- Worker lấy việc bằng `UPDATE … SET status='running' WHERE id=? AND status='resumable'`.

### `handoffs` (FR-006 đến FR-017)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | String(36) PK | Mã duy nhất (FR-015), tương đương `bot-answer:<bot>:<run>` của OpenBot. |
| `run_id` | FK agent_runs | Lượt chạy của agent hỏi. |
| `tool_call_id` | String | Lời gọi `message_agent` tương ứng. Duy nhất trên (`run_id`, `tool_call_id`). |
| `conversation_id` | FK | Hội thoại gốc. |
| `from_agent` | String(48) | Do nền tảng điền (FR-008). |
| `to_agent` | String(48) | Do nền tảng tra theo quyền và theo `available_agents` của người dùng gốc. |
| `depth` | Integer | |
| `task`, `bounds`, `good_answer` | Text | Yêu cầu có cấu trúc (FR-007). |
| `attachments` | Text | Nội dung agent hỏi chủ động đính kèm. Có giới hạn độ dài. |
| `status` | String(16) | Xem vòng đời bên dưới. |
| `refusal_reason` | String(200), nullable | Lý do nội bộ, ví dụ `not_granted`, `unknown_or_hidden`, `depth_cap`, `per_run_cap`, `loop`, `disabled`. Lời gửi cho agent luôn là cùng một câu cho ba lý do đầu (FR-009). |
| `attempts` | Integer | Thử lại tối đa `handoff_max_attempts` (mặc định 2) lần (FR-016). |
| `lease_until` | DateTime, nullable | |
| `answer` | Text, nullable | Nguyên văn câu trả lời. |
| `answer_visible` | Boolean, nullable | Kết quả kiểm duyệt khi hiển thị (FR-052). |
| `late` | Boolean | Câu trả lời về sau khi agent hỏi đã làm tiếp. |
| `created_at`, `finished_at` | | |

**Vòng đời**:

```text
(được mời) ── tool guard ──▶ refused                                   [ghi nhật ký, không chạy]
          └──▶ queued ──(worker lấy, lease)──▶ running ──▶ answered      [ghi tin nguyên văn đúng một lần]
                                                  └──(lỗi)──▶ queued (attempts+1) … ──▶ failed   ["không nhận được câu trả lời"]
```

### `person_requests` (FR-024 đến FR-031)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | String(36) PK | |
| `run_id` | FK agent_runs | Lượt chạy chờ câu trả lời, kể cả lượt chạy ở tầng sâu. |
| `tool_call_id` | String | |
| `conversation_id` | FK | Hội thoại gốc (FR-029). |
| `requester_id` | FK users | Người dùng gốc. |
| `agent_slug` | String(48) | Agent tạo câu hỏi. |
| `recipient_id` | FK users | Bằng `requester_id` khi hỏi chính người đang trò chuyện. |
| `kind` | String(16) | Một trong `question`, `approval`, `choice`, `install_agent`. |
| `body` | Text | Đã qua ẩn thông tin cá nhân và kiểm duyệt (FR-031). |
| `options` | JSON list[str] | Ví dụ `["Đồng ý", "Sửa", "Từ chối"]`. Câu trả lời tự do luôn được nhận. |
| `private_to_recipient` | Boolean | Câu hỏi có dữ liệu riêng phát sinh từ nhóm thì không hiện thẻ trong nhóm (FR-046). |
| `status` | String(16) | Xem vòng đời bên dưới. |
| `answer`, `answered_by`, `answered_at` | | |
| `expires_at` | DateTime | Mặc định cộng 72 giờ (FR-027). |
| `read_at` | DateTime, nullable | Dùng cho huy hiệu hộp yêu cầu. |

**Vòng đời**:

```text
draft ──(duyệt "send" nếu gửi người khác)──▶ open ──▶ answered | expired | cancelled
draft ──(bị từ chối duyệt)──▶ cancelled
(không có người nhận hợp lệ hoặc người nhận rời lớp) ──▶ undeliverable
```

- Khi hỏi chính người đang trò chuyện, câu hỏi bỏ qua bước duyệt và đi thẳng tới `open`.
- Câu trả lời chỉ được nhận khi `status='open'`, bằng `UPDATE … WHERE status='open'` (FR-029).

### `approval_cards` (FR-032 đến FR-037)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | String(36) PK | |
| `run_id`, `tool_call_id` | | Duy nhất trên cặp này. |
| `conversation_id` | FK | Luôn là hội thoại gốc, kể cả khi lượt chạy ở tầng sâu (FR-037). |
| `user_id` | FK users | Người dùng gốc, người duy nhất trả lời được. |
| `agent_slug`, `tool`, `arguments` | | Tham số chính xác sẽ chạy (FR-036). |
| `action_kind` | String(16) | |
| `preview` | JSON | Nội dung xem trước và đối tượng chịu tác động. |
| `choices` | JSON list | Tập con của `once`, `conversation`, `always`, `deny`, `did_it`, `dont`, tuỳ chế độ (FR-035). |
| `status` | String(16) | Một trong `open`, `allowed`, `denied`, `expired`. |
| `answer` | String(16), nullable | |
| `executed_at` | DateTime, nullable | Đặt trong cùng giao dịch với lần chạy duy nhất (FR-036). |
| `expires_at` | DateTime | Mặc định cộng 24 giờ. |

### `approval_rules` (FR-032, FR-033)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | PK | |
| `scope` | String(16) | Một trong `user`, `class`, `admin`, `conversation`. |
| `scope_id` | String(36), nullable | `user_id`, `class_id` hoặc `conversation_id`. `null` khi scope là `admin`. |
| `action_kind` | String(16) | |
| `agent_slug`, `tool`, `target` | nullable | Điều kiện khớp. `null` khớp mọi giá trị. |
| `effect` | String(8) | Một trong `allow`, `deny`, `ask`. |
| `source` | String(16) | Một trong `card`, `typed`, `admin`, `class`. Chỉ `source='card'` mở được một loại luôn phải hỏi (FR-034). |
| `created_by`, `created_at` | | |

- Rule `scope=conversation` được tạo từ lựa chọn "Cho phép trong hội thoại này" và bị xoá khi người dùng tắt.

### `approval_kind_modes` (FR-035)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `action_kind` | String(16) | Khoá chính cùng `role`. |
| `role` | String(16) | |
| `mode` | String(16) | Một trong `members_choose`, `ask_every_time`, `do_it_yourself`. |

- Seed: học sinh là `ask_every_time` cho mọi loại; giáo viên và phụ huynh là `members_choose`.

### `user_settings`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `user_id` | PK, FK users | |
| `extra_vigilant` | Boolean, mặc định `false` | FR-032 |

## 3. Quan hệ

```text
users 1─* conversations (người tạo) 1─* conversation_members *─1 users | agent_slug
conversations 1─* chat_messages
conversations 1─* agent_runs 1─* handoffs ─1 agent_runs (luồng nháp của agent được hỏi, handoff_id)
agent_runs 1─* person_requests ─1 users (recipient)
agent_runs 1─* approval_cards
chat_messages ─0..1 handoffs | person_requests | approval_cards | agent_runs
installations ─ handoff_allow ∩ agent_versions.manifest.handoff_to
```

## 4. Quy tắc kiểm tra quan trọng

- **Đích handoff hợp lệ (FR-007, FR-008, FR-012)**: tất cả các điều kiện sau đều đúng.
  - `to_agent` thuộc `effective_grants(run)`.
  - `to_agent` thuộc `available_agents(user gốc, room, role)`.
  - `to_agent` không nằm trong `run.chain`.
  - `run.depth + 1` không vượt `handoff_max_depth`.
  - `root.handoff_count` nhỏ hơn `handoff_max_per_run`.
  - `room.policy.allow_handoffs` bật.
  - `effective_grants(run)` được tính bằng `manifest.handoff_to ∩ (installation.handoff_allow or manifest.handoff_to)`.
- **Quyền xem tin (FR-047, FR-050)**: người xem là thành viên chưa rời nhóm, và `seq > joined_seq` (hoặc
  `can_see_history`), và `visible_to` là null hoặc chứa người xem.
- **Duy nhất một lần (FR-015, FR-029, FR-036)**: dùng các ràng buộc duy nhất `chat_messages.handoff_id` và
  (`run_id`, `tool_call_id`) trên ba bảng, cùng cập nhật có điều kiện trạng thái.
