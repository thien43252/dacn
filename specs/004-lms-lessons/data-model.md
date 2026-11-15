# Data Model: feature 004 (LMS)

Migration mới: `backend/migrations/versions/0007_lms.py`. Khóa chính `String(36)` sinh bằng `new_id`, thời gian
`DateTime(timezone=True)`, theo quy ước của `main`. Mọi bảng có `class_id` để lọc quyền nhanh (khử chuẩn có chủ đích).

## Sơ đồ quan hệ

```text
classes 1─* lessons 1─* lesson_items ─┬─1 quizzes 1─* quiz_questions
                                      │             1─* quiz_attempts (student)
                                      ├─1 assignments 1─* assignment_extensions (student)
                                      │               1─* submissions (student) 1─* submission_versions
                                      ├─? lms_files
                                      └─? documents (kho tri thức hiện có, khi "cho agent đọc")
lesson_items 1─* content_views (student)
ai_suggestions ─> quiz (gợi ý câu hỏi) | submission | quiz_attempt (gợi ý chấm)
notifications ─> users ;  grade_audit ─> classes, users
```

## lessons

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| class_id | FK classes, cascade | index |
| title | str(200) | bắt buộc, qua guard |
| description | text | mặc định "" |
| lesson_date | date? | ngày học, tùy chọn |
| position | int | thứ tự trong lớp |
| status | str(16) | `draft` → `published` → `archived`; `archived` → `draft` (khôi phục) |
| publish_at | datetime? | null = mở ngay khi `published` |
| created_by | FK users | |
| created_at, updated_at | datetime | `TimestampMixin` |

Quy tắc: học sinh/phụ huynh thấy khi `status = published`; thấy nội dung khi `publish_at` null hoặc ≤ now. Lưu trữ buổi
có bài nộp: giữ mọi dữ liệu con, ẩn với học sinh, các cột điểm vẫn trong sổ điểm (đánh dấu "đã lưu trữ").

## lesson_items

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| lesson_id | FK lessons, cascade | index |
| class_id | FK classes | |
| kind | str(16) | `file` \| `video` \| `link` \| `text` \| `assignment` \| `quiz` |
| title | str(200) | |
| position | int | thứ tự trong buổi |
| body | text | nội dung `text`, mô tả ngắn cho loại khác |
| url | str(1000)? | `video` bằng link, `link` |
| embed_url | str(1000)? | URL nhúng đã chuẩn hóa (R4) |
| file_id | FK lms_files? | `file`, `video` tải lên |
| document_id | FK documents?, set null | bật "cho agent đọc" (R3) |
| visible | bool | mặc định true; ẩn từng mục trong buổi đã công bố |
| created_at | datetime | |

Ràng buộc: `kind=video` cần đúng một trong `url`/`file_id`; `kind=file` cần `file_id`; `kind=link` cần `url`.

## lms_files

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| class_id | FK classes, cascade | |
| owner_id | FK users | người tải |
| purpose | str(16) | `content` \| `prompt` (đề bài) \| `submission` |
| filename | str(255) | tên hiển thị (không dùng làm đường dẫn) |
| content_type | str(100) | theo whitelist (R2) |
| size_bytes | int | ≤ 25 MB, video ≤ 200 MB |
| storage_path | str(500) | `uploads/lms/<class_id>/<id><ext>` |
| created_at | datetime | |

Quyền tải: tệp `content`/`prompt` → thành viên lớp và phụ huynh của học sinh trong lớp (khi mục hiển thị với họ); tệp
`submission` → học sinh chủ bài, phụ huynh của em, giáo viên lớp.

## quizzes (1–1 với lesson_items kind=quiz)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| item_id | PK, FK lesson_items, cascade | |
| class_id | FK classes | |
| open_at, close_at | datetime? | null = mở ngay / không đóng |
| duration_minutes | int? | null = không giới hạn |
| max_attempts | int | mặc định 1; 0 = không giới hạn |
| scoring_policy | str(8) | `best` \| `last` \| `average` |
| shuffle_questions, shuffle_options | bool | |
| show_score | str(12) | `on_submit` \| `after_close` \| `never` |
| show_answers | str(12) | `on_submit` \| `after_close` \| `never` |
| block_agents | bool | mặc định true (FR-028) |
| ai_grading | bool | mặc định true (FR-036) |
| weight | float | mặc định 1 |
| counts_in_grade | bool | mặc định true |

Không cho công bố quiz không có câu hỏi. `max_points` = tổng điểm các câu (tính khi đọc).

## quiz_questions

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| quiz_id | FK quizzes, cascade | |
| position | int | |
| kind | str(12) | `single` \| `multi` \| `true_false` \| `short` \| `essay` |
| prompt | text | qua guard |
| options | JSON | `[{id, text}]` cho single/multi; id ổn định khi sửa/trộn |
| answer_key | JSON | single: `option_id`; multi: `[option_id]`; true_false: bool; short: `[chuỗi chấp nhận]`; essay: null |
| multi_scoring | str(16) | `all_or_nothing` \| `partial` (chỉ `multi`) |
| points | float | > 0 |
| explanation | text | lời giải, chỉ hiện khi `show_answers` cho phép |
| rubric | JSON? | essay: `{criteria:[{name, max_points, description}], model_answer}` |
| source | str(8) | `manual` \| `ai` |
| ai_suggestion_id | FK ai_suggestions? | khi câu đến từ gợi ý đã duyệt (FR-032) |

## quiz_attempts

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| quiz_id | FK quizzes, cascade | |
| class_id | FK classes | |
| student_id | FK users | |
| attempt_no | int | unique `(quiz_id, student_id, attempt_no)` |
| status | str(12) | `in_progress` → `submitted` (chờ chấm tự luận) → `graded` |
| started_at | datetime | giờ server |
| deadline_at | datetime? | `min(started_at + duration, close_at)` |
| submitted_at | datetime? | |
| submit_reason | str(8)? | `manual` \| `timeout` \| `closed` |
| snapshot | JSON | đề lúc bắt đầu: `[{question_id, kind, prompt, options(đã trộn), points}]`, không chứa đáp án |
| answers | JSON | `{question_id: giá trị}`; chỉ ghi khi `in_progress` và now ≤ deadline |
| item_scores | JSON | `{question_id: {points, graded_by: auto\|<user_id>, feedback}}` |
| score | float? | tổng khi mọi câu đã chấm |
| max_score | float | tổng điểm theo snapshot |

Chuyển trạng thái: nộp (tay/hết giờ/đóng) → chấm tự động câu khách quan → `graded` nếu không có tự luận, ngược lại
`submitted`; giáo viên chấm hết tự luận → `graded`. Chấm lại (R5) đổi `item_scores`/`score`, ghi `grade_audit`.

## assignments (1–1 với lesson_items kind=assignment)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| item_id | PK, FK lesson_items, cascade | |
| class_id | FK classes | |
| prompt | text | đề bài, qua guard |
| prompt_file_ids | JSON | `[lms_files.id]` purpose `prompt` |
| due_at | datetime? | |
| max_points | float | mặc định 10 |
| allow_late | bool | mặc định true |
| late_penalty_per_day_pct | float | 0–100, mặc định 0 (FR-020a) |
| late_penalty_max_pct | float | 0–100, mặc định 0 |
| rubric | JSON? | thang chấm + đáp án mẫu (FR-033) |
| ai_grading | bool | mặc định true |
| weight | float | mặc định 1 |
| counts_in_grade | bool | mặc định true |

## assignment_extensions

`(assignment_id, student_id)` unique, `due_at`, `granted_by`, `created_at`. Hạn riêng thay hạn chung (FR-021).

## submissions

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| assignment_id | FK assignments, cascade | unique `(assignment_id, student_id)` |
| class_id | FK classes | |
| student_id | FK users | |
| status | str(12) | `submitted` → `graded` → `returned`; nộp lại khi `returned` mở lại `submitted` nếu còn hạn |
| latest_version | int | |
| is_late | bool | theo phiên bản mới nhất |
| days_late | int | |
| raw_score | float? | giáo viên chấm |
| penalty | float | tính theo R12 |
| penalty_waived | bool | |
| final_score | float? | `max(0, raw − penalty)` hoặc `raw` khi bỏ trừ |
| feedback | text | |
| graded_by, graded_at, returned_at | | |

Học sinh/phụ huynh chỉ thấy `raw_score`, `penalty`, `final_score`, `feedback` khi `status = returned`.

## submission_versions

`id`, `submission_id`, `version_no`, `text`, `file_ids` (JSON), `submitted_at`, `is_late`. Không sửa, không xóa.

## ai_suggestions

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| class_id | FK classes | |
| kind | str(16) | `questions` \| `grading` |
| target_type | str(16) | `quiz` \| `submission` \| `attempt_question` |
| target_id | str | |
| agent_id, agent_version_id | FK | agent Hub đã tạo gợi ý (FR-038) |
| request | JSON | tham số: loại câu, số câu, độ khó, document_ids; hoặc question_id |
| status | str(16) | `pending` → `ready` \| `failed` \| `skipped_consent`; `ready` → `approved` \| `edited` \| `discarded` |
| payload | JSON | câu hỏi gợi ý (kèm đáp án, giải thích, `source`) hoặc `{points, criteria:[{name, points, reason}], feedback}` |
| final | JSON? | giá trị giáo viên chốt (để đo độ lệch SC-010) |
| error | str(300)? | lý do không tạo được gợi ý |
| requested_by, reviewed_by | FK users | |
| created_at, reviewed_at | datetime | |

Gợi ý chấm không bao giờ được trả qua endpoint của học sinh/phụ huynh và không đọc bởi sổ điểm (FR-034). Gỡ agent không
xóa hàng ở đây.

## content_views

`(item_id, student_id)` unique, `first_viewed_at`, `last_viewed_at`. Ghi khi học sinh mở mục (FR-007).

## notifications

| Trường | Kiểu | Ghi chú |
|---|---|---|
| id | str | |
| user_id | FK users, cascade | index |
| kind | str(24) | `lesson_published` \| `assigned` \| `due_soon` \| `returned` \| `to_grade` \| `ai_ready` |
| class_id | FK classes? | |
| title | str(200) | |
| link | str(300) | đường dẫn trong web |
| dedupe_key | str(120) | unique, tạo lặp lại an toàn |
| read_at | datetime? | |
| created_at | datetime | |

## grade_audit

`id`, `class_id`, `actor_id`, `action` (`grade` \| `regrade` \| `edit_score` \| `waive_penalty` \| `extend` \|
`return` \| `delete_submission` \| `ai_approve`), `target_type`, `target_id`, `student_id?`, `before` (JSON), `after`
(JSON), `created_at`.

## Thay đổi ở bảng/code hiện có

- `documents`: không đổi schema; thêm `meta.lesson_item_id` để tab Tài liệu ghi nguồn "từ buổi học".
- `knowledge.service.search`: thêm tham số `document_ids: list[str] | None`.
- `tools.impl.QuizArgs`: thêm `document_ids`, `question_types`; output thêm `source` mỗi câu.
- `tools.impl.RubricArgs`: nhận `rubric` có cấu trúc và `max_points`.
- `guard_events`: không đổi schema; dùng `category = "exam_integrity"`.
