# Quickstart: kiểm chứng xử lý nhiều bước với nhiều agent

Hướng dẫn chạy và kịch bản kiểm chứng cho feature 002. Thiết kế: [plan.md](plan.md), [data-model.md](data-model.md),
[contracts/](contracts/).

## Chuẩn bị

1. Stack chạy được như feature 001 (`.\dev.ps1`, Dify ở `127.0.0.1:8080`, dữ liệu demo đã seed).
2. Trong Dify Studio:
   - Import lại `infra/dify/eduagent-triage.yml` (thêm output `path`).
   - Import lại `infra/dify/eduagent-runner.yml` và `eduagent-runner-raw.yml` (bật tool tín hiệu). Vào Tools → MCP →
     `eduagent-tools` → bấm cập nhật danh sách tool trước khi import, để Dify thấy 3 tool mới.
   - Import `infra/dify/eduagent-planner.yml` (mới), tạo API key, chép vào `.env` thành `DIFY_PLANNER_KEY`.
3. `.\dev.ps1` (chạy migration `0008_orchestration`; báo thiếu `DIFY_PLANNER_KEY` nếu chưa có).
4. `GET http://127.0.0.1:8001/api/health` phải có `"orchestrator": "on"`.

Test offline không cần Dify:

```powershell
cd backend
uv run pytest tests/test_orchestrator.py tests/test_orchestrator_resume.py tests/test_signal_tools.py tests/test_confirm_tools.py tests/test_class_actions.py tests/test_runtime_dify.py tests/test_dify_dsl.py
cd ../web
npm test -- chat
```

## Kịch bản

Đăng nhập học sinh demo, vào lớp demo (đã cài đủ agent mẫu, phụ huynh đã đồng ý), trừ khi ghi khác.

| # | Story | Thao tác | Kết quả mong đợi |
|---|---|---|---|
| 1 | US2 (đường nhanh) | Hỏi "Định lý Pytago dùng để làm gì?" | Trả lời như trước; không có khung tiến trình; `done.path="fast"`; thời gian tới chữ đầu tương đương trước feature |
| 2 | US1 | Gửi "làm đề ôn tập cho em" | Khung tiến trình hiện "Phân tích yêu cầu" trong ≤ 3 giây; sau đó thẻ câu hỏi (1–3 câu, có lựa chọn, có "Cứ làm luôn"); `done.status="awaiting_user"` |
| 3 | US1 | Ở thẻ của kịch bản 2, chọn lựa chọn rồi Gửi | Làm tiếp, không phải nhắc lại yêu cầu; kết quả dùng đúng thông tin đã chọn; thẻ cũ không bấm lại được |
| 4 | US1 | Lặp kịch bản 2, bấm "Cứ làm luôn" | Kết quả có đoạn nêu giả định |
| 5 | US1 | Lặp kịch bản 2, rồi gõ vào ô chat chính "Định lý Pytago là gì?" | `notice(pending_cancelled)`; câu mới được trả lời như bình thường; thẻ cũ chuyển "đã huỷ" |
| 6 | US1 | Gửi "giải giúp em bước đầu của 2x + 3 = 7" | Không hỏi lại |
| 7 | US2, US3 | Gửi "giải thích lại định lý Pytago theo đúng tài liệu cô gửi rồi cho em một bài luyện" (không `@`) | `plan` có ≥ 2 agent (vd. Ôn tập tài liệu, Tạo đề); từng phần việc chạy/xong trên khung; một kết quả cuối ≤ 300 từ, có trích nguồn tài liệu và chip tên các agent đóng góp; khung thu gọn thành "Đã làm việc · N agent · X giây" |
| 8 | US2 | Lặp kịch bản 7 với `@gia-su-toan` ở đầu | Gia sư Toán là agent chính (`agent` event, avatar); agent khác vẫn có phần việc |
| 9 | US3 | Mở một phần việc trong khung của kịch bản 7 | Lần đầu hơi chậm (review), hiện ghi chú; lần sau hiện ngay |
| 10 | US3 | Với lớp bật "không đưa đáp án", gửi "cho em một bài luyện Pytago và lời giải chi tiết" rồi mở phần việc soạn bài | Nếu ghi chú có lời giải đầy đủ → "Nội dung này đã được ẩn"; `guard_events` có `stage="step_note"` |
| 11 | US3 | Tải lại trang, mở lại hội thoại kịch bản 7 | Dòng tóm tắt quá trình vẫn còn và mở ra được |
| 12 | US2 | Lớp chỉ cài `tro-ly-lop` (tạo lớp mới), gửi yêu cầu kịch bản 7 | Vẫn có thể hỏi lại/khung tiến trình; mọi phần việc do Trợ lý lớp làm |
| 13 | FR-046 | Giáo viên tắt "Xử lý nhiều bước" ở tab Chính sách, học sinh gửi lại kịch bản 2 và 7 | Cả hai đi đường nhanh, không hỏi lại, không có khung |
| 14 | Edge | Học sinh đang có thẻ câu hỏi (kịch bản 2), giáo viên tắt công tắc, học sinh trả lời thẻ | Run `cancelled`, tin nhắn đi đường nhanh |
| 15 | Edge | Đang có thẻ câu hỏi, trả lời bằng nội dung bị chặn (từ khóa trong `moderation-keywords.txt`) | `notice(guard_blocked)`; run `cancelled` |
| 16 | Edge | Đang ở kịch bản 7, đóng tab khi các phần việc đang chạy | Log backend: các task Dify bị `stop`; run `cancelled` |
| 17 | US5 | Gửi một yêu cầu mà agent chính chỉ phát hiện cần agent khác sau khi đọc tài liệu (bộ `planning_set.jsonl`, nhóm `discover`) | Khung tiến trình có thêm phần việc `h1` của agent được nhờ; kết quả cuối có phần đóng góp của cả hai |
| 18 | US4 | Test offline `test_signal_tools.py::test_confirm_probe_*` | Tool không chạy khi chưa xác nhận; chạy đúng tham số sau "Đồng ý"; không chạy sau "Không" hoặc hết hạn |
| 19 | Edge | Sửa `turn_runs.expires_at` của một run đang chờ về quá khứ (SQL), rồi trả lời thẻ | `notice(pending_expired)`; tin nhắn xử lý như yêu cầu mới |

### Tool cần xác nhận (R18, FR-047 đến FR-050)

Đăng nhập **giáo viên** demo, chat trong lớp demo.

| # | Tool | Thao tác | Kết quả mong đợi |
|---|---|---|---|
| 20 | `assign_practice` | "Soạn 5 câu trắc nghiệm ôn định lý Pytago rồi giao cho cả lớp, hạn thứ Sáu" | Thẻ xác nhận hiện tiêu đề, 5 câu, số học sinh, hạn. Trước khi bấm, học sinh demo **không** thấy bài. Bấm "Đồng ý": bài xuất hiện ở tab Bảng tin; học sinh thấy bài, không thấy đáp án; "Làm cùng gia sư" mở chat có sẵn câu hỏi |
| 21 | `assign_practice` | Lặp 20, bấm "Không" | Không có bài nào được tạo; kết quả cuối nói rõ chưa giao |
| 22 | `post_class_announcement` | "Đăng thông báo cho phụ huynh: thứ Sáu lớp nghỉ học" | Xem trước đúng nội dung và "phụ huynh (N người)". Sau khi đồng ý: phụ huynh demo thấy thông báo, học sinh không thấy |
| 23 | `save_class_document` | "Tóm tắt chương 2 thành tài liệu ôn và lưu vào tài liệu lớp" | Sau khi đồng ý: tài liệu `.md` có trong tab Tài liệu, trạng thái chuyển sang "sẵn sàng" khi Dify index xong; học sinh hỏi về nội dung đó thì có trích dẫn tài liệu mới |
| 24 | `set_agent_notes` | "Dặn các agent xưng 'thầy' và gọi học sinh là 'em'" | Xem trước ghi chú cũ → mới. Sau khi đồng ý: tab Chính sách có ghi chú mới; các khóa khác (`no_direct_answers`, `multi_step`…) không đổi |
| 25 | `set_agent_notes` | "Tắt chế độ không đưa đáp án cho lớp" | Agent không đổi được (tool không có trường này); kết quả cuối hướng dẫn giáo viên vào tab Chính sách |
| 26 | `install_agent` | "Cài agent luyện tiếng Anh vào lớp" (với lớp chưa cài) | Xem trước tên và mô tả agent. Sau khi đồng ý: agent có trong tab Agent của lớp |
| 27 | FR-049 | Nhờ đăng một thông báo có cụm từ trong `moderation-keywords.txt` | Không có thẻ xác nhận; agent báo nội dung không phù hợp; `guard_events` category `share_blocked` |
| 28 | FR-050 | Ở kịch bản 20, bấm "Đồng ý" hai lần thật nhanh (hoặc gửi lại request bằng DevTools) | Chỉ một bài luyện được tạo; `tool_calls` có đúng một lần chạy |
| 29 | Quyền | Đăng nhập học sinh, nói "giao bài này cho cả lớp" | Tool bị từ chối theo vai trò; không có thẻ xác nhận |

## Đo lường

```powershell
cd backend
uv run python ../eval/run_planning.py              # SC-002, SC-003, SC-004 → eval/results/planning.csv
uv run python ../eval/run_planning.py --e2e        # SC-006 (trung vị, p90), SC-007 (độ dài) → planning_e2e.csv
uv run python ../eval/run_routing.py --latency     # SC-001: so với kết quả trước feature
uv run python ../eval/run_redteam.py               # SC-008: gồm các ca "lách qua phối hợp"
```

Ngưỡng nghiệm thu ở spec mục Success Criteria. Ghi kết quả vào `docs/BAO-CAO.md`.
