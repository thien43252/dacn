# Hợp đồng: MCP tools (bổ sung cho feature 001)

Nền: [specs/001-dify-core-migration/contracts/mcp-tools.md](../../001-dify-core-migration/contracts/mcp-tools.md).
URL, transport, xác thực và 6 bước kiểm tra trong handler giữ nguyên.

## Tool tín hiệu (mới)

Thuộc registry với `signal=True`. Không cần khai báo trong manifest agent: mọi agent đều được dùng **khi và chỉ khi**
handle ở chế độ `step`. Handler không chờ gì: ghi tín hiệu vào `ToolContext.signals`, ghi `tool_calls`, phát sự kiện
`tool` có `step_key`, rồi trả ngay câu xác nhận.

| Tool | Tham số (sau `ctx`) | Kiểm tra | Trả về cho agent |
|---|---|---|---|
| `request_help` | `agent: str` (slug, có thể rỗng), `task: str` (10–1000 ký tự) | `ctx.may_request_help` (false ở phần việc `origin="help"`) | "Đã ghi nhận yêu cầu hỗ trợ. Hãy kết thúc phần việc với những gì đã có; hệ thống sẽ gửi lại kết quả." |
| `ask_user` | `questions: [{question: str ≤ 200, options: str[] ≤ 6}]` (1–3 câu) | — | "Đã ghi nhận câu hỏi. Hãy kết thúc phần việc; nếu không hỏi được, hệ thống sẽ ghi giả định." |
| `request_confirmation` | `summary: str` (10–400 ký tự) | — | như `ask_user` |

Bổ sung vào bảng kiểm tra trong handler, sau bước 2:

| # | Điều kiện | Kết quả khi sai |
|---|---|---|
| 2a | tool có `signal=True` thì handle phải ở `mode="step"` | từ chối với lý do "Công cụ này chỉ dùng trong phần việc của quá trình nhiều bước." (stage `tool`, category `tool_denied`) |
| 2b | tool không có `signal=True` thì phải có trong manifest (bước 3 cũ) | như cũ |

Backend xử lý tín hiệu sau khi phần việc kết thúc ([research.md](../research.md) R5): chỉ tín hiệu đầu tiên của mỗi
loại trong một phần việc được dùng; slug trong `request_help` không thuộc danh sách agent → backend tự chọn theo
`task`, không có agent nào phù hợp → ghi vào ghi chú "ngoài khả năng của các agent trong lớp" (User Story 5 kịch
bản 2).

## Tool cần xác nhận

`PlatformTool.requires_confirmation=True`. Bước mới sau bước 6 (tham số hợp lệ):

| # | Điều kiện | Kết quả |
|---|---|---|
| 7 | tool cần xác nhận | **không chạy**; ghi `tool_calls` với `denied_reason="awaiting_confirmation"`; thêm tín hiệu `{type: "confirm_tool", tool, args, summary}` (summary dựng từ `confirm_template` + tham số); trả "Cần người dùng xác nhận trước khi thực hiện; hệ thống sẽ hỏi. Hãy kết thúc phần việc." |

Ở mọi chế độ (`fast`, `step`, `synthesis`) quy tắc 7 đều áp dụng. Sau khi người dùng bấm "Đồng ý", backend gọi trực
tiếp `IMPLEMENTATIONS[tool](context, args)` với `args` đã lưu (không qua MCP, không qua agent), ghi `tool_calls` bình
thường.

### `confirm_probe` (chỉ khi `ENABLE_TEST_TOOLS=true`)

| Trường | Giá trị |
|---|---|
| Tham số | `target: str` (≤ 100), `note: str` (≤ 300) |
| Vai trò | `teacher`, `student`, `parent` |
| `requires_confirmation` | true |
| `confirm_template` | "Ghi một thông báo thử tới “{target}”: {note}" |
| Tác dụng | trả `{"ok": true, "target": …}`; không làm gì khác |

Không có trong DSL runner phát hành. Test và eval đăng ký tool này qua handle (manifest agent thử nghiệm có
`tools: [confirm_probe]`).

## Tool cần xác nhận cho giáo viên (R18, FR-047)

Chung cho cả 5 tool: `roles={"teacher"}`, `needs_class=True`, `requires_confirmation=True`. Phải được khai báo trong
manifest của agent (bước 3 của handler). Ngoài 6 bước cũ, handler kiểm tra thêm:

| # | Điều kiện | Khi sai |
|---|---|---|
| 6a | người dùng là giáo viên của `class_id` trong handle (không chỉ có vai trò `teacher`) | từ chối, `tool_denied` |
| 6b | kiểm duyệt nội dung chia sẻ (FR-049): từ khóa cho mọi trường văn bản; thêm `eduagent-review` (`role="student"`, `no_direct_answers="false"`: giáo viên được chủ động chia sẻ lời giải, chỉ chặn nội dung không an toàn, lộ thông tin cá nhân hay chứa chỉ dẫn chèn vào) với tool có `share_review` | lỗi tool "Nội dung không phù hợp để chia sẻ: <lý do>"; `guard_events` stage `tool`, category `share_blocked`; **không** tạo yêu cầu xác nhận |

Sau đó áp dụng bước 7 (chưa chạy, tạo yêu cầu xác nhận kèm `preview`).

| Tool | Tham số (sau `ctx`) | `share_review` | Xem trước (FR-048) | Khi chạy | `result_ref` |
|---|---|---|---|---|---|
| `save_class_document` | `title: str` (3–120), `content: str` (Markdown, 20–20000) | có | "Lưu “{title}” vào tài liệu lớp {class}. Học sinh và các agent của lớp sẽ đọc được." + 600 ký tự đầu | tạo `Document` `.md` từ `content`, chạy `process_document` (đồng bộ Dify) như khi tải lên | `document_id` |
| `set_agent_notes` | `notes: str` (≤ 1000), `mode: "replace" \| "append"` | không (chỉ từ khóa) | "Đổi ghi chú cho mọi agent của lớp {class}." + ghi chú cũ → ghi chú mới | ghi `policy.notes_for_agents`; không chạm khóa nào khác của `policy` | `class_id` |
| `install_agent` | `agent: str` (slug trên Hub) | không | "Cài agent “{name}” vào lớp {class}; {n} học sinh sẽ dùng được." + mô tả agent | dùng hàm service tách từ `install_in_class` (cùng quy tắc chứng nhận/hiển thị); đã cài → kết quả "đã có sẵn", không lỗi | `installation_id` |
| `post_class_announcement` | `title: str` (3–120), `body: str` (10–2000), `audience: "students" \| "parents" \| "all"` | có | "Đăng thông báo “{title}” tới {nhóm} lớp {class} ({n} người)." + nội dung | tạo `class_announcements` (`source="agent"`) | `announcement_id` |
| `assign_practice` | `title: str` (3–120), `instructions: str` (≤ 1000), `questions: [{question, options?}]` (1–20), `answer_key?: [{index, answer, explanation?}]`, `due_at?: ISO 8601` | có (không gửi `answer_key` đi review) | "Giao bài “{title}” ({k} câu) cho {n} học sinh lớp {class}, hạn {due \| “không có hạn”}." + danh sách câu hỏi | tạo `assignments` (`source="agent"`) | `assignment_id` |

Kết quả trả cho agent ở bước tổng hợp (sau khi chạy): `{"done": true, "summary": "...", "link": "/classes/{id}?tab=..."}`;
khi bị từ chối, hết hạn hoặc huỷ: `{"done": false, "reason": "user_rejected" | "expired" | "cancelled"}`.

Agent ở chế độ kiểm định (`source="certify"`): bước 7 vẫn chạy (không có tác dụng), yêu cầu xác nhận được coi là "Không"
ngay (FR-041).
