# Quickstart: kiểm chứng feature 004 (LMS)

## Chuẩn bị

```powershell
.\dev.ps1            # Postgres, migration (gồm 0007_lms), seed --ensure, backend :8001, web :5173
```

Seed `--ensure` bổ sung cho lớp demo của `teacher@demo.edu.vn`: 2 buổi học (một buổi đã công bố có PDF, video link,
quiz 5 câu, bài tập; một buổi nháp), agent nền tảng `tro-giang-lms` đã cài vào lớp, vài bài nộp mẫu của `student@` và
`student2@`. Mật khẩu `Demo123!`. Không cần API key (LLM `fake`), trừ bước đo SC-006/SC-009/SC-010 bằng mô hình thật.

Kiểm tra tự động:

```powershell
cd backend; uv run pytest -q tests/test_lms_*.py; uv run ruff check .; cd ..
cd web; npm test; npm run build; cd ..
cd backend; uv run python ../eval/run_exam_integrity.py   # SC-006, mô hình fake: phần luật
```

Kiểm thử trên trình duyệt: dùng skill `run-eduagent` cho các kịch bản dưới đây.

## Kịch bản

| # | Kịch bản | Bước | Kết quả mong đợi | Spec |
|---|---|---|---|---|
| 1 | Tạo và công bố buổi | GV vào lớp → tab "Buổi học" → tạo "Buổi 3", thêm PDF, link YouTube, đoạn văn bản, kéo đổi thứ tự → Công bố | Buổi ở nháp không hiện với HS; sau khi công bố HS thấy, mở PDF và phát video ngay trong trang | US1, FR-001–004 |
| 2 | Hẹn giờ mở | Đặt `publish_at` = 10 phút sau | HS thấy "sắp mở", không mở được nội dung | FR-002 |
| 3 | Tệp sai | Tải tệp `.exe` và video > 200 MB | Bị từ chối, thông báo nêu giới hạn | FR-005 |
| 4 | Cho agent đọc | Bật công tắc trên PDF → HS hỏi agent lớp về nội dung | Tài liệu hiện ở tab Tài liệu; câu trả lời dẫn nguồn tài liệu buổi | FR-006 |
| 5 | Làm quiz | HS làm quiz 15 phút, tải lại trang giữa chừng, nộp | Câu đã chọn còn nguyên, đồng hồ không đặt lại; câu khách quan có điểm ngay | US2, FR-011, FR-013, SC-003, SC-004 |
| 6 | Hết giờ | Tạo quiz 1 phút, HS bắt đầu rồi để hết giờ | Bài tự nộp; lần lưu sau hạn nhận 409 | FR-012 |
| 7 | Bí mật đáp án | Trong lúc làm và sau khi nộp (chế độ "sau khi đóng"), xem response `GET attempts/{id}` trong DevTools | Không có `answer_key`/`explanation` cho tới sau `close_at` | FR-014, SC-005 |
| 8 | Chấm lại | GV sửa đáp án một câu → Chấm lại | Điểm các lượt cập nhật, có dòng trong nhật ký điểm | FR-015 |
| 9 | Chặn đáp án | HS đang làm bài kiểm tra: dán câu hỏi vào (a) chat agent lớp, (b) chat agent tự tạo, (c) nhóm có agent | Cả ba bị từ chối kèm lý do; GV mở Nhật ký lớp không thấy sự kiện | US6, FR-028, SC-006 |
| 10 | Quiz luyện tập | Tắt `block_agents` → hỏi lại | Agent trả lời bình thường | FR-028 |
| 11 | Bài tập và nộp muộn | Bài tập trừ 10%/ngày, tối đa 30%; HS2 nộp muộn 2 ngày 3 giờ (chỉnh đồng hồ bằng test hoặc đặt hạn lùi), GV chấm 8, trả bài | Mức trừ 3, điểm cuối 5, HS thấy cả ba số sau khi trả | US3, FR-020a |
| 12 | Gia hạn riêng | GV gia hạn cho HS1, HS1 nộp sau hạn chung | Không bị đánh dấu muộn | FR-021 |
| 13 | Gợi ý câu hỏi | Lớp có `tro-giang-lms` → "Gợi ý câu hỏi" 5 câu trắc nghiệm từ PDF buổi | Câu nháp có đáp án, giải thích, trích đoạn tài liệu; chỉ vào quiz sau khi duyệt | FR-031, FR-032 |
| 14 | Gợi ý chấm | Bài tự luận của HS1 → "Gợi ý chấm" | Điểm theo tiêu chí, nhãn "gợi ý của AI"; HS chưa thấy gì cho tới khi GV duyệt và trả | FR-033, FR-034, SC-011 |
| 15 | Đồng ý | Phụ huynh của HS2 rút đồng ý → GV gợi ý chấm hàng loạt | Bài HS2 bị bỏ qua và liệt kê lý do; GV tự chấm được | FR-037 |
| 16 | Chưa cài agent | Gỡ `tro-giang-lms` khỏi lớp | Nút gợi ý ẩn/vô hiệu kèm hướng dẫn cài từ Hub; gợi ý đã duyệt vẫn còn | FR-038 |
| 17 | Sổ điểm | GV mở tab "Sổ điểm", đổi trọng số, tải CSV | Điểm khớp từng bài; CSV mở đúng tiếng Việt trong Excel | US4, FR-023, SC-007 |
| 18 | Việc cần làm | HS mở "Việc cần làm" | Bài chưa nộp của mọi lớp, sắp theo hạn | FR-024 |
| 19 | Phụ huynh | `parent@` mở trang của con | Thấy việc cần làm, điểm đã trả; đổi `student_id` sang HS khác → 403/404 | US5, FR-026, FR-027, SC-008 |
| 20 | Thông báo | GV trả bài | Chuông của HS tăng số chưa đọc, bấm tới bài | FR-025 |

## Đo tiêu chí có mô hình thật (tùy chọn)

- SC-006: `uv run python ../eval/run_exam_integrity.py --provider <tên>` → tỉ lệ từ chối mỗi kênh ≥ 95%.
- SC-009/SC-010: `uv run python ../eval/run_lms_assist.py --provider <tên>` trên tài liệu và bộ 30 bài tự luận có điểm
  giáo viên trong `eval/lms_assist/` → tỉ lệ câu duyệt không sửa ≥ 80%, độ lệch ≤ 1 điểm ở ≥ 80% bài.

## Kết quả kiểm thử đầu-cuối (2026-11-16)

Chạy trên stack của `.\dev.ps1` (Postgres `eduagent_main`, migration 0007, seed `--ensure`, LLM thật), trình duyệt
Chrome qua skill `run-eduagent`. Kịch bản không chạy trên trình duyệt được ghi rõ là "test tự động", tức là được kiểm
bằng pytest (310+ test, chạy trên cả SQLite và Postgres).

| # | Kết quả | Ghi chú |
|---|---|---|
| 1 | Đạt | Tab "Buổi học" đứng đầu; GV tạo buổi, tải PDF vào mục tài liệu; HS xem buổi đã công bố, video YouTube nhúng phát trong trang, tệp .md có nút tải |
| 2 | Test tự động | `test_lms_lessons.py` (publish_at tương lai → `locked`) |
| 3 | Đạt | Tệp `.exe` bị từ chối kèm danh sách định dạng; giới hạn dung lượng: `test_lms_files.py` |
| 4 | Test tự động | `test_lms_lessons.py` (bật/tắt "cho agent đọc", tìm kiếm thấy nội dung) |
| 5 | Đạt | Làm quiz 15 phút, đồng hồ chạy, "Đã lưu", tải lại trang vẫn còn lựa chọn; nộp có xác nhận; bài có tự luận hiện "Chờ chấm" |
| 6 | Test tự động | `test_lms_quizzes.py` (hết giờ tự nộp, lưu sau hạn → 409 `attempt_closed`) |
| 7 | Đạt | Response `POST attempts` của HS không có `answer_key`/`explanation`/`rubric`; mọi tổ hợp chế độ: `test_lms_quizzes.py` |
| 8 | Test tự động | `test_lms_quizzes.py` (chấm lại + `grade_audit`) |
| 9 | Đạt (kênh a) | HS đang làm bài dán câu 1 vào chat Trợ lý lớp → bị từ chối với thông báo bài kiểm tra; kênh b, c và nhật ký GV: `test_lms_integrity.py`, `eval/run_exam_integrity.py` (96/96 mỗi kênh với mô hình fake) |
| 10 | Test tự động | `test_lms_integrity.py` (`block_agents=false`) |
| 11 | Đạt | HS nộp lại qua UI (2 phiên bản); ví dụ trừ muộn 8 → 5: `test_lms_assignments.py`, `test_lms_grading.py` |
| 12 | Test tự động | `test_lms_assignments.py` (gia hạn riêng) |
| 13 | Test tự động | `test_lms_assist.py`; nút "Gợi ý câu hỏi" có trong màn soạn quiz |
| 14 | Đạt | Gợi ý chấm bằng `tro-giang-lms` (mô hình thật, 8/10 kèm lý do từng tiêu chí); HS không thấy điểm trước khi GV duyệt và trả; sau khi trả HS thấy điểm, trừ muộn, điểm cuối, nhận xét |
| 15 | Test tự động | `test_lms_assist.py` (`skipped_consent`, không gọi mô hình) |
| 16 | Test tự động | `test_lms_assist.py` (gỡ agent → 409, gợi ý cũ còn) |
| 17 | Đạt | Tab "Sổ điểm" đúng trạng thái/điểm; CSV có BOM, nhãn tiếng Việt |
| 18 | Đạt | "Việc cần làm" của HS2 liệt kê quiz chưa làm kèm hạn |
| 19 | Đạt | Phụ huynh xem việc cần làm và "Điểm đã trả" của con (8/10); đọc dữ liệu HS khác → 404; toàn bộ endpoint: `test_lms_access.py` |
| 20 | Đạt | Sau khi GV trả bài, chuông của HS có 1 thông báo "returned" |

Lỗi tìm thấy khi kiểm thử và đã sửa: gợi ý chấm chọn nhầm agent chấm Văn trong lớp Toán (nay ưu tiên agent đúng môn
hoặc "chung"); CSV ghi mã trạng thái tiếng Anh (nay ghi nhãn tiếng Việt).
