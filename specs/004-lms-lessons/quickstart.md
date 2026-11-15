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
