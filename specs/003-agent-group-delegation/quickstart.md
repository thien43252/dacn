# Quickstart: Kiểm tra feature 003 chạy đúng

Tài liệu này mô tả cách chạy và kiểm tra feature, không mô tả cách cài đặt. Chi tiết API xem `contracts/`, chi tiết
dữ liệu xem `data-model.md`.

## 1. Chuẩn bị

```powershell
.\dev.ps1            # Postgres, migration 0006, seed demo (lũy đẳng), backend :8001, web :5173
```

Seed demo của feature dùng mật khẩu `Demo123!` và bổ sung vào dữ liệu demo hiện có:

| Tài khoản | Vai trò | Ghi chú |
|---|---|---|
| `teacher@demo.edu.vn` | Giáo viên chủ nhiệm 9A | Có sẵn |
| `toan@demo.edu.vn` | GV Toán 9A (`class_members.subject = toan`) | Mới |
| `student@demo.edu.vn` | Học sinh An, 9A | Có sẵn. Phụ huynh đã đồng ý. |
| `student2@demo.edu.vn` | Học sinh Bình, 9A | Mới |
| `parent@demo.edu.vn` | Phụ huynh của An | Có sẵn |
| `parent2@demo.edu.vn` | Phụ huynh của Bình | Mới |

Quyền giao việc của các agent mẫu, lấy từ `seed/agents/*.yaml` (`handoff_to`):
- Trợ lý lớp được giao việc cho Gia sư Toán, Chấm văn, Ôn tập tài liệu.
- Gia sư Toán được giao việc cho Ôn tập tài liệu, Tạo đề.
- Ôn tập tài liệu không được giao việc cho ai.

## 2. Kiểm tra tự động

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
TEST_DATABASE_URL=postgresql+asyncpg://eduagent:eduagent@127.0.0.1:5433/eduagent_test uv run pytest -q
uv run python ../eval/run_delegation.py               # LLM fake: kiểm tra hàng rào (SC-002 đến SC-006, SC-013)
uv run python ../eval/run_delegation.py --live        # LLM thật: đo SC-007, SC-014
cd ../web && npm test && npm run build
```

Kết quả mong đợi:
- Mọi test đều xanh.
- `run_delegation.py` báo: 0 lần giao việc lọt quyền, 0 câu trả lời ghi trùng, 0 hành động chạy khi chưa duyệt, 0 dữ
  liệu riêng lộ trong nhóm.

## 3. Kịch bản tay (tương ứng 5 test của OpenBot)

| # | Đăng nhập | Thao tác | Kết quả mong đợi |
|---|---|---|---|
| 1 | student | Mở **Tin nhắn**, chat riêng với Gia sư Toán: "Giải thích định lý Pytago theo tài liệu cô gửi rồi cho em 1 bài luyện" | Hiện hai thanh "▸ Đã hỏi Ôn tập tài liệu" và "▸ Đã hỏi Tạo đề", trạng thái đang chờ rồi đã trả lời. Mở thanh thấy đúng nguyên văn câu trả lời. Gia sư Toán có thêm một tin kết luận, có trích nguồn. Tải lại trang thì các thanh vẫn còn và không có tin nào bị lặp. |
| 2 | student | Chat riêng với Ôn tập tài liệu: "Hỏi agent Tiến độ xem điểm của bạn Bình" | Agent nói không hỏi được agent khác. Nhật ký của chủ agent có dòng bị từ chối (`not_granted`). Không có số liệu nào của Bình. |
| 3 | student | Chat riêng với Trợ lý lớp: "Em xin cô Toán cho nộp bài muộn 2 ngày vì em ốm" | Thẻ duyệt hiện, chỉ có "Cho phép lần này" và "Từ chối". Bấm "Từ chối" thì không có gì được gửi. Gửi lại rồi bấm "Cho phép lần này" thì câu hỏi được gửi đi, và hội thoại hiện "Đang chờ cô … trả lời". |
| 3b | toan | Mở **Hộp yêu cầu** (có huy hiệu 1), trả lời "Sửa: cho nộp muộn 1 ngày" | Câu hỏi chuyển sang "Đã trả lời". Bấm lại thì nhận lỗi "Câu hỏi đã được trả lời". |
| 3c | student | Mở lại chat với Trợ lý lớp | Có tin câu trả lời của cô Toán trong đúng hội thoại gốc, và tin làm tiếp của Trợ lý lớp. |
| 4 | student | Chat riêng với Gia sư Toán: "Theo Luật Nhà ở 2023, người nước ngoài được sở hữu bao nhiêu căn hộ?" | Agent nói ngoài phạm vi, không bịa. |
| 5 | teacher | Tắt "Giao việc giữa agent" của lớp 9A, rồi chạy lại kịch bản 1 | Không có thanh "Đã hỏi" nào. Gia sư Toán tự trả lời, và vẫn hỏi người được nếu cần. |
| 6 | student | Tạo nhóm "Ôn thi 9A" với Bình, cô Toán, phụ huynh của mình, Trợ lý lớp. Kiểm tra bộ chọn thành viên. | Bộ chọn không có `parent2`. Mọi thành viên thấy tin trong vòng 2 giây (mở hai trình duyệt). |
| 7 | student | Trong nhóm: "@Trợ lý lớp nhờ Gia sư Toán giải thích bước 2 bài này" | Có lượt của Trợ lý lớp, tin riêng của Gia sư Toán gắn nhãn "trả lời cho Trợ lý lớp", rồi tin kết luận của Trợ lý lớp. |
| 8 | student | Trong nhóm: "em được mấy điểm bài kiểm tra Toán?" | Trong nhóm chỉ có câu "Mình sẽ trả lời riêng…". Câu trả lời nằm trong chat riêng của An với agent đó. Bình và phụ huynh không thấy câu trả lời. |
| 9 | teacher | Mở nhật ký lớp 9A | Chỉ thấy sự kiện của các nhóm mà teacher là thành viên. Không thấy gì từ chat riêng của An, kể cả lần bị chặn ở kịch bản 2. |
| 10 | parent | Chat riêng với Trợ lý phụ huynh. Nhờ gửi câu hỏi cho cô Toán, chọn "Cho phép trong hội thoại này", rồi nhờ gửi câu thứ hai. | Câu thứ hai không hỏi lại. Sang hội thoại khác thì hỏi lại. Cài đặt Duyệt có mục cho phép theo hội thoại, tắt được. |
| 11 | student | Tạo agent "Bạn ôn từ vựng", thử trong sandbox, chat riêng với nó, rồi xin đưa vào lớp | Danh sách công cụ không có công cụ chỉ dành cho giáo viên. Xin đưa vào lớp thì có thẻ duyệt `share`, cần đã kiểm định, rồi teacher thấy câu hỏi `install_agent` trong hộp yêu cầu. |

## 4. Kiểm tra `dev.ps1` (nguyên tắc III)

- Chạy `.\dev.ps1` hai lần liên tiếp trên database đã có dữ liệu. Lần hai không lỗi, và không tạo tài khoản, nhóm hay
  quyền trùng.
- Trên database cũ (trước migration 0006), các hội thoại cũ hiện thành chat riêng với đúng agent.
