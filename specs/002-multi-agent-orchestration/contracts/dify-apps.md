# Hợp đồng: các ứng dụng Dify (bổ sung cho feature 001)

Nền: [specs/001-dify-core-migration/contracts/dify-apps.md](../../001-dify-core-migration/contracts/dify-apps.md).
Fixture mới ghi vào `backend/tests/fixtures/dify/` từ Dify 1.19.0 đã ghim.

## 1. `eduagent-triage` — thêm output `path`

Thêm một nhánh LLM (model `DIFY_TRIAGE_MODEL`, nhiệt độ 0) chạy **song song** với Question Classifier an toàn, nối
vào node Code gộp cuối. Inputs không đổi.

| Output mới | Kiểu | Giá trị |
|---|---|---|
| `path` | string | `fast` \| `full`; parse lỗi hoặc trống → `fast` |

Prompt của nhánh (tóm tắt): trả `full` khi (a) yêu cầu cần ít nhất hai chuyên môn khác nhau trong `roster`, hoặc
(b) thiếu thông tin mà thiếu nó thì kết quả khác hẳn (lớp, chương, số câu, đề bài…), hoặc (c) người dùng muốn một
hành động tác động ra ngoài cuộc trò chuyện (lưu tài liệu lớp, đổi ghi chú cho agent, cài agent, đăng thông báo, giao bài luyện). Câu hỏi kiến thức, giải thích, chào
hỏi, một bài tập cụ thể đã đủ đề → `fast`. Phân vân → `fast`.

Backend bỏ qua `path` khi `verdict != "allow"`. Token của nhánh nằm trong `total_tokens` của workflow (purpose
`triage`, như cũ).

Fixture: `triage_path_full.json`, `triage_path_fast.json`.

## 2. `eduagent-planner` — mới (Workflow, blocking)

`POST /v1/workflows/run`, khóa `DIFY_PLANNER_KEY`, `response_mode="blocking"`, `user=<users.id>`,
timeout `DIFY_TIMEOUT_S`.

### Inputs

| Biến | Kiểu | Bắt buộc | Nội dung |
|---|---|---|---|
| `query` | paragraph (≤ 4000) | có | yêu cầu gốc đã ẩn thông tin cá nhân |
| `role` | select | có | `teacher` · `student` · `parent` |
| `roster` | paragraph (JSON) | có | `[{slug, name, description, capabilities, subjects, tools, is_fallback}]` — chỉ agent dùng được |
| `requested_agent` | text | không | agent người dùng chọn/`@mention`; nếu có thì phải là `lead` |
| `history` | paragraph (≤ 3000) | không | tối đa 6 tin gần nhất "Người dùng:/Trợ lý:", mỗi tin ≤ 500 ký tự |
| `resume` | paragraph (JSON) | không | khi làm tiếp: `{goal, questions:[{question, answer}], skipped: bool, done_steps:[{key, agent, title}], new_message}` |
| `interactive` | select (`true`/`false`) | có | `false` → không được trả `missing`/`confirm_interpretation` |
| `can_ask` | select (`true`/`false`) | có | `false` khi đã dùng hết lần hỏi (`clarify_rounds`) |
| `limits` | text (JSON) | có | `{"max_steps":5,"max_agents":3,"max_questions":3}` |

### Outputs (sau node Code)

| Biến | Kiểu | Nội dung |
|---|---|---|
| `ok` | string | `true` khi parse được JSON hợp lệ |
| `plan` | string (JSON) | đối tượng bên dưới |

```json
{
  "goal": "Ôn định lý Pytago theo tài liệu lớp và có một bài luyện",
  "lead": "gia-su-toan",
  "answers_pending": true,
  "missing": [{"id": "q1", "question": "Em học lớp mấy?", "options": ["7", "8", "9"], "why": "độ khó bài luyện"}],
  "assumptions": ["Bài luyện mức trung bình"],
  "confirm_interpretation": "",
  "steps": [
    {"key": "s1", "agent": "on-tap-tai-lieu", "title": "Tìm lý thuyết trong tài liệu lớp",
     "task": "Tìm phần định lý Pytago trong tài liệu lớp, tóm tắt kèm vị trí", "depends_on": []},
    {"key": "s2", "agent": "tao-de", "title": "Soạn một bài luyện",
     "task": "Soạn 1 bài luyện định lý Pytago bám phần lý thuyết ở s1, không kèm lời giải", "depends_on": ["s1"]}
  ]
}
```

- `answers_pending` chỉ có nghĩa khi có `resume.new_message`: `true` nếu tin nhắn mới là câu trả lời cho câu hỏi đang
  chờ, `false` nếu là yêu cầu khác.
- `missing` rỗng khi đủ thông tin; nếu khác rỗng thì `steps` vẫn được trả (kế hoạch dự kiến) nhưng backend dừng hỏi
  trước khi chạy.
- `confirm_interpretation`: một câu tóm tắt cách hiểu cần người dùng xác nhận, hoặc rỗng.

### Backend kiểm tra (`orchestrator/planner.py`)

| Quy tắc | Xử lý khi sai |
|---|---|
| `ok == "true"` và JSON đúng dạng | quay về đường nhanh (FR-006) |
| `lead` thuộc `roster`; bằng `requested_agent` nếu có | đặt `requested_agent`, hoặc agent `is_fallback`, hoặc agent đầu tiên |
| mỗi `steps[].agent` thuộc `roster` | đổi thành `lead` (FR-039) |
| `key` duy nhất, `depends_on` trỏ tới key có thật, không vòng | bỏ phụ thuộc lỗi; còn vòng → quay về đường nhanh |
| ≤ `max_steps` phần việc, ≤ `max_agents` agent (tính cả `lead`) | cắt phần việc cuối theo thứ tự topo |
| `missing` ≤ `max_questions`, mỗi câu ≤ 200 ký tự, ≤ 6 lựa chọn | cắt |
| `interactive=false` hoặc `can_ask=false` | `missing` và `confirm_interpretation` chuyển thành `assumptions` |
| `steps` rỗng | một phần việc mặc định cho `lead` với `task = goal` |
| `title` ≤ 80 ký tự, không chứa từ khóa kiểm duyệt | cắt; trúng từ khóa → "Phần việc của <tên agent>" |

Usage: `data.total_tokens` → purpose `planner`, `path="full"`.

Fixture: `planner_multi.json`, `planner_missing.json`, `planner_bad_slug.json`, `planner_invalid.json`,
`planner_resume_answer.json`, `planner_resume_new_topic.json`.

## 3. `eduagent-runner` và `eduagent-runner-raw` — bật tool tín hiệu

Inputs không đổi (`system_prompt`, `ctx`, `safety_note`). Thay đổi DSL:

- Bật thêm `request_help`, `ask_user`, `request_confirmation` từ MCP provider `eduagent-tools`, tham số `ctx` ở chế độ
  Fixed Value như 5 tool cũ ([mcp-tools.md](mcp-tools.md)).
- Tăng số vòng tối đa của agent node từ 5 lên 6 (một vòng dành cho tool tín hiệu).

Cách backend dùng runner:

| Lần gọi | `conversation_id` | `system_prompt` | `query` | Stream |
|---|---|---|---|---|
| Đường nhanh | hội thoại chính | như 001 | tin nhắn | chuyển cho người dùng |
| Phần việc | `""` (mới) | `build_system_prompt(agent_của_phần_việc)` + khối `STEP_MODE` | mục tiêu + phần việc + ghi chú phụ thuộc + yêu cầu gốc | backend đọc hết, không chuyển |
| Tổng hợp | hội thoại chính | `build_system_prompt(lead)` + khối `SYNTHESIS_MODE` (ghi chú làm việc, giả định, phần chưa làm được, kết quả xác nhận) | yêu cầu gốc + "Thông tin bổ sung" (câu hỏi/câu trả lời) | chuyển cho người dùng |

`system_prompt` vẫn ≤ 12000 ký tự: ghi chú trong khối tổng hợp mỗi phần ≤ `floor(6000 / số phần việc)` ký tự.

Usage: phần việc → purpose `step`; tổng hợp → `synthesis`; mọi dòng `path="full"`.

Fixture: `runner_step_note.sse`, `runner_step_signal.sse` (có lời gọi `ask_user`), `runner_step_replaced.sse`.

## 4. `eduagent-review` — dùng lại cho ghi chú làm việc

Không đổi DSL. Gọi với `question` = yêu cầu gốc, `reply` = ghi chú (≤ 12000), `role` và `no_direct_answers` của
người xem và lớp. Với giáo viên, giữ đúng quy tắc của 001: không gọi review (giáo viên được xem đáp án theo thiết
kế), chỉ qua kiểm duyệt từ khóa; đó chính là "kiểm duyệt đầu ra áp dụng cho vai trò" mà FR-034 yêu cầu. Usage:
purpose `note_review`, `path="full"`.
