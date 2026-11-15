# Implementation Plan: Buổi học, tài liệu, video, bài tập và bài kiểm tra trong lớp (LMS)

**Branch**: phát triển trực tiếp trên `main` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-lms-lessons/spec.md`

## Summary

Biến mỗi lớp thành khóa học kiểu LMS: giáo viên tạo **buổi học** chứa tài liệu, video (tệp hoặc link), liên kết, văn
bản, **bài tập** (nộp, chấm, trả bài, trừ điểm muộn, gia hạn riêng) và **quiz/bài kiểm tra** (5 loại câu, hẹn giờ, chấm
tự động câu khách quan, snapshot đề, chấm lại). Có sổ điểm có trọng số và xuất CSV, trang "Việc cần làm", thông báo
trong ứng dụng, và chế độ chỉ xem cho phụ huynh.

Phần gắn với lõi AI:
- Runtime chặn mọi agent đưa đáp án cho học sinh đang làm bài kiểm tra, ở cả agent lớp, agent tự tạo, nhóm chat và
  handoff. Lần chặn ghi như sự kiện riêng tư, không hiện cho giáo viên.
- Agent Hub đã kiểm định (`tro-giang-lms`) gợi ý câu hỏi từ tài liệu buổi học và gợi ý chấm theo thang chấm. Gợi ý chỉ
  có hiệu lực sau khi giáo viên duyệt, và tôn trọng đồng ý của phụ huynh.

Cách làm: package mới `backend/app/lms/` và migration `0007_lms`. Dùng lại quyền lớp, kho tài liệu, guard, worker, tool
`quiz_generator`/`rubric_grader`. Phía web thêm feature `web/src/features/lms/`.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 7 + React 19 (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic 2, LangGraph (runtime hiện có), python-multipart;
web: Vite 8, plain CSS. **Không thêm dependency mới** (CSV tự viết, kéo thả bằng HTML5, video bằng thẻ `video`/`iframe`).

**Storage**: PostgreSQL 16 + pgvector (bảng mới ở [data-model.md](data-model.md)); tệp trên đĩa ở
`backend/data/uploads/lms/<class_id>/` (R2)

**Testing**: pytest + pytest-asyncio trên SQLite (LLM/embedder `fake`), chạy lại trên Postgres bằng `TEST_DATABASE_URL`;
vitest cho web; kiểm thử đầu-cuối bằng skill `run-eduagent` theo [quickstart.md](quickstart.md); eval
`eval/run_exam_integrity.py`, `eval/run_lms_assist.py`

**Target Platform**: chạy local trên Windows qua `dev.ps1` (Docker Postgres, uvicorn, Vite dev server), trình duyệt desktop

**Project Type**: web application (backend + web)

**Performance Goals**: chấm và hiện điểm câu khách quan < 2 giây sau khi nộp (SC-003); sổ điểm 40 × 20 < 3 giây
(SC-007); lưu câu trả lời < 500 ms để debounce 1 giây không dồn hàng

**Constraints**:
- Đáp án không bao giờ rời server trước thời điểm cho phép (SC-005).
- Không tin đồng hồ trình duyệt.
- Tệp ≤ 25 MB, video ≤ 200 MB, ghi theo khúc.
- Gợi ý AI không lọt tới học sinh hay phụ huynh (SC-011).
- Không đổi hợp đồng manifest agent.

**Scale/Scope**: quy mô demo/đồ án: vài lớp, ≤ 40 học sinh/lớp, ≤ 30 buổi/lớp, ≤ 50 câu/quiz. Khoảng 13 bảng mới, khoảng
45 endpoint, khoảng 12 màn hình hoặc tab web.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Nguyên tắc | Đánh giá | Trạng thái |
|---|---|---|
| I. Tài liệu và spec viết bằng tiếng Việt | spec, plan, research, data-model, contracts, quickstart đều viết tiếng Việt. Định danh code, tên API, khóa cấu hình giữ tiếng Anh | ĐẠT |
| II. Không tự commit | Không bước nào của plan commit. `tasks.md` không chứa task commit. Mọi thay đổi để trong working tree, chỉ đề xuất commit message tiếng Anh | ĐẠT |
| III. `dev.ps1` luôn chạy được | Có 3 thay đổi chạm bước chạy: (a) migration `0007_lms`, đã nằm trong `alembic upgrade head` mà `dev.ps1` vốn gọi; (b) seed thêm dữ liệu LMS và agent `tro-giang-lms` qua `seed_demo --ensure`, vẫn lũy đẳng; (c) thư mục tệp `data/uploads/lms`, tạo khi cần. Biến `LMS_MAX_FILE_MB`/`LMS_MAX_VIDEO_MB` là tùy chọn, có mặc định. Dù có thể không phải sửa `dev.ps1`, `tasks.md` MUST có task kiểm tra cú pháp và chạy `.\dev.ps1` sau khi xong, cập nhật `.env.example` (biến tùy chọn) và mục "Chạy local"/"Kiểm tra" của README (lệnh eval mới, dữ liệu demo LMS) | ĐẠT (có task bắt buộc) |

Đánh giá lại sau Phase 1: thiết kế không thêm service, container, cổng hay biến bắt buộc nào. Kết quả không đổi:
**ĐẠT**. Không có vi phạm cần giải trình.

## Project Structure

### Documentation (this feature)

```text
specs/004-lms-lessons/
├── plan.md              # File này
├── research.md          # Phase 0: R1–R17
├── data-model.md        # Phase 1: bảng, trạng thái, ràng buộc
├── quickstart.md        # Phase 1: 20 kịch bản kiểm chứng
├── contracts/
│   └── lms-api.md       # Phase 1: REST + hợp đồng runtime chặn đáp án
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── lms/                       # MỚI
│   │   ├── __init__.py
│   │   ├── models.py              # lessons, lesson_items, lms_files, quizzes, quiz_questions, quiz_attempts,
│   │   │                          # assignments, assignment_extensions, submissions, submission_versions,
│   │   │                          # ai_suggestions, content_views, notifications, grade_audit
│   │   ├── schemas.py             # schema tách riêng cho giáo viên / học sinh-phụ huynh (không có đáp án)
│   │   ├── access.py              # quyền theo vai trò lớp, ép student_id, phụ huynh → con (R15)
│   │   ├── files.py               # upload theo khúc, whitelist, FileResponse + Range (R2)
│   │   ├── lessons.py             # router buổi học, mục, thứ tự, lượt xem, cho agent đọc (R3, R4, R16)
│   │   ├── quizzes.py             # router quiz, câu hỏi, lượt làm, lưu nháp, nộp, kết quả, chấm lại
│   │   ├── grading.py             # hàm thuần: chấm từng loại câu (R7), trừ điểm muộn (R12), điểm quiz theo policy
│   │   ├── assignments.py         # router bài tập, nộp, gia hạn, chấm, trả bài
│   │   ├── gradebook.py           # sổ điểm, CSV, my-grades, todo (R11)
│   │   ├── integrity.py           # active_exams, so khớp stem/đáp án cho runtime (R8)
│   │   ├── assist.py              # agent Hub đủ điều kiện, gọi quiz_generator/rubric_grader, duyệt gợi ý (R9)
│   │   ├── notify.py              # tạo thông báo có dedupe, router /notifications (R10)
│   │   └── jobs.py                # việc định kỳ gọi từ worker.tick: chốt lượt quá hạn, nhắc hạn, publish_at
│   ├── runtime/graph.py           # SỬA: screen + review gọi lms.integrity; EXAM_BLOCKED
│   ├── orchestration/handoffs.py  # SỬA: câu trả lời handoff hiện cho học sinh đi qua kiểm tra bài kiểm tra
│   ├── orchestration/worker.py    # SỬA: tick gọi lms.jobs
│   ├── guard/classifier.py        # SỬA: review_output nhận ngữ cảnh câu hỏi bài kiểm tra đang mở
│   ├── knowledge/service.py       # SỬA: search(document_ids=...)
│   ├── tools/impl.py              # SỬA: QuizArgs/RubricArgs mở rộng, output có source/criteria
│   ├── config.py                  # SỬA: lms_max_file_mb, lms_max_video_mb
│   └── main.py                    # SỬA: include các router lms
├── migrations/versions/0007_lms.py   # MỚI
├── scripts/seed_demo.py           # SỬA: dữ liệu demo LMS, cài tro-giang-lms vào lớp demo
└── tests/
    ├── test_lms_lessons.py  test_lms_files.py  test_lms_quizzes.py  test_lms_grading.py
    ├── test_lms_assignments.py  test_lms_gradebook.py  test_lms_access.py
    └── test_lms_integrity.py  test_lms_assist.py  test_lms_notify.py

seed/agents/tro-giang-lms.yaml     # MỚI: agent nền tảng trợ giảng (quiz_generator, rubric_grader, class_doc_search)
eval/
├── exam_integrity.jsonl           # MỚI: ≥ 30 câu × 3 kênh (SC-006)
├── run_exam_integrity.py          # MỚI
├── lms_assist/                    # MỚI: tài liệu + 30 bài tự luận có điểm GV (SC-009, SC-010)
└── run_lms_assist.py              # MỚI

web/src/
├── api-client/lms.ts              # MỚI: kiểu + gọi API theo contracts/lms-api.md
├── features/lms/                  # MỚI
│   ├── LessonsTab.tsx             # tab "Buổi học" trong ClassDetailPage (GV: soạn; HS/PH: xem)
│   ├── LessonEditor.tsx  LessonView.tsx  ItemEditor.tsx  VideoPlayer.tsx  FileUpload.tsx
│   ├── QuizEditor.tsx  QuestionEditor.tsx  QuizTake.tsx  QuizResult.tsx  QuizResults.tsx
│   ├── AssignmentEditor.tsx  AssignmentView.tsx  SubmissionsTable.tsx  GradingPanel.tsx
│   ├── SuggestionReview.tsx       # duyệt câu hỏi / điểm AI gợi ý
│   ├── GradebookTab.tsx  TodoPage.tsx  MyGradesPage.tsx
│   ├── NotificationBell.tsx
│   ├── videoUrl.ts  countdown.ts  (+ *.test.ts)
│   └── lms.css
├── features/classes/ClassDetailPage.tsx   # SỬA: thêm tab Buổi học, Sổ điểm
├── features/family/ParentPages.tsx        # SỬA: mục việc cần làm và điểm của con
└── app/routes.ts                          # SỬA: /student/todo, /student/classes/:id/lessons/:lid, trang làm bài
```

**Structure Decision**: Giữ cấu trúc web application hiện có (`backend/` + `web/`). Toàn bộ nghiệp vụ LMS nằm trong
`backend/app/lms/` và `web/src/features/lms/`. Chỗ chạm vào module cũ chỉ là các điểm móc được liệt kê ở trên: runtime,
handoff, worker, knowledge search, tools và seed.

## Thứ tự triển khai đề xuất (đầu vào cho /speckit-tasks)

1. **Nền**: migration, models, `access.py`, `files.py`, `notify.py` khung. Đây là điều kiện cho mọi story.
2. **US1 (P1)**: buổi học và mục nội dung, video, cho agent đọc, lượt xem. Tab web.
3. **US2 (P1)**: quiz, `grading.py`, lượt làm có snapshot, lưu nháp, tự nộp (`jobs.py`), kết quả theo quyền, chấm lại,
   thống kê. Màn soạn và làm bài.
4. **US3 (P2)**: bài tập, nộp nhiều phiên bản, trừ điểm muộn, gia hạn, chấm và trả bài.
5. **US6 (P2)**: `integrity.py` và móc vào runtime/handoff, eval SC-006. Phần trợ lý AI: tool mở rộng, `assist.py`, agent
   seed, màn duyệt gợi ý, đồng ý.
6. **US4 (P2)**: sổ điểm, CSV, việc cần làm, điểm của tôi, nhắc hạn.
7. **US5 (P3)**: màn phụ huynh, test truy cập chéo SC-008.
8. **Hoàn thiện**: seed demo, `.env.example`, README, chạy `.\dev.ps1`, kiểm thử đầu-cuối theo quickstart.

Gợi ý giao việc (skill orchestrate):
- **Phù hợp để giao cho worker:** test bảng giá trị của `grading.py`, schema/CRUD theo mẫu router hiện có, UI soạn và
  xem, dataset eval, CSV.
- **Giữ lại tự làm:** `access.py`, `integrity.py` và các móc vào runtime, cơ chế snapshot/bí mật đáp án, `assist.py`,
  migration.

## Complexity Tracking

Không có vi phạm hiến pháp cần giải trình.
