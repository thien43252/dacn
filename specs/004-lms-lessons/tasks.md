---

description: "Danh sách task triển khai feature 004: buổi học, tài liệu, video, bài tập, quiz/bài kiểm tra (LMS)"
---

# Tasks: Buổi học, tài liệu, video, bài tập và bài kiểm tra trong lớp (LMS)

**Input**: tài liệu thiết kế trong `specs/004-lms-lessons/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/lms-api.md](contracts/lms-api.md), [quickstart.md](quickstart.md)

**Tests**: có task test. Success Criteria của spec đòi kiểm chứng định lượng (SC-003 đến SC-011), plan đã liệt kê các
file test, và dự án luôn chạy `pytest` và `vitest` trước khi coi việc là xong. Test dùng LLM và embedder `fake`, cùng
fixture `client`, `as_user`, `drain` trong `backend/tests/conftest.py` và helper `class_with_student`, `install`, `chat`
trong `backend/tests/helpers.py`. Mọi chỗ đọc giờ hiện tại trong `app/lms` đi qua một hàm `now()` duy nhất để test patch
được.

**Organization**: task được nhóm theo user story để làm và kiểm tra từng story độc lập.

**Hiến pháp**: không task nào được chạy `git commit`/`push` (nguyên tắc II). Mọi chuỗi giao diện và thông báo lỗi viết
tiếng Việt (nguyên tắc I).

## Format: `[ID] [P?] [Story] Mô tả`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong).
- **[Story]**: user story của task (US1 đến US6, theo spec.md).
- Đường dẫn tính từ gốc repo: `backend/app/…`, `backend/tests/…`, `web/src/…`.

---

## Phase 1: Setup (hạ tầng chung)

**Mục đích**: tạo khung package, cấu hình, khung web.

- [X] T001 Tạo package `backend/app/lms/` gồm `__init__.py` và các file rỗng có docstring: `models.py`, `schemas.py`, `access.py`, `files.py`, `lessons.py`, `quizzes.py`, `grading.py`, `assignments.py`, `gradebook.py`, `integrity.py`, `assist.py`, `notify.py`, `jobs.py`. Thêm hàm `now() -> datetime` (UTC, timezone-aware) vào `backend/app/lms/__init__.py`
- [X] T002 [P] Thêm `lms_max_file_mb: int = 25` và `lms_max_video_mb: int = 200` vào `Settings` trong `backend/app/config.py`; thêm hai biến tùy chọn `LMS_MAX_FILE_MB`, `LMS_MAX_VIDEO_MB` (đã comment, ghi giá trị mặc định) vào `.env.example`
- [X] T003 [P] Tạo khung web: `web/src/api-client/lms.ts` (khai báo kiểu TypeScript theo [contracts/lms-api.md](contracts/lms-api.md), dùng `http.ts` hiện có), thư mục `web/src/features/lms/` với `lms.css` rỗng

---

## Phase 2: Foundational (điều kiện tiên quyết cho mọi story)

**Mục đích**: schema, quyền, tệp, thông báo, móc router và worker. **Chưa xong phase này thì không làm story nào.**

- [X] T004 Viết toàn bộ model SQLAlchemy trong `backend/app/lms/models.py` theo [data-model.md](data-model.md): `Lesson`, `LessonItem`, `LmsFile`, `Quiz`, `QuizQuestion`, `QuizAttempt`, `Assignment`, `AssignmentExtension`, `Submission`, `SubmissionVersion`, `AISuggestion`, `ContentView`, `Notification`, `GradeAudit`. Giữ đúng các ràng buộc sau:
  - `lessons.status` thuộc "`draft` → `published` → `archived`".
  - `lesson_items.kind` là "`file` \| `video` \| `link` \| `text` \| `assignment` \| `quiz`".
  - unique `(quiz_id, student_id, attempt_no)`, `(assignment_id, student_id)`, `(item_id, student_id)` của `content_views`, `(assignment_id, student_id)` của extensions, và `notifications.dedupe_key`.
  - `quizzes.max_attempts` "mặc định 1; 0 = không giới hạn".
  - `assignments.max_points` "mặc định 10".
  - `late_penalty_per_day_pct`/`late_penalty_max_pct` "0–100, mặc định 0".
  - `block_agents`/`ai_grading` "mặc định true", `weight` mặc định 1.

  Import module trong `backend/app/models.py` để metadata thấy bảng.
- [X] T005 Viết migration `backend/migrations/versions/0007_lms.py` (down_revision = revision của `0006_groups_handoffs_approvals.py`) tạo đủ 14 bảng, index trên mọi `class_id`, `lesson_id`, `quiz_id`, `student_id`, `user_id`; kèm `downgrade()`. Chạy `uv run alembic upgrade head` trên Postgres dev để kiểm
- [X] T006 [P] Viết `backend/app/lms/access.py`:
  - `load_lms_class(db, class_id, user, roles)` bọc `classes.load_class` và trả 409 "Lớp đã lưu trữ, chỉ xem được." cho thao tác ghi khi `room.archived`.
  - `resolve_student(db, user, role, student_id)`: học sinh luôn bị ép `student_id = user.id`, phụ huynh phải có `student_id ∈ children_of(user)` nếu không thì 404, giáo viên nhận mọi học sinh của lớp.
  - `is_teacher(role)`.

  Tất cả theo R15.
- [X] T007 [P] Viết `backend/app/lms/files.py`:
  - Whitelist định dạng theo R2: pdf, docx, pptx, xlsx, txt, md, png, jpg, webp, mp4, webm, mp3, zip.
  - `save_upload(db, room, owner, upload, purpose)` ghi theo khúc 1 MB vào `storage_root()/lms/<class_id>/<id><ext>`. Vượt `lms_max_file_mb` (video: `lms_max_video_mb`) thì xóa phần đã ghi, trả 413 "Tệp vượt quá N MB.". Sai định dạng trả 415 kèm danh sách định dạng nhận. Tệp rỗng trả 400.
  - Router `POST /classes/{cid}/files`: `purpose` `content|prompt` chỉ giáo viên, `submission` chỉ học sinh.
  - Router `GET /classes/{cid}/files/{fid}` trả `FileResponse` (hỗ trợ `Range`), `?download=1` thì trả `attachment`. Quyền theo mục "Quyền tải" của data-model.
- [X] T008 [P] Viết `backend/app/lms/notify.py`:
  - `notify(db, user_ids, kind, title, link, class_id, dedupe_key)`: bỏ qua khi `dedupe_key` đã tồn tại, an toàn trên cả SQLite và Postgres.
  - Router `GET /notifications` (`?unread=1`, trả `{items, unread_count}`) và `POST /notifications/read` (`{ids?}`).
- [X] T009 [P] Viết `backend/app/lms/schemas.py` phần dùng chung: `FileOut`, `NotificationOut`, và hàm `screen_text(field_name, text)` gọi `guard.rules.screen_input`. Khi `block` thì trả 422 "Nội dung <trường> vi phạm quy tắc an toàn."; khi `redact` thì trả văn bản đã ẩn kèm cờ để response báo cho người nhập (R14)
- [X] T010 Đăng ký router của `files.py`, `notify.py` (và chỗ cho các router lms sau này) trong `backend/app/main.py`; thêm `jobs.run_due(db)` (khung rỗng) và gọi nó trong `tick()` của `backend/app/orchestration/worker.py`
- [X] T011 [P] Test nền trong `backend/tests/test_lms_files.py`:
  - Upload pdf hợp lệ.
  - `.exe` trả 415.
  - Tệp vượt giới hạn trả 413 (patch setting xuống 1 MB) và không để lại tệp.
  - Tải tệp có `Range: bytes=0-9` trả 206.
  - Học sinh lớp khác bị 404.
  - Học sinh không upload được `purpose=content`.
- [X] T012 [P] Test thông báo trong `backend/tests/test_lms_notify.py`: `dedupe_key` trùng không tạo bản ghi thứ hai, `unread_count` đúng, đánh dấu đã đọc
- [X] T013 [P] Web nền:
  - `web/src/features/lms/FileUpload.tsx`: chọn tệp, hiện tiến độ, hiện lỗi 413/415 bằng thông báo của server.
  - `web/src/features/lms/NotificationBell.tsx`: số chưa đọc, hỏi lại mỗi 60 giây, danh sách và bấm tới `link`.
  - Gắn chuông vào header của layout trong `web/src/app/App.tsx`.

**Checkpoint**: migration chạy được, upload/tải tệp và thông báo hoạt động, story bắt đầu được.

---

## Phase 3: User Story 1 - Giáo viên tạo buổi học và đăng tài liệu, video (Priority: P1) 🎯 MVP

**Goal**: giáo viên tạo, sắp xếp, công bố buổi học có tài liệu, video, link, văn bản; học sinh xem trong trang; tài liệu
bật "cho agent đọc" vào kho tri thức.

**Independent Test**: giáo viên demo tạo buổi có PDF và video, công bố; học sinh cùng lớp mở được tệp và phát video;
học sinh lớp khác không thấy (quickstart kịch bản 1–4).

### Tests cho User Story 1

- [X] T014 [P] [US1] Test buổi học trong `backend/tests/test_lms_lessons.py`:
  - Tạo buổi ra `draft`; học sinh không thấy buổi nháp; công bố thì học sinh thấy.
  - `publish_at` tương lai thì học sinh thấy `locked: true` và không có `items`.
  - Đổi thứ tự bằng `PUT .../order` với danh sách id đầy đủ (thiếu id trả 422).
  - Xóa buổi chưa có bài nộp thì xóa được.
  - Lớp `archived` chặn ghi với 409.
  - Học sinh `POST /lessons` trả 403.
- [X] T015 [P] [US1] Test mục nội dung trong `backend/tests/test_lms_lessons.py`:
  - Ràng buộc "`kind=video` cần đúng một trong `url`/`file_id`; `kind=file` cần `file_id`; `kind=link` cần `url`".
  - Link YouTube/Vimeo được chuẩn hóa `embed_url` (R4).
  - `visible=false` thì ẩn với học sinh.
  - Đề mục chứa nội dung bị guard chặn trả 422.
  - `POST /items/{iid}/view` gọi hai lần vẫn chỉ ra một `content_views`; giáo viên xem được danh sách đã xem/chưa xem.
- [X] T016 [P] [US1] Test "cho agent đọc" trong `backend/tests/test_lms_lessons.py`:
  - Bật `agent_readable` trên PDF thì tạo `Document` có `meta.lesson_item_id`, chạy `process_document`, và `knowledge.search` tìm thấy nội dung.
  - Tắt thì `Document` và chunk bị xóa nhưng tệp của buổi còn.
  - Định dạng mp4 bật cờ thì trả 422.
- [X] T017 [P] [US1] Test vitest `web/src/features/lms/videoUrl.test.ts`: chuẩn hóa `youtube.com/watch?v=`, `youtu.be/`, `vimeo.com/<id>`, link `.mp4`, và link khác thành loại `link`

### Implementation cho User Story 1

- [X] T018 [US1] Thêm schema buổi học và mục vào `backend/app/lms/schemas.py`: `LessonCreate`, `LessonPatch`, `LessonOut` (có `locked`, `items`), `ItemCreate`, `ItemPatch` (gồm `agent_readable`), `ItemOut` (có `viewed` cho học sinh), `OrderIn {ids}`; `title` "str(200) bắt buộc"
- [X] T019 [US1] Viết hàm thuần `embed_for(url) -> (kind, embed_url | None)` trong `backend/app/lms/lessons.py` theo R4 (`youtube-nocookie.com/embed/<id>`, `player.vimeo.com/video/<id>`, `.mp4/.webm` trực tiếp)
- [X] T020 [US1] Viết router buổi học trong `backend/app/lms/lessons.py`:
  - Các endpoint mục "Buổi học và mục nội dung" của contracts: list, create, get, patch, delete, order.
  - Lọc hiển thị theo R15.
  - DELETE khi đã có bài nộp/lượt làm thì 409 với gợi ý lưu trữ.
  - Công bố gọi `notify` (kind `lesson_published`) cho học sinh lớp nếu `publish_at` null hoặc đã tới.
- [X] T021 [US1] Viết router mục nội dung trong `backend/app/lms/lessons.py`:
  - create, patch, delete, order mục; `view`; `views`.
  - `kind=quiz|assignment` tạo kèm bản ghi `Quiz`/`Assignment` mặc định.
  - Qua `screen_text` cho `title`/`body`.
- [X] T022 [US1] Thêm `document_ids: list[str] | None = None` cho `search()` trong `backend/app/knowledge/service.py`, và viết `set_agent_readable(db, item, on)` trong `backend/app/lms/lessons.py` theo R3:
  - Bật thì sao tệp sang đường dẫn kho, tạo `Document` với `meta={"lesson_item_id": ...}`, gọi `process_document` qua BackgroundTasks.
  - Tắt thì xóa `Document`.
  - Chỉ PDF/DOCX/TXT/MD.
- [X] T023 [US1] Thêm vào `backend/app/lms/jobs.py` việc mở buổi hẹn giờ: buổi `published` có `publish_at` vừa tới thì gửi thông báo `lesson_published` (dedupe `lesson_published:<lesson_id>:<user_id>`)
- [X] T024 [P] [US1] Viết `web/src/features/lms/videoUrl.ts` và `web/src/features/lms/VideoPlayer.tsx`: `iframe` cho embed, `video controls` cho tệp/link trực tiếp, lỗi phát thì hiện nút "Mở ở tab mới"
- [X] T025 [US1] Viết `web/src/features/lms/LessonsTab.tsx` và `web/src/features/lms/LessonEditor.tsx`:
  - Giáo viên thấy danh sách buổi có nhãn trạng thái (dùng `StatusBadge`); tạo/sửa buổi; kéo thả HTML5 và nút lên/xuống để đổi thứ tự; công bố/về nháp/lưu trữ; hẹn giờ `publish_at`.
  - Học sinh/phụ huynh thấy danh sách buổi đã công bố, buổi khóa có nhãn "Sắp mở".
- [X] T026 [US1] Viết `web/src/features/lms/ItemEditor.tsx`:
  - Thêm mục tài liệu (qua `FileUpload`), video (tải lên hoặc dán link), liên kết, đoạn văn bản.
  - Công tắc "Cho agent đọc" (ẩn với định dạng không hỗ trợ), ẩn/hiện mục, đổi thứ tự.
- [X] T027 [US1] Viết `web/src/features/lms/LessonView.tsx`:
  - Học sinh mở buổi: xem PDF/ảnh trong trang (`iframe`/`img` trỏ endpoint tệp), phát video bằng `VideoPlayer`, định dạng khác thì nút tải về.
  - Gọi `POST /view` khi mở mục.
  - Giáo viên xem số học sinh đã xem từng mục.
- [X] T028 [US1] Thêm tab "Buổi học" (đặt đầu danh sách tab) vào `web/src/features/classes/ClassDetailPage.tsx`; thêm route `/student/classes/:classId/lessons/:lessonId` và `/teacher/classes/:classId/lessons/:lessonId` trong `web/src/app/routes.ts`; trang lớp của học sinh `web/src/features/classes/StudentClassesPage.tsx` có lối vào danh sách buổi

**Checkpoint**: US1 chạy độc lập: quickstart kịch bản 1–4 đạt.

---

## Phase 4: User Story 2 - Quiz/bài kiểm tra, làm bài, chấm tự động (Priority: P1)

**Goal**: giáo viên soạn quiz 5 loại câu và cấu hình thời gian/lượt/chế độ xem; học sinh làm bài có lưu nháp, đồng hồ
server, tự nộp; câu khách quan chấm ngay; giáo viên chấm tự luận, chấm lại, xem thống kê.

**Independent Test**: quiz 5 câu, học sinh làm, tải lại giữa chừng, nộp và thấy điểm ngay; giáo viên thấy kết quả
(quickstart kịch bản 5–8).

### Tests cho User Story 2

- [X] T029 [P] [US2] Test bảng giá trị trong `backend/tests/test_lms_grading.py` cho `grade_question()` theo R7:
  - `single`, `true_false`, `short` (chuẩn hóa NFC, casefold, gộp khoảng trắng, nhiều đáp án chấp nhận, **không** bỏ dấu).
  - `multi` `all_or_nothing` và `partial` "`max(0, (số đúng đã chọn − số sai đã chọn) / số đáp án đúng) × điểm`".
  - Bỏ trống.
  - `essay` ra `None`.
  - Điểm quiz theo `best`/`last`/`average` chỉ trên lượt đã chấm xong.
- [X] T030 [P] [US2] Test lượt làm trong `backend/tests/test_lms_quizzes.py`:
  - Bắt đầu thì có snapshot không chứa `answer_key`/`explanation`/`rubric`; gọi lại lấy đúng lượt đang làm (hai tab).
  - `deadline_at = min(started_at + duration, close_at)`.
  - Lưu câu trả lời sau `deadline_at` (patch `now()`) trả 409 `attempt_closed`.
  - Đọc lượt quá hạn thì tự chốt `submit_reason=timeout`; `jobs.run_due` chốt lượt quá hạn không ai đọc.
  - `max_attempts=1` thì lần 2 trả 409; quiz chưa mở hoặc đã đóng trả 409.
  - Quiz không có câu hỏi không công bố được.
- [X] T031 [P] [US2] Test bí mật đáp án trong `backend/tests/test_lms_quizzes.py` (SC-005): với mọi tổ hợp `show_score`/`show_answers` × mọi loại câu, duyệt **mọi** response của học sinh và phụ huynh (`GET quiz`, `POST attempts`, `PUT answers`, `GET attempt`, `submit`) và khẳng định không có khóa `answer_key`, `explanation`, `rubric` trước thời điểm cho phép, có sau thời điểm đó
- [X] T032 [P] [US2] Test chấm tự luận và chấm lại trong `backend/tests/test_lms_quizzes.py`:
  - Quiz có tự luận thì `submitted` và điểm "chờ chấm"; giáo viên chấm hết thì `graded`.
  - Sửa câu khi có lượt đang làm không đổi snapshot của lượt đó.
  - Sửa đáp án rồi `regrade` thì điểm mọi lượt cập nhật và có dòng `grade_audit` action `regrade`.
  - `results` trả số đã làm, trung bình, phân bố, tỉ lệ đúng từng câu.
  - Sao chép quiz sang buổi của lớp khác của cùng giáo viên được; lớp của giáo viên khác trả 404.
- [X] T033 [P] [US2] Test vitest `web/src/features/lms/countdown.test.ts`: đồng hồ đếm theo `deadline_at` và độ lệch `server_now` (không theo đồng hồ máy), về 0 thì gọi callback nộp một lần

### Implementation cho User Story 2

- [X] T034 [US2] Viết `backend/app/lms/grading.py` (hàm thuần, không I/O): `normalize_short(text)`, `grade_question(kind, answer_key, value, points, multi_scoring)`, `attempt_total(item_scores)`, `quiz_score(attempts, policy)`; làm tròn 2 chữ số
- [X] T035 [US2] Thêm schema quiz vào `backend/app/lms/schemas.py`:
  - `QuizConfig`: các trường của bảng `quizzes`; `scoring_policy` "`best` \| `last` \| `average`"; `show_score`/`show_answers` "`on_submit` \| `after_close` \| `never`".
  - `QuestionIn`/`QuestionTeacherOut`: `kind` "`single` \| `multi` \| `true_false` \| `short` \| `essay`", `points` "> 0", options `[{id, text}]` với id sinh ở server và giữ nguyên khi sửa.
  - `QuizStudentView`, `AttemptView`, `AttemptResult`: là **class riêng không có trường đáp án** (R5).
- [X] T036 [US2] Viết router soạn quiz trong `backend/app/lms/quizzes.py`:
  - GET (giáo viên dạng đầy đủ, học sinh/phụ huynh dạng `QuizStudentView`), PATCH cấu hình.
  - CRUD câu hỏi và order; câu hỏi qua `screen_text`; response sửa/xóa có `affects_submitted`.
  - Công bố buổi/mục quiz không có câu hỏi thì 422.
- [X] T037 [US2] Viết luồng làm bài trong `backend/app/lms/quizzes.py`:
  - `POST attempts`: tạo hoặc trả lượt `in_progress` trong một transaction; snapshot có trộn câu/đáp án theo cấu hình; `deadline_at`; trả `server_now`.
  - `PUT answers`: chỉ khi `in_progress` và `now() ≤ deadline_at`, nếu không thì 409 `attempt_closed`.
  - `submit`; hàm `finalize(attempt, reason)` chấm câu khách quan bằng `grading.py` rồi đặt `graded` hoặc `submitted`.
  - Chốt lười khi đọc lượt quá hạn.
  - `GET attempt` trả kết quả theo `show_score`/`show_answers` và `close_at`.
- [X] T038 [US2] Viết chấm tay, chấm lại, thống kê, sao chép trong `backend/app/lms/quizzes.py`:
  - `PUT attempts/{aid}/scores/{questionId}` ghi `grade_audit` action `grade`.
  - `POST questions/{id}/regrade` tính lại theo snapshot cộng `answer_key` hiện tại, ghi `grade_audit` action `regrade`.
  - `GET results` theo FR-016.
  - `POST quizzes/{qid}/copy` theo FR-017.
- [X] T039 [US2] Thêm vào `backend/app/lms/jobs.py` việc chốt lượt quá hạn: lượt `in_progress` có `deadline_at < now()` thì `finalize(reason=timeout|closed)`; đăng ký router quizzes trong `backend/app/main.py`
- [X] T040 [P] [US2] Viết `web/src/features/lms/countdown.ts` (tính thời gian còn lại theo `deadline_at` và độ lệch với `server_now`)
- [X] T041 [US2] Viết `web/src/features/lms/QuizEditor.tsx` và `web/src/features/lms/QuestionEditor.tsx`:
  - Form cấu hình (mở/đóng, thời lượng, số lượt, cách tính điểm, trộn, chế độ xem điểm/đáp án, "Cho phép hỏi agent khi làm bài" tức `block_agents` đảo, "Trợ lý chấm AI").
  - Soạn 5 loại câu: đáp án đúng, điểm, giải thích, cách chấm nhiều đáp án, rubric và đáp án mẫu cho tự luận.
  - Đổi thứ tự; cảnh báo "đã có N bài nộp" kèm nút "Chấm lại".
- [X] T042 [US2] Viết `web/src/features/lms/QuizTake.tsx`:
  - Màn làm bài với đồng hồ `countdown.ts`.
  - Lưu từng câu với debounce 1 giây và hiện trạng thái "Đã lưu".
  - Nhận 409 `attempt_closed` thì chuyển sang kết quả; hết giờ thì tự nộp; xác nhận trước khi nộp; khôi phục câu trả lời khi tải lại.
  - Route `/student/classes/:classId/quizzes/:quizId/take` trong `web/src/app/routes.ts`.
- [X] T043 [US2] Viết `web/src/features/lms/QuizResult.tsx` (học sinh: điểm/đáp án theo quyền xem, "chờ chấm" cho tự luận) và `web/src/features/lms/QuizResults.tsx` (giáo viên: bảng lượt làm, thống kê, chấm câu tự luận từng lượt)

**Checkpoint**: US1 và US2 chạy độc lập: quickstart kịch bản 5–8 đạt.

---

## Phase 5: User Story 3 - Bài tập: giao, nộp, chấm và phản hồi (Priority: P2)

**Goal**: bài tập có hạn nộp, nộp nhiều phiên bản, nộp muộn và trừ điểm, gia hạn riêng, chấm, nhận xét, trả bài.

**Independent Test**: một học sinh nộp đúng hạn, một học sinh nộp muộn; giáo viên chấm và trả bài; học sinh thấy điểm,
mức trừ và nhận xét (quickstart kịch bản 11–12).

### Tests cho User Story 3

- [X] T044 [P] [US3] Test hàm trừ điểm trong `backend/tests/test_lms_grading.py` theo R12:
  - `days_late` làm tròn lên theo ngày.
  - Ví dụ spec: điểm tối đa 10, trừ 10%/ngày, tối đa 30%, muộn 2 ngày 3 giờ, chấm 8 thì `penalty=3`, `final=5`.
  - `final` không âm; `penalty_waived` thì `final=raw`; mặc định 0% thì không trừ.
- [X] T045 [P] [US3] Test luồng bài tập trong `backend/tests/test_lms_assignments.py`:
  - Nộp đúng hạn.
  - Quá hạn và `allow_late=false` thì 409 `past_due`.
  - Nộp muộn thì `is_late`.
  - Nộp lại tạo phiên bản 2 và giáo viên xem được phiên bản 1.
  - Hạn riêng thay hạn chung (FR-021).
  - Chấm nhưng chưa trả thì học sinh không thấy điểm; trả thì thấy `raw_score`, `penalty`, `final_score`, `feedback` và nhận thông báo `returned`.
  - Bỏ trừ và gia hạn ghi `grade_audit`.
  - Bài nộp chứa nội dung bị guard chặn thì 422.

### Implementation cho User Story 3

- [X] T046 [US3] Thêm `late_penalty(raw, max_points, submitted_at, effective_due, per_day_pct, max_pct, waived)` vào `backend/app/lms/grading.py` theo R12
- [X] T047 [US3] Thêm schema bài tập vào `backend/app/lms/schemas.py`:
  - `AssignmentConfig`, `ExtensionIn`, `SubmissionIn {text?, file_ids?}`, `GradeIn {raw_score, feedback, penalty_waived?}`.
  - `SubmissionTeacherOut` và `SubmissionStudentOut`, trong đó điểm/nhận xét chỉ có khi `status = returned`.
- [X] T048 [US3] Viết router trong `backend/app/lms/assignments.py`:
  - GET (theo vai trò, phụ huynh dùng `resolve_student`), PATCH cấu hình, PUT/DELETE extension.
  - POST submission tạo `SubmissionVersion` mới; `file_ids` phải là tệp `purpose=submission` của chính học sinh.
  - GET danh sách nộp (đã nộp, muộn, chưa nộp), GET chi tiết submission.
  - PUT grade tính `penalty`/`final_score`; POST return (trống thì trả mọi bài đã chấm).
  - Thông báo `assigned` khi mục bài tập được công bố, `to_grade` cho giáo viên (dedupe theo bài và ngày).
  - Đăng ký router trong `backend/app/main.py`.
- [X] T049 [US3] Viết `web/src/features/lms/AssignmentEditor.tsx`: đề bài, tệp đính kèm, hạn nộp, điểm tối đa, cho nộp muộn, mức trừ %/ngày và mức trừ tối đa (mặc định 0), rubric và đáp án mẫu, bật/tắt trợ lý chấm AI
- [X] T050 [US3] Viết `web/src/features/lms/AssignmentView.tsx`: học sinh xem đề, hạn hiệu lực, trạng thái (chưa nộp, đã nộp, nộp muộn, quá hạn); nộp văn bản và tệp; nộp lại; xem điểm chấm, mức trừ, điểm cuối và nhận xét sau khi được trả
- [X] T051 [US3] Viết `web/src/features/lms/SubmissionsTable.tsx` và `web/src/features/lms/GradingPanel.tsx`: bảng học sinh × trạng thái, gia hạn riêng, xem các phiên bản, chấm điểm và nhận xét, bỏ trừ điểm, trả bài từng bài hoặc hàng loạt, lịch sử `grade_audit` của bài

**Checkpoint**: US3 chạy độc lập: quickstart kịch bản 11–12 đạt.

---

## Phase 6: User Story 6 - Agent tôn trọng bài kiểm tra; trợ lý AI cho giáo viên (Priority: P2)

**Goal**: mọi agent không đưa đáp án cho học sinh đang làm bài kiểm tra (không báo cho giáo viên); agent Hub
`tro-giang-lms` gợi ý câu hỏi và gợi ý chấm, chỉ có hiệu lực khi giáo viên duyệt, tôn trọng đồng ý của phụ huynh.

**Independent Test**: học sinh đang làm bài dán câu hỏi vào chat agent lớp, agent tự tạo, nhóm; cả ba từ chối và nhật ký
lớp của giáo viên không có sự kiện. Giáo viên gợi ý 5 câu và gợi ý chấm một bài, duyệt rồi mới có hiệu lực (quickstart
kịch bản 9–10, 13–16).

### Tests cho User Story 6

- [X] T052 [P] [US6] Test chặn đầu vào trong `backend/tests/test_lms_integrity.py` (dùng helper `chat`):
  - Học sinh có lượt `in_progress` của quiz `block_agents=true` dán nguyên văn stem câu hỏi vào chat agent lớp: agent **không** được gọi (FakeChatModel không nhận lượt `run_agent`), notice `guard_blocked` có `EXAM_BLOCKED`, có `GuardEvent(category="exam_integrity", stage="input", private_space=True)`.
  - Cùng câu hỏi gửi tới agent cá nhân tự tạo (installation scope `personal`) cũng bị chặn.
  - Sau khi nộp, hoặc khi `block_agents=false`: không chặn.
  - Câu không liên quan tới bài: không chặn.
- [X] T053 [P] [US6] Test chặn đầu ra trong `backend/tests/test_lms_integrity.py`:
  - FakeChatModel trả câu trả lời chứa đáp án đúng của câu trong bài thì bị `text_reset` thay bằng `EXAM_BLOCKED`.
  - Trong nhóm (`app/chat/groups.py`) có một học sinh đang làm bài, người hỏi là học sinh khác, câu trả lời chứa đáp án thì vẫn bị chặn.
  - Câu trả lời handoff (feature 003, chạy `drain`) chứa đáp án bị chặn trước khi hiện cho học sinh.
  - `GET /classes/{cid}/audit` của giáo viên không chứa sự kiện `exam_integrity`; `/audit/events` của admin có sự kiện nhưng `excerpt` rỗng.
- [X] T054 [P] [US6] Test trợ lý trong `backend/tests/test_lms_assist.py` (LLM `fake` trả JSON có sẵn):
  - `GET assist/agents` chỉ liệt kê agent cài trong lớp, đang bật, phiên bản `certified`, có `teacher` trong `target_roles` và tool `quiz_generator`/`rubric_grader`; gỡ cài thì danh sách rỗng và POST gợi ý trả 409.
  - Gợi ý câu hỏi: `pending` → `ready`, mỗi câu có đáp án, giải thích, `source`; chưa duyệt thì quiz không có câu mới; duyệt/sửa/bỏ từng câu thì câu duyệt có `source="ai"`, `ai_suggestion_id`.
  - `document_ids` giới hạn tìm kiếm trong tài liệu buổi.
  - Gợi ý chấm: payload có `criteria`; học sinh và phụ huynh gọi mọi endpoint của mình không thấy `ai_suggestions` hay điểm gợi ý (SC-011); sổ điểm không tính điểm gợi ý chưa duyệt; duyệt thì ghi `final` và điểm vào bài nhưng chưa trả.
  - Học sinh chưa có đồng ý (lớp `require_parent_consent`) thì `skipped_consent` và LLM không được gọi (FR-037).
  - Bài nộp bị guard chặn thì `failed` kèm lý do.
  - Gỡ agent không xóa gợi ý đã duyệt.

### Implementation cho User Story 6: chặn đáp án

- [X] T055 [US6] Viết `backend/app/lms/integrity.py`:
  - `active_exams(db, user_ids) -> list[ActiveExam]`: lượt `in_progress` chưa quá hạn của quiz `block_agents=true`, kèm stem, lựa chọn, đáp án đúng.
  - `matches_question(text, exams) -> ActiveExam | None`: chuẩn hóa bằng `app.textnorm.fold`, độ trùng n-gram ký tự 3 ≥ ngưỡng `EXAM_MATCH_THRESHOLD`, đặt hằng số và kiểm bằng dataset T059.
  - `reveals_answer(reply, exams) -> bool`: câu trả lời chứa văn bản đáp án đúng của lựa chọn/đáp án ngắn, hoặc ký hiệu lựa chọn đúng đi kèm stem khớp.
  - `exam_context(exams) -> str` cho LLM review.
- [X] T056 [US6] Sửa `backend/app/runtime/graph.py`:
  - Thêm hằng `EXAM_BLOCKED` ("Bạn đang làm một bài kiểm tra trên lớp nên mình chưa thể giúp câu này. Làm xong bài, mình cùng xem lại nhé!").
  - Node `screen`: nếu `ctx.role == "student"`, gọi `active_exams([ctx.user.id])` và `matches_question`; khớp thì `ctx.log("input", Verdict("block", "exam_integrity", ..., "rule"), text)` rồi `_blocked`.
  - Node `review`: lấy học sinh đang đọc (người hỏi trong hội thoại `direct`, mọi thành viên học sinh còn trong nhóm khi `conversation_kind == "group"`), gọi `active_exams`; nếu có thì `reveals_answer` (luật), sau đó `classifier.review_output(..., no_answers=True, exam_context=...)` **kể cả khi người hỏi là giáo viên/phụ huynh trong nhóm**; chặn thì `_replace(ctx, EXAM_BLOCKED)` và ghi `ctx.log("output", ...)`.
- [X] T057 [US6] Sửa `backend/app/guard/classifier.py`: `review_output` nhận thêm tham số tùy chọn `exam_context: str = ""`, đưa vào prompt là "câu hỏi của bài kiểm tra học sinh đang làm; chặn mọi đáp án/lời giải của các câu này kể cả diễn đạt lại", category trả về `exam_integrity`. Không đổi hành vi khi tham số rỗng (test hiện có vẫn qua)
- [X] T058 [US6] Sửa `backend/app/orchestration/handoffs.py`: trước khi ghi câu trả lời của agent được giao việc vào hội thoại mà học sinh thấy, chạy cùng kiểm tra `active_exams` / `reveals_answer` / review như T056; bị chặn thì ghi `EXAM_BLOCKED` thay nội dung và log `GuardEvent` stage `handoff`
- [X] T059 [P] [US6] Tạo dataset `eval/exam_integrity.jsonl`: ≥ 30 câu hỏi bài kiểm tra mẫu (Toán, Văn, Anh), mỗi câu có bản dán nguyên văn và ≥ 1 bản diễn đạt lại, cùng ≥ 10 câu đối chứng không liên quan. Viết `eval/run_exam_integrity.py` chạy cả ba kênh (chat agent lớp, agent cá nhân, nhóm), in tỉ lệ từ chối mỗi kênh và tỉ lệ chặn nhầm; tham số `--provider` giống `eval/run_delegation.py`

### Implementation cho User Story 6: trợ lý AI cho giáo viên

- [X] T060 [US6] Mở rộng tool trong `backend/app/tools/impl.py`:
  - `QuizArgs` thêm `document_ids: list[str] = []` và `question_types: list[str]` (các loại của LMS); `quiz_generator` truyền `document_ids` vào `knowledge.search`, sửa `QUIZ_SYSTEM` để mỗi câu có `kind`, `options`, `answer`, `explanation`, `source` (tên tài liệu + vị trí đoạn).
  - `RubricArgs` nhận `rubric` có cấu trúc `{criteria:[{name, max_points, description}], model_answer}` và `max_points`; `rubric_grader` trả `{points, criteria:[{name, points, reason}], feedback}`.
  - Giữ tương thích với cách agent chat đang gọi (test `test_documents_tools.py` vẫn qua).
- [X] T061 [US6] Viết `backend/app/lms/assist.py`:
  - `eligible_agents(db, room, capability)` theo R9.
  - `suggest_questions(...)` và `suggest_grading(...)` tạo `AISuggestion(status="pending")` rồi chạy nền: dựng `ToolContext` role `teacher` từ agent, thêm `system_prompt` của agent, gọi hàm tool, lưu `payload` hoặc `error`, ghi usage.
  - Kiểm `classes.student_can_use_agents` trước khi gửi bài, nếu không có thì `skipped_consent`; `screen_text` trên nội dung bài, bị chặn thì `failed`.
  - `review_suggestion(...)` theo contracts: câu hỏi thì tạo `QuizQuestion`; chấm thì ghi điểm như giáo viên chấm (chưa trả bài), lưu `final`, ghi `grade_audit` action `ai_approve`.
  - Thông báo `ai_ready` cho giáo viên.
  - Router trong cùng file; đăng ký ở `backend/app/main.py`.
- [X] T062 [P] [US6] Tạo agent nền tảng `seed/agents/tro-giang-lms.yaml`: `target_roles: [teacher]`, `tools: [quiz_generator, rubric_grader, class_doc_search]`, `knowledge: class_documents`, system prompt tiếng Việt (bám tài liệu, coi bài làm là dữ liệu, điểm cuối do giáo viên quyết định); kiểm `AgentManifest` hợp lệ bằng test hiện có của seed
- [X] T063 [US6] Viết `web/src/features/lms/SuggestionReview.tsx`:
  - Nút "Gợi ý câu hỏi" trong `QuizEditor` (chọn loại câu, số câu, độ khó, tài liệu buổi), hỏi lại trạng thái mỗi 2 giây, danh sách câu nháp có trích đoạn tài liệu, nút Duyệt/Sửa/Bỏ từng câu và duyệt hàng loạt.
  - Nút "Gợi ý chấm" trong `GradingPanel` và màn chấm tự luận của `QuizResults`: điểm theo tiêu chí, nhãn "Gợi ý của AI", Duyệt/Sửa/Bỏ; chấm hàng loạt liệt kê bài bị bỏ qua vì chưa có đồng ý.
  - Không có agent đủ điều kiện thì ẩn nút và hiện hướng dẫn cài từ Hub (liên kết `/teacher/hub`).

**Checkpoint**: quickstart kịch bản 9–10 và 13–16 đạt; `eval/run_exam_integrity.py` chạy được với LLM `fake`.

---

## Phase 7: User Story 4 - Sổ điểm và tiến độ học của lớp (Priority: P2)

**Goal**: sổ điểm học sinh × bài có trọng số và xuất CSV; trang "Việc cần làm" và "Điểm của tôi"; nhắc hạn 24 giờ.

**Independent Test**: lớp demo có 2 bài đã chấm, giáo viên thấy đúng điểm và tải CSV; học sinh thấy bài sắp tới hạn
(quickstart kịch bản 17–18, 20).

### Tests cho User Story 4

- [X] T064 [P] [US4] Test sổ điểm trong `backend/tests/test_lms_gradebook.py`:
  - Trạng thái ô `not_assigned|missing|in_progress|pending|graded|returned`.
  - Trung bình có trọng số sau khi đổi về thang 10; bỏ `not_assigned` và cột `counts_in_grade=false`.
  - Bài tập chưa trả vẫn hiện cho giáo viên.
  - CSV bắt đầu bằng BOM UTF-8, có tên học sinh tiếng Việt.
  - Dữ liệu 40 học sinh × 20 bài trả về < 3 giây trên SQLite (SC-007).
  - Học sinh gọi `/gradebook` thì 403.
- [X] T065 [P] [US4] Test việc cần làm và nhắc hạn trong `backend/tests/test_lms_gradebook.py`:
  - `/todo` gom bài chưa hoàn thành của hai lớp, sắp theo hạn gần nhất, bỏ bài đã nộp.
  - `/my-grades` chỉ có điểm đã trả.
  - `jobs.run_due` tạo `due_soon` cho bài còn ≤ 24 giờ, chạy hai lần vẫn một thông báo.

### Implementation cho User Story 4

- [X] T066 [US4] Viết `backend/app/lms/gradebook.py`:
  - `GET /classes/{cid}/gradebook`: truy vấn gom nhóm từ `submissions` và `quiz_attempts`, điểm quiz dùng `grading.quiz_score`, không đọc `ai_suggestions`.
  - `GET /gradebook.csv` có BOM; `GET /classes/{cid}/my-grades`; `GET /todo`.
  - Học sinh và phụ huynh dùng `resolve_student`.
  - Đăng ký router.
- [X] T067 [US4] Thêm vào `backend/app/lms/jobs.py` nhắc hạn: bài tập có `due_at` và quiz có `close_at` trong 24 giờ tới, học sinh chưa nộp hoặc chưa làm thì `notify(kind="due_soon", dedupe_key="due_soon:<item_id>:<user_id>")`
- [X] T068 [US4] Viết `web/src/features/lms/GradebookTab.tsx`: bảng cuộn ngang có cột học sinh cố định, ô trạng thái/điểm bấm tới bài, sửa trọng số và "tính vào điểm" của cột, nút "Tải CSV"; thêm tab "Sổ điểm" vào `web/src/features/classes/ClassDetailPage.tsx`
- [X] T069 [US4] Viết `web/src/features/lms/TodoPage.tsx` và `web/src/features/lms/MyGradesPage.tsx`; thêm mục sidebar "Việc cần làm" (`/student/todo`) cho học sinh trong `web/src/app/routes.ts` và route trang điểm theo lớp

**Checkpoint**: quickstart kịch bản 17–18, 20 đạt.

---

## Phase 8: User Story 5 - Phụ huynh theo dõi việc học của con (Priority: P3)

**Goal**: phụ huynh chỉ xem buổi học, việc cần làm, trạng thái nộp và điểm đã trả của con.

**Independent Test**: `parent@` thấy bài chưa nộp và điểm đã trả của con; không thấy dữ liệu học sinh khác (quickstart
kịch bản 19).

### Tests cho User Story 5

- [X] T070 [P] [US5] Test truy cập chéo trong `backend/tests/test_lms_access.py` (SC-008):
  - Dựng hai học sinh cùng lớp và hai phụ huynh.
  - Với mọi endpoint đọc dữ liệu cá nhân (`attempts/{aid}`, `submissions/{sid}`, `assignments/{asg}?student_id=`, `my-grades`, `todo`, `files/{fid}` purpose `submission`), học sinh A/phụ huynh A truy cập dữ liệu của B thì 403 hoặc 404.
  - Phụ huynh gọi mọi endpoint ghi (nộp bài, bắt đầu làm bài, lưu câu trả lời) thì 403.
  - Phụ huynh của học sinh không thuộc lớp thì 404.

### Implementation cho User Story 5

- [X] T071 [US5] Rà mọi router trong `backend/app/lms/` để mọi endpoint đọc dữ liệu cá nhân đi qua `resolve_student` và mọi endpoint ghi từ chối vai trò `parent`; sửa chỗ thiếu cho tới khi T070 qua
- [X] T072 [US5] Thêm vào `web/src/features/family/ParentPages.tsx` mục theo từng con: việc cần làm (đã nộp, chưa nộp, quá hạn), điểm đã trả theo lớp, lối vào danh sách buổi học (chỉ xem, ẩn mọi nút làm bài/nộp bài)

**Checkpoint**: mọi user story chạy độc lập.

---

## Phase 9: Polish & việc chung

- [X] T073 Bổ sung `backend/scripts/seed_demo.py` (chế độ `--ensure`, lũy đẳng):
  - Cho lớp demo của `teacher@demo.edu.vn`: 2 buổi (một đã công bố có PDF từ `seed/documents/`, video link, quiz 5 câu đủ loại, bài tập có trừ muộn; một nháp).
  - Cài `tro-giang-lms` vào lớp.
  - Bài nộp mẫu của `student@` và `student2@` (một bài đã trả).
  - Chạy hai lần không nhân đôi dữ liệu.
- [X] T074 [P] Tạo `eval/lms_assist/` (tài liệu mẫu và 30 bài tự luận kèm điểm giáo viên) và `eval/run_lms_assist.py` đo SC-009 (tỉ lệ câu duyệt không sửa, dùng đáp án tham chiếu) và SC-010 (độ lệch ≤ 1 điểm), tham số `--provider`
- [X] T075 [P] Cập nhật `README.md`: mục "Trạng thái" (feature 004), "Chạy local" (dữ liệu demo LMS, biến tùy chọn `LMS_MAX_*`), "Kiểm tra" (thêm `uv run python ../eval/run_exam_integrity.py`)
- [X] T076 Kiểm `dev.ps1` theo nguyên tắc III: parse cú pháp bằng `pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw dev.ps1)) | Out-Null"`, rồi chạy `.\dev.ps1` trên máy có Docker, xác nhận migration `0007_lms` và seed chạy, backend và web lên. Chỉ sửa `dev.ps1` nếu phát hiện bước thiếu; không chạy được thì ghi rõ "chưa chạy thử"
- [X] T077 Chạy toàn bộ kiểm tra: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`, chạy lại pytest với `TEST_DATABASE_URL` trỏ Postgres, `cd web && npm test && npm run build`; sửa tới khi qua
- [X] T078 Kiểm thử đầu-cuối 20 kịch bản của `specs/004-lms-lessons/quickstart.md` trên trình duyệt bằng skill `run-eduagent`; ghi kết quả từng kịch bản (đạt, không đạt, lý do) vào cuối `quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: bắt đầu ngay.
- **Foundational (Phase 2)**: sau Setup; **chặn** mọi story (T004 → T005 trước mọi thứ dùng bảng).
- **US1 (Phase 3)**: sau Phase 2. US2, US3 cần mục `quiz`/`assignment` mà T021 tạo, nên làm US1 trước. Nếu chạy song
  song thì tách riêng phần tạo mục quiz/bài tập của T021.
- **US2 (Phase 4)**, **US3 (Phase 5)**: sau US1, độc lập với nhau.
- **US6 (Phase 6)**:
  - Phần chặn đáp án (T052–T053, T055–T059) cần US2 (lượt làm bài).
  - Phần trợ lý (T054, T060–T063) cần US2 (quiz, câu tự luận) và US3 (bài nộp).
- **US4 (Phase 7)**: cần US2 và US3 để có điểm.
- **US5 (Phase 8)**: cần các router của US1–US4.
- **Polish (Phase 9)**: sau các story muốn giao.

### Trong mỗi story

- Viết test trước, chạy cho thấy đỏ, rồi mới cài đặt.
- Thứ tự: schema → hàm thuần (`grading.py`) → router → jobs → web.
- `backend/app/main.py` và `backend/app/lms/schemas.py` bị nhiều task sửa nên làm tuần tự, không đánh [P].

### Parallel Opportunities

- Phase 2: T006, T007, T008, T009 chạy song song sau T004; T011, T012, T013 song song.
- US1: test T014–T017 song song; T024 song song với T018–T023.
- US2: test T029–T033 song song; T040 song song với backend.
- US6: T059 (dataset) và T062 (YAML agent) song song với mọi task khác; T052–T054 song song.
- US4 và US5 có thể chạy song song khi US2 và US3 đã xong.

## Parallel Example: User Story 2

```text
# Viết test song song (khác file hoặc độc lập):
Task: "T029 Test bảng giá trị grade_question trong backend/tests/test_lms_grading.py"
Task: "T030 Test lượt làm trong backend/tests/test_lms_quizzes.py"
Task: "T033 Test countdown trong web/src/features/lms/countdown.test.ts"

# Sau T034–T037, web chạy song song với backend jobs:
Task: "T039 Chốt lượt quá hạn trong backend/app/lms/jobs.py"
Task: "T041 QuizEditor.tsx, QuestionEditor.tsx"
```

## Parallel Example: User Story 6

```text
Task: "T059 Dataset eval/exam_integrity.jsonl + eval/run_exam_integrity.py"
Task: "T062 seed/agents/tro-giang-lms.yaml"
Task: "T052 Test chặn đầu vào trong backend/tests/test_lms_integrity.py"
Task: "T054 Test trợ lý trong backend/tests/test_lms_assist.py"
```

## Gợi ý giao việc (skill orchestrate)

Theo `plan.md`:
- **Hợp giao cho worker** (mô tả rõ, kiểm được bằng test): T011, T012, T017, T024, T029, T033, T040, T044, T049–T051, T059, T062, T064, T068, T069, T072, T074, T075.
- **Giữ lại tự làm** (rủi ro bảo mật, kiến trúc hoặc móc vào runtime): T004–T007, T030–T031, T035, T037, T055–T058, T061, T070–T071.
- **Khi giao việc**, brief phải nhắc: không commit, chuỗi hiển thị viết tiếng Việt, chạy `pytest`/`vitest` của phần mình.

## Implementation Strategy

### MVP (User Story 1)

1. Phase 1 → Phase 2 → Phase 3.
2. **Dừng lại kiểm**: quickstart kịch bản 1–4, sau đó demo được: giáo viên đăng bài giảng, học sinh xem.

### Giao dần

1. MVP (US1).
2. Thêm US2 (quiz, chấm tự động): demo bài kiểm tra.
3. Thêm US3 (bài tập).
4. Thêm US6 (chặn đáp án và trợ lý AI): điểm khác biệt AI của đồ án.
5. Thêm US4 (sổ điểm, việc cần làm), rồi US5 (phụ huynh).
6. Phase 9: seed, README, `dev.ps1`, kiểm thử đầu-cuối.

Mỗi bước đều chạy `pytest` và `vitest` toàn bộ để không làm hỏng feature 003.
