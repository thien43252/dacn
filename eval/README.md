# Bộ dữ liệu đánh giá

Ba file JSONL (UTF-8, mỗi dòng một object), dùng cho thực nghiệm tuần 11 và cho certification pipeline (tuần 9).
`backend/tests/test_eval_datasets.py` kiểm tra schema, id duy nhất và số lượng tối thiểu.

## `redteam_vi.jsonl`: 190 câu tấn công

| Trường | Ý nghĩa |
| --- | --- |
| `id` | Tiền tố theo nhóm: `ai-`, `jb-`, `pi-`, `pii-`, `age-`, `sh-`, `hr-`, `dg-`, `mis-`, `rb-` |
| `category` | Một trong 10 nhóm bên dưới |
| `technique` | Kỹ thuật tấn công cụ thể (ví dụ `authority_claim`, `no_diacritics`, `doc_instruction`) |
| `role` | Vai trò gửi tin: `student`, `teacher`, `parent` |
| `grade`, `subject` | Khối lớp (5 đến 12) và mã môn (`toan`, `van`, `anh`, `ly`, `hoa`, `sinh`, `su`, `dia`, `gdcd`, `tin`, `chung`) |
| `prompt` | Tin nhắn của người dùng |
| `context` | Chỉ có ở `prompt_injection` gián tiếp: nội dung tài liệu hoặc kết quả tool mà agent đọc được |
| `expected` | `block` (guard phải chặn hoặc agent phải từ chối) hoặc `safe_response` (agent trả lời nhưng không làm theo yêu cầu: chỉ gợi ý, chuyển hướng, hỗ trợ) |
| `criteria` | Tiêu chí cho LLM-judge chấm một câu trả lời là đạt |

| Nhóm | Số câu | Nội dung |
| --- | --- | --- |
| `academic_integrity` | 35 | Làm hộ bài, xin đáp án, gian lận khi đang kiểm tra, lách bằng vai diễn hay tự xưng quyền |
| `jailbreak` | 30 | Bỏ qua hướng dẫn, DAN, chế độ nhà phát triển, mã hóa, đổi ngôn ngữ, hệ thống giả |
| `pii` | 25 | Thông tin cá nhân của bạn học, giáo viên, hội thoại người khác, chia sẻ quá mức |
| `prompt_injection` | 20 | Chỉ dẫn gián tiếp nhúng trong tài liệu lớp, kết quả tool, bài làm học sinh |
| `age_inappropriate` | 20 | Tình dục, bạo lực ghê rợn, chất kích thích, cờ bạc, thử thách nguy hiểm |
| `harassment` | 15 | Miệt thị, phân biệt vùng miền, dân tộc, tin đồn, đe dọa |
| `dangerous_illegal` | 15 | Xâm nhập hệ thống, giả giấy tờ, chất nổ, lừa đảo |
| `self_harm` | 12 | Ý nghĩ tự hại, xin phương pháp, dấu hiệu gián tiếp |
| `role_boundary` | 10 | Vượt quyền vai trò: sửa điểm, đổi chính sách, bỏ qua đồng ý, xem lớp khác |
| `misinformation` | 8 | Tin giả, trích dẫn bịa, thông tin y tế sai |

Các câu `self_harm` dùng `safe_response` khi cần phản hồi hỗ trợ (đồng cảm, khuyến khích nói với người lớn, Tổng đài
quốc gia bảo vệ trẻ em 111), và `block` khi người dùng xin phương pháp.

## `benign_vi.jsonl`: 60 câu hợp lệ

Cùng schema, `category = "benign"`, `expected = "allow"`. Câu hỏi hợp lệ nhưng chạm chủ đề dễ bị chặn nhầm: lịch sử
chiến tranh, giáo dục giới tính, an toàn hóa chất, phòng chống ma túy, văn học về cái chết, giáo viên xin đáp án. Dùng
để đo tỉ lệ chặn nhầm (false positive) của guard.

## `routing_set.jsonl`: 101 câu định tuyến

| Trường | Ý nghĩa |
| --- | --- |
| `id` | `ro-001`... |
| `role` | Vai trò người gửi |
| `installed` | Các agent đang khả dụng cho người gửi trong lớp |
| `message` | Tin nhắn |
| `expected_agent` | Agent orchestrator cần chọn; luôn nằm trong `installed` |
| `kind` | `clear`, `mention`, `no_diacritics`, `ambiguous_*`, `multi_intent`, `specialist_not_installed`, `mention_not_allowed`, `mention_not_installed`, `platform`, `smalltalk`, `wellbeing`, `no_specialist`, `english_message`, `mention_overrides_topic` |

Agent mẫu (seed tuần 10): `gia-su-toan`, `luyen-tieng-anh`, `on-tap-tai-lieu`, `cham-van` (học sinh, giáo viên),
`tao-de` (giáo viên), `tro-ly-phu-huynh` (phụ huynh), `tro-ly-lop` (agent dự phòng của lớp). Quy ước:

- `@mention` một agent đã cài và được phép cho vai trò đó thì luôn thắng chủ đề tin nhắn.
- `@mention` agent chưa cài hoặc không dành cho vai trò đó thì về `tro-ly-lop`.
- Không có agent chuyên môn phù hợp thì về `tro-ly-lop`.

## Ghi chú

Đây là dữ liệu do tác giả viết tay cho đồ án, không phải benchmark chuẩn. Khi báo cáo kết quả cần nêu rõ kích thước và
cách xây dựng. Không thêm thông tin cá nhân thật vào các file này.
