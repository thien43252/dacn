# Research: Buổi học, quiz/bài kiểm tra, bài tập (feature 004)

Mỗi mục: **Quyết định**, **Lý do**, **Phương án đã cân nhắc**. Mọi mục "NEEDS CLARIFICATION" của Technical Context
đã được giải quyết ở đây.

## R1. Vị trí code mới

- **Quyết định**: Thêm package `backend/app/lms/` (models, schemas, các router `lessons`, `quizzes`, `assignments`,
  `gradebook`, và các service `files`, `grading`, `integrity`, `assist`, `notify`). Thông báo nằm trong
  `backend/app/lms/notify.py` + bảng `notifications` (đủ dùng cho feature này, chưa tách module riêng). Web thêm
  `web/src/features/lms/` và `web/src/api-client/lms.ts`.
- **Lý do**: Giữ đúng cách chia module theo nghiệp vụ của `main` (`classes/`, `knowledge/`, `orchestration/`…). Một
  package giúp migration, test và review theo feature dễ hơn.
- **Phương án đã cân nhắc**: Nhét vào `classes/` (file phình to, trộn quyền thành viên với nội dung học); tách 4 package
  (nhiều import vòng giữa quiz/assignment/gradebook).

## R2. Lưu tệp và phát video

- **Quyết định**: Dùng lại `settings.upload_dir` (`backend/data/uploads`), thư mục con `lms/<class_id>/`, tên tệp là
  `<file_id><ext>` (không bao giờ dùng tên client làm đường dẫn, như `knowledge/router.py`). Ghi tệp theo từng khúc
  (1 MB) để tệp video 200 MB không nằm hết trong RAM; vượt giới hạn thì dừng, xóa phần đã ghi, trả 413. Tải xuống qua
  endpoint có kiểm tra quyền, trả `FileResponse` (Starlette hỗ trợ header `Range` nên tua video được). Giới hạn: tài
  liệu/ảnh/tệp nộp 25 MB, video 200 MB; whitelist định dạng (pdf, docx, pptx, xlsx, txt, md, png, jpg, webp, mp4, webm,
  mp3, zip). Biến môi trường tùy chọn `LMS_MAX_FILE_MB`, `LMS_MAX_VIDEO_MB` có giá trị mặc định nên không bắt buộc sửa
  `.env`.
- **Lý do**: Chạy local, không có object storage; cùng chỗ với tài liệu agent nên `dev.ps1` không cần bước mới.
- **Phương án đã cân nhắc**: Lưu blob trong Postgres (phình DB, không stream range); MinIO (thêm container, trái mục
  tiêu gọn của `dev.ps1`).

## R3. "Cho agent đọc" và kho tri thức

- **Quyết định**: Mục tài liệu có `document_id` tùy chọn. Bật cờ → tạo một `Document` của lớp trỏ tới **cùng tệp đã
  lưu** (bản sao tệp sang đường dẫn của kho để xóa độc lập) và gọi `process_document` như upload ở tab Tài liệu. Tắt
  cờ → xóa `Document` (chunk xóa theo cascade), giữ tệp của buổi học. Chỉ áp dụng cho PDF/DOCX/TXT/MD (định dạng kho
  hiện đọc được); định dạng khác ẩn công tắc. `knowledge.search` nhận thêm tham số `document_ids` tùy chọn để trợ lý soạn
  câu hỏi chỉ tìm trong tài liệu của một buổi.
- **Lý do**: Spec yêu cầu dùng chung kho tri thức hiện có, không tạo kho mới; tách bản ghi giúp tab Tài liệu vẫn hiển
  thị và xóa được như cũ.
- **Phương án đã cân nhắc**: Một bảng tệp dùng chung cho cả hai nơi (phải sửa sâu `knowledge/`, rủi ro hồi quy).

## R4. Video bằng đường link

- **Quyết định**: Nhận link YouTube, Vimeo và link trực tiếp tới tệp `.mp4/.webm`. YouTube/Vimeo được chuẩn hóa thành
  URL nhúng (`youtube-nocookie.com/embed/<id>`, `player.vimeo.com/video/<id>`) và hiện trong `iframe`; link tệp hiện
  bằng thẻ `video`. Link khác lưu như "liên kết ngoài". Khi nhúng lỗi, UI hiện nút "Mở ở tab mới".
- **Lý do**: Đủ cho nhu cầu lớp học, không phải gọi API ngoài khi lưu.
- **Phương án đã cân nhắc**: oEmbed (cần gọi mạng lúc lưu, test phải mock).

## R5. Giữ bí mật đáp án và chống đổi đề giữa chừng

- **Quyết định**: Câu hỏi lưu `answer_key` riêng; schema trả cho học sinh là một kiểu Pydantic khác **không có trường
  đáp án** (không lọc bằng `if`). Khi học sinh bắt đầu lượt làm, hệ thống chụp **snapshot** đề (id câu, nội dung, lựa
  chọn với id ổn định, thứ tự sau khi trộn, điểm) vào lượt làm. Chấm dựa trên snapshot + `answer_key` hiện tại của câu
  (id lựa chọn không đổi khi trộn). Sửa câu chỉ ảnh hưởng lượt bắt đầu sau đó; "chấm lại" tính lại điểm các lượt đã nộp
  theo đáp án mới và ghi `grade_audit`. Đáp án và lời giải chỉ có trong response xem kết quả khi `show_answers` cho
  phép (sau khi nộp hoặc sau `close_at`).
- **Lý do**: FR-014/SC-005 cần bảo đảm theo cấu trúc chứ không theo kỷ luật lập trình; snapshot giải quyết edge case
  sửa đề khi đang có người làm và trộn đáp án.
- **Phương án đã cân nhắc**: Version hóa toàn bộ quiz (nặng, không cần cho phạm vi này).

## R6. Thời gian làm bài, lưu nháp, tự nộp

- **Quyết định**: Server ghi `started_at` và tính `deadline_at = min(started_at + duration, close_at)`. Client lưu câu
  trả lời bằng `PUT .../answers` (debounce ~1 giây, gửi từng câu), server từ chối mọi lần lưu có thời điểm nhận >
  `deadline_at` (409, không có thời gian ân hạn). Đồng hồ trên UI đếm theo `deadline_at` do server trả về. Lượt quá hạn
  được chốt **lười** (bất kỳ lần đọc lượt làm nào sau hạn) và **chủ động** bởi `worker.tick` (quét lượt `in_progress`
  quá hạn, chốt với `submit_reason = timeout|closed`). Mỗi học sinh chỉ có một lượt `in_progress` cho một quiz (ràng
  buộc unique `(quiz_id, student_id, attempt_no)` + kiểm tra trong cùng transaction; hai tab cùng dùng một lượt).
- **Lý do**: Không tin đồng hồ trình duyệt (FR-011); worker trong tiến trình đã có (`orchestration/worker.py`) nên
  không cần scheduler mới.
- **Phương án đã cân nhắc**: WebSocket giữ phiên làm bài (phức tạp, không cần); cho 10 giây ân hạn (trái FR-012).

## R7. Quy tắc chấm tự động

- **Quyết định**:
  - Một đáp án / đúng-sai: đúng → đủ điểm, sai/bỏ trống → 0.
  - Nhiều đáp án: `all_or_nothing` (tập chọn = tập đúng) hoặc `partial`:
    `max(0, (số đúng đã chọn − số sai đã chọn) / số đáp án đúng) × điểm`.
  - Điền chỗ trống: so khớp sau chuẩn hóa (Unicode NFC, casefold, gộp khoảng trắng, bỏ khoảng trắng đầu/cuối) với bất kỳ
    đáp án chấp nhận nào; không bỏ dấu tiếng Việt (bỏ dấu đổi nghĩa). Dùng `app/textnorm.py` nếu khớp quy tắc này.
  - Tự luận: `pending` cho tới khi giáo viên chấm.
  - Điểm làm tròn 2 chữ số. Điểm của quiz theo `scoring_policy` (cao nhất, lần cuối, trung bình) trên các lượt **đã chấm
    xong**.
- **Lý do**: Quy tắc phổ biến của LMS, kiểm thử được bằng bảng giá trị.

## R8. Chặn đáp án khi đang làm bài kiểm tra (FR-028)

- **Quyết định**: `app/lms/integrity.py` cung cấp `active_exams(db, user_ids)` → các lượt `in_progress` của quiz có
  `block_agents = true`, kèm stem câu hỏi và đáp án đúng (chỉ dùng phía server). Chèn vào runtime ở hai chỗ, áp dụng cho
  **mọi** hội thoại vì khóa theo người học, không theo agent hay lớp:
  1. Node `screen` (`runtime/graph.py`): nếu người gửi là học sinh có bài đang mở, so khớp tin nhắn với stem các câu
     (chuẩn hóa `textnorm.fold`, độ trùng n-gram ký tự / token ≥ ngưỡng) → chặn với thông báo `EXAM_BLOCKED`.
  2. Node `review`: nếu **bất kỳ** học sinh nào đang đọc câu trả lời có bài đang mở (người hỏi trong chat riêng; mọi
     thành viên học sinh còn trong nhóm), (a) luật: câu trả lời chứa đáp án đúng của câu khớp với câu hỏi → chặn;
     (b) gọi `classifier.review_output` với `no_answers=True` và thêm ngữ cảnh "các câu hỏi bài kiểm tra đang mở" để mô
     hình nhận ra dạng diễn đạt lại. Chặn → thay bằng `EXAM_BLOCKED`.
  - Câu trả lời của agent được giao việc (handoff, feature 003) cũng hiện cho học sinh nên đi qua cùng bước review
    trước khi ghi vào hội thoại.
  - Ghi `GuardEvent(category="exam_integrity", private_space=True)` qua `ctx.log`: theo cơ chế hiện có, sự kiện trong
    không gian riêng tư không hiện cho giáo viên/phụ huynh; admin thấy không kèm trích đoạn (FR-051 của 003).
  - Đo SC-006 bằng `eval/run_exam_integrity.py` + dataset `eval/exam_integrity.jsonl` (≥ 30 câu × 3 kênh). Với LLM
    `fake`, chỉ phần luật được kiểm tra trong pytest; phần diễn đạt lại đo bằng mô hình thật khi có API key.
- **Lý do**: Runtime đã có lớp guard và category `academic_integrity`; chèn ở đây phủ cả agent tự tạo chưa kiểm định,
  agent trong nhóm và handoff mà không phải sửa từng agent.
- **Phương án đã cân nhắc**: Thêm chỉ dẫn vào system prompt (dễ vượt qua); khóa hẳn chat (bị loại ở bước clarify).

## R9. Trợ lý AI cho giáo viên là agent trên Hub (FR-031 – FR-038)

- **Quyết định**:
  - Agent đủ điều kiện = có `Installation` scope `class` đang bật trong lớp, phiên bản `certified`, `target_roles` có
    `teacher`, và manifest khai báo tool: `quiz_generator` (gợi ý câu hỏi) hoặc `rubric_grader` (gợi ý chấm). Không thêm
    trường mới vào manifest.
  - LMS gọi trực tiếp hàm tool trong `tools/impl.py` ở "chế độ trợ lý" (không qua chat), với `ToolContext` role
    `teacher` dựng từ agent đó, và thêm `system_prompt` của agent làm chỉ dẫn. Ghi nhận usage như tool call.
  - `quiz_generator` mở rộng: nhận `document_ids` (giới hạn trong tài liệu của buổi), trả thêm `source` (tài liệu + vị
    trí đoạn) cho mỗi câu, và hỗ trợ đủ loại câu của LMS. `rubric_grader` nhận rubric/đáp án mẫu của bài và trả điểm theo
    tiêu chí + lý do.
  - Chạy nền (`BackgroundTasks`), kết quả lưu trong `ai_suggestions` (trạng thái `pending → ready | failed`), UI hỏi lại
    mỗi 2 giây cho tới khi xong.
  - Trước khi gửi bài nộp cho AI: kiểm `classes.student_can_use_agents(room, student_id)` (FR-037, không có thì
    `skipped_consent`), `guard.rules.screen_input` trên nội dung (chặn thì `failed` kèm lý do), coi nội dung bài là dữ
    liệu (bọc thẻ như `rubric_grader` đang làm).
  - Seed: thêm agent nền tảng `seed/agents/tro-giang-lms.yaml` (tools `quiz_generator`, `rubric_grader`,
    `class_doc_search`; `target_roles: [teacher]`). `sync_platform_agents` cho phiên bản `certified`; `seed_demo
    --ensure` cài agent này vào lớp demo.
- **Lý do**: Đúng câu trả lời clarify (agent Hub, qua kiểm định), tận dụng hai tool đã có thay vì viết LLM pipeline mới.
- **Phương án đã cân nhắc**: Thêm trường `lms_assist` vào manifest (đổi hợp đồng agent, phải sửa builder và kiểm định);
  chạy qua hội thoại chat (khó lấy output có cấu trúc, lẫn vào lịch sử chat).

## R10. Thông báo và nhắc hạn

- **Quyết định**: Bảng `notifications` với `dedupe_key` unique (ví dụ `due_soon:<item_id>:<user_id>`) để tạo lặp lại an
  toàn. Tạo lúc: công bố buổi (khi tới `publish_at` thì worker tạo), giao bài, trả bài/điểm, có bài nộp chờ chấm (gộp
  theo bài). Nhắc 24 giờ trước hạn do `worker.tick` quét. Web: chuông trên header có số chưa đọc, hỏi lại mỗi 60 giây.
- **Lý do**: Spec chỉ cần thông báo trong ứng dụng; dùng worker sẵn có.
- **Phương án đã cân nhắc**: Đẩy qua SSE bus của chat (bus hiện theo hội thoại, không theo người dùng).

## R11. Sổ điểm và xuất bảng tính

- **Quyết định**: Mỗi bài tập/quiz là một cột, có `weight` (mặc định 1) và `counts_in_grade`. Ô điểm tính khi đọc từ
  `submissions` / `quiz_attempts` (không lưu bảng điểm riêng để tránh lệch), đổi về thang 10 trước khi lấy trung bình có
  trọng số. Ô "không được giao" (học sinh vào lớp sau khi bài đóng) bị loại khỏi trung bình. Xuất CSV UTF-8 có BOM
  (Excel mở đúng tiếng Việt), không thêm thư viện.
- **Lý do**: 40 × 20 ô tính trong vài truy vấn gom nhóm, đạt SC-007 (< 3 giây) không cần cache.
- **Phương án đã cân nhắc**: Xuất `.xlsx` (thêm dependency `openpyxl`, không cần thiết).

## R12. Trừ điểm nộp muộn

- **Quyết định**: `effective_due` = hạn riêng của học sinh nếu có, ngược lại hạn chung.
  `days_late = ceil((submitted_at − effective_due) / 24h)` khi dương; `penalty = min(per_day_pct × days_late, max_pct) / 100
  × max_points`; `final = max(0, raw − penalty)`, hoặc `raw` nếu giáo viên bỏ trừ (`penalty_waived`, ghi
  `grade_audit`). Thời điểm nộp dùng phiên bản mới nhất.
- **Lý do**: Khớp kịch bản ví dụ trong spec (2 ngày 3 giờ → 3 ngày).

## R13. Nhật ký thao tác điểm (FR-030, FR-035)

- **Quyết định**: Bảng `grade_audit` riêng (người làm, hành động, đối tượng, học sinh, giá trị trước/sau, thời điểm).
  Yêu cầu AI gợi ý và kết quả duyệt ghi vào chính `ai_suggestions` (người yêu cầu, người duyệt, trạng thái). Giáo viên
  xem lịch sử ngay trong màn chấm bài.
- **Lý do**: `guard_events` dành cho quyết định an toàn, trộn vào làm nhiễu nhật ký an toàn của lớp.

## R14. Guard cho nội dung LMS (FR-029)

- **Quyết định**: Mọi trường văn bản người dùng nhập (đề bài, câu hỏi, lựa chọn, bài nộp, nhận xét) đi qua
  `guard.rules.screen_input` khi lưu: `block` → 422 với lý do; `redact` → lưu bản đã ẩn và báo cho người nhập. Không gọi
  bộ phân loại LLM ở đây (chi phí, độ trễ khi lưu nháp).
- **Lý do**: Cùng lớp luật với chat; LLM classifier vẫn chạy khi nội dung tới agent.

## R15. Hiển thị buổi học và quyền

- **Quyết định**: Học sinh thấy buổi `published`; nếu `publish_at > now` chỉ thấy tiêu đề và nhãn "sắp mở". Không có điều
  kiện mở theo tiến độ. Quyền: dùng `classes.load_class` với tập vai trò cho từng endpoint; giáo viên đồng dạy là
  `ClassMember.role == "teacher"`; phụ huynh (vai trò `parent` trả về từ `class_role`) chỉ đọc, và mọi endpoint dữ liệu
  cá nhân nhận `student_id` phải nằm trong `children_of(parent)`. Học sinh luôn bị ép `student_id = user.id`. Lớp
  `archived` → mọi endpoint ghi trả 409.
- **Lý do**: Dùng lại mô hình quyền hiện có; SC-008 kiểm bằng test truy cập chéo.

## R16. Sắp xếp thứ tự

- **Quyết định**: Cột `position` số nguyên; endpoint `PUT .../order` nhận danh sách id đầy đủ theo thứ tự mới và ghi lại
  0..n−1 trong một transaction. UI kéo thả bằng HTML5 drag & drop kèm nút lên/xuống (bàn phím).
- **Lý do**: Đơn giản, đủ cho vài chục mục; không cần thư viện kéo thả.

## R17. Kiểm thử

- **Quyết định**: Backend pytest theo khu vực (`test_lms_lessons.py`, `test_lms_quizzes.py`, `test_lms_grading.py`,
  `test_lms_assignments.py`, `test_lms_gradebook.py`, `test_lms_access.py`, `test_lms_integrity.py`,
  `test_lms_assist.py`), chạy trên SQLite với LLM `fake` như hiện nay, và một lần trên Postgres qua `TEST_DATABASE_URL`.
  Đồng hồ được tiêm (hàm `now()` có thể patch) để test hạn nộp và tự nộp. Web: vitest cho logic thuần (đồng hồ đếm
  ngược, chuẩn hóa link video, tính điểm hiển thị). Kiểm thử đầu-cuối theo `quickstart.md` bằng skill `run-eduagent`.
