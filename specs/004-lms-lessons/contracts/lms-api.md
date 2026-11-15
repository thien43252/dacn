# Hợp đồng API: feature 004 (LMS)

Tiền tố `/api`, xác thực bằng cookie phiên hiện có, lỗi theo dạng `{"detail": "<thông báo tiếng Việt>"}`. Cột **Vai trò**
là vai trò trong lớp (`classes.load_class`): `T` giáo viên (chủ lớp, đồng dạy; admin đi như giáo viên), `S` học sinh,
`P` phụ huynh của học sinh trong lớp. Mã lỗi chung: 404 không thuộc lớp, 403 sai vai trò, 409 lớp đã lưu trữ hoặc sai
trạng thái, 413/415 tệp, 422 dữ liệu sai hoặc bị guard chặn.

## Buổi học và mục nội dung

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/classes/{cid}/lessons` | T S P | Danh sách buổi. T thấy mọi trạng thái; S/P chỉ `published`, buổi chưa tới `publish_at` có `locked: true` và không có `items` |
| POST | `/classes/{cid}/lessons` | T | Tạo buổi `{title, description?, lesson_date?, publish_at?}` → `draft` |
| GET | `/classes/{cid}/lessons/{lid}` | T S P | Chi tiết buổi kèm `items` đã lọc theo quyền; S/P kèm `viewed` từng mục |
| PATCH | `/classes/{cid}/lessons/{lid}` | T | Sửa trường; `status: published\|draft\|archived` |
| DELETE | `/classes/{cid}/lessons/{lid}` | T | Buổi chưa có bài nộp/lượt làm → xóa; có → 409 kèm gợi ý lưu trữ |
| PUT | `/classes/{cid}/lessons/order` | T | `{ids: [...]}` đầy đủ |
| POST | `/classes/{cid}/lessons/{lid}/items` | T | Tạo mục `{kind, title, body?, url?, file_id?}`; `kind=quiz\|assignment` tạo kèm cấu hình mặc định |
| PATCH | `/classes/{cid}/items/{iid}` | T | Sửa mục, `visible`, `agent_readable: bool` (R3) |
| DELETE | `/classes/{cid}/items/{iid}` | T | Như DELETE buổi |
| PUT | `/classes/{cid}/lessons/{lid}/items/order` | T | `{ids: [...]}` |
| POST | `/classes/{cid}/items/{iid}/view` | S | Ghi `content_views` (idempotent) |
| GET | `/classes/{cid}/items/{iid}/views` | T | Học sinh đã xem/chưa xem |

## Tệp

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| POST | `/classes/{cid}/files` | T S | multipart `file`, `purpose` (`content\|prompt` chỉ T; `submission` chỉ S) → `{id, filename, content_type, size_bytes}` |
| GET | `/classes/{cid}/files/{fid}` | theo R2 | Trả tệp; hỗ trợ `Range`; `?download=1` đặt `Content-Disposition: attachment` |

## Quiz / bài kiểm tra

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/classes/{cid}/quizzes/{qid}` | T S P | T: cấu hình + câu hỏi đầy đủ đáp án. S/P: `QuizStudentView` (cấu hình công khai, số câu, tổng điểm, trạng thái mở/đóng, các lượt của học sinh) — **không bao giờ** có `answer_key`, `explanation`, `rubric` |
| PATCH | `/classes/{cid}/quizzes/{qid}` | T | Cấu hình (data-model `quizzes`) |
| POST | `/classes/{cid}/quizzes/{qid}/questions` | T | Thêm câu |
| PATCH/DELETE | `/classes/{cid}/questions/{questionId}` | T | Sửa/xóa câu; response nêu `affects_submitted: n` nếu đã có bài nộp |
| PUT | `/classes/{cid}/quizzes/{qid}/questions/order` | T | `{ids}` |
| POST | `/classes/{cid}/questions/{questionId}/regrade` | T | Chấm lại mọi lượt đã nộp theo đáp án hiện tại → `{updated: n}` |
| POST | `/classes/{cid}/quizzes/{qid}/attempts` | S | Bắt đầu hoặc tiếp tục lượt → `AttemptView {id, attempt_no, deadline_at, server_now, questions(snapshot, không đáp án), answers}`. 409 khi hết lượt / chưa mở / đã đóng |
| GET | `/classes/{cid}/attempts/{aid}` | S(chủ) P(con) T | Đang làm: như trên. Đã nộp: kèm điểm/đáp án theo `show_score`/`show_answers` (với S/P) |
| PUT | `/classes/{cid}/attempts/{aid}/answers` | S(chủ) | `{question_id, value}` → `{saved_at}`; 409 `attempt_closed` khi quá `deadline_at` hoặc đã nộp |
| POST | `/classes/{cid}/attempts/{aid}/submit` | S(chủ) | Nộp → kết quả theo quyền xem |
| GET | `/classes/{cid}/quizzes/{qid}/results` | T | Danh sách lượt, thống kê (FR-016): số đã làm, trung bình, phân bố, tỉ lệ đúng từng câu |
| PUT | `/classes/{cid}/attempts/{aid}/scores/{questionId}` | T | Chấm câu tự luận `{points, feedback}`; ghi `grade_audit` |
| POST | `/classes/{cid}/quizzes/{qid}/copy` | T | `{target_lesson_id}` (lớp khác của chính giáo viên được phép) (FR-017) |

## Bài tập

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/classes/{cid}/assignments/{asg}` | T S P | T: cấu hình + thống kê nộp. S: đề, hạn hiệu lực của em, bài nộp của em (điểm chỉ khi `returned`). P: như S, chỉ đọc, `?student_id=` là con |
| PATCH | `/classes/{cid}/assignments/{asg}` | T | Cấu hình (data-model `assignments`) |
| PUT | `/classes/{cid}/assignments/{asg}/extensions/{studentId}` | T | `{due_at}` hoặc DELETE để bỏ |
| POST | `/classes/{cid}/assignments/{asg}/submissions` | S | `{text?, file_ids?}` → phiên bản mới; 409 `past_due` khi quá hạn và không cho nộp muộn |
| GET | `/classes/{cid}/assignments/{asg}/submissions` | T | Danh sách học sinh × trạng thái (đã nộp, muộn, chưa nộp) |
| GET | `/classes/{cid}/submissions/{sid}` | T, S(chủ), P(con) | Chi tiết + các phiên bản; S/P không thấy điểm trước khi trả |
| PUT | `/classes/{cid}/submissions/{sid}/grade` | T | `{raw_score, feedback, penalty_waived?}` → tính `penalty`, `final_score` (R12) |
| POST | `/classes/{cid}/assignments/{asg}/return` | T | `{submission_ids?}` (trống = mọi bài đã chấm) → `returned` + thông báo |

## Trợ lý AI cho giáo viên (agent Hub)

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/classes/{cid}/assist/agents` | T | Agent đủ điều kiện trong lớp, theo `capability: questions\|grading`; rỗng → UI hiện hướng dẫn cài từ Hub |
| POST | `/classes/{cid}/quizzes/{qid}/suggest-questions` | T | `{agent_slug?, count, kinds[], level, document_ids?}` → `AISuggestion(status=pending)` |
| POST | `/classes/{cid}/suggest-grading` | T | `{targets: [{type: submission\|attempt_question, id}], agent_slug?}` → danh sách suggestion; học sinh chưa có đồng ý → `skipped_consent` (FR-037) |
| GET | `/classes/{cid}/suggestions/{sgid}` | T | Trạng thái và payload |
| POST | `/classes/{cid}/suggestions/{sgid}/review` | T | Câu hỏi: `{decisions: [{index, action: approve\|edit\|discard, question?}]}` → tạo `quiz_questions` cho mục duyệt. Chấm: `{action: approve\|edit\|discard, points?, feedback?}` → ghi điểm như giáo viên chấm (chưa trả bài) |

Học sinh và phụ huynh không có endpoint nào trả `ai_suggestions`.

## Sổ điểm, việc cần làm, thông báo

| Method | Path | Vai trò | Mô tả |
|---|---|---|---|
| GET | `/classes/{cid}/gradebook` | T | `{columns:[{item_id, kind, title, max_points, weight, counts}], rows:[{student, cells:[{state, score, final}], average}]}`; `state`: `not_assigned\|missing\|in_progress\|pending\|graded\|returned` |
| GET | `/classes/{cid}/gradebook.csv` | T | CSV UTF-8 có BOM |
| GET | `/classes/{cid}/my-grades` | S, P(`?student_id=`) | Điểm đã trả của một học sinh trong lớp |
| GET | `/todo` | S, P(`?student_id=`) | Việc chưa hoàn thành của mọi lớp, sắp theo hạn |
| GET | `/notifications` | mọi người | `?unread=1`; `{items, unread_count}` |
| POST | `/notifications/read` | mọi người | `{ids?}` (trống = tất cả) |
| GET | `/classes/{cid}/grade-audit` | T | Nhật ký thao tác điểm, lọc theo học sinh/bài |

## Hợp đồng runtime: chặn đáp án khi làm bài (FR-028)

Không phải endpoint; là hành vi của `runtime/graph.py` mà test kiểm:

- Đầu vào: tin nhắn của học sinh có lượt `in_progress` của quiz `block_agents = true`, khớp stem câu hỏi → không gọi
  agent, trả notice `kind: "guard_blocked"` với văn bản `EXAM_BLOCKED`, ghi `GuardEvent(stage="input",
  category="exam_integrity", private_space=true)`.
- Đầu ra: câu trả lời (kể cả câu trả lời từ handoff) gửi tới hội thoại có học sinh đang làm bài, nếu chứa đáp án hoặc
  lời giải của câu trong bài → `text_reset` + `EXAM_BLOCKED`, ghi `GuardEvent(stage="output", ...)`.
- Sự kiện này không xuất hiện trong `GET /classes/{cid}/audit` của giáo viên và không trong báo cáo phụ huynh; admin thấy
  qua `/audit/events` không kèm `excerpt`.
- Khi `block_agents = false` hoặc lượt đã nộp/hết hạn: không chặn vì lý do bài kiểm tra.
