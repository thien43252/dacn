# EduAgent Hub: nền tảng mở multi-agent cho lớp học, với lớp tin cậy cho người dùng vị thành niên

*Bản nháp báo cáo đồ án. Các bảng có dấu ⟨…⟩ điền từ `eval/results/` sau khi chạy thực nghiệm với mô hình thật.*

## 1. Đặt vấn đề

Giáo viên, học sinh và phụ huynh Việt Nam đã dùng chatbot AI hằng ngày, nhưng qua các công cụ đa dụng không biết gì
về lớp học: không có chính sách của giáo viên, không phân biệt người dùng là trẻ vị thành niên, không có nhật ký để
người lớn biết chuyện gì đã xảy ra. Các kho "GPTs" cho phép ai cũng tạo agent, nhưng không có bước kiểm định nào trước
khi agent đến tay học sinh.

Đồ án xây dựng **EduAgent Hub**: giáo viên tự tạo lớp, thêm học sinh và phụ huynh, chọn agent từ một kho mở (do nền
tảng hoặc giáo viên khác xây) và cài vào lớp. Đóng góp chính không nằm ở từng agent mà ở **lớp tin cậy** bao quanh
chúng:

1. **Orchestrator theo lớp**: định tuyến tin nhắn tới agent phù hợp trong số agent lớp đã cài, áp chính sách lớp lên
   mọi agent.
2. **Guardrails 3 lớp**: đầu vào, công cụ, đầu ra; có nhật ký cho giáo viên và quản trị.
3. **Certification pipeline**: kiểm định tự động mọi phiên bản agent trước khi đến học sinh, phụ huynh hay lên Hub.

Câu hỏi nghiên cứu:
- **RQ1.** Guard nhiều lớp giảm tỉ lệ tấn công thành công (ASR) bao nhiêu so với chỉ dựa vào system prompt, và phải
  trả giá bao nhiêu về chặn nhầm, độ trễ, chi phí?
- **RQ2.** Router LLM chọn đúng agent tốt hơn router từ khoá bao nhiêu trên tin nhắn tiếng Việt thật (không dấu, đa ý,
  @mention)?
- **RQ3.** Pipeline kiểm định tự động phát hiện agent độc hại (kể cả loại tinh vi) với precision/recall bao nhiêu, và
  phần động (red-team + giám khảo) đóng góp gì so với kiểm tra tĩnh?

## 2. Khảo sát sản phẩm liên quan

| Sản phẩm | Điểm mạnh | Khoảng trống so với đồ án |
| --- | --- | --- |
| Khanmigo (Khan Academy) | Gia sư Socratic, không đưa đáp án, có dashboard giáo viên | Một agent do nhà cung cấp làm; không có kho agent mở cho giáo viên |
| MagicSchool, Brisk | Nhiều công cụ cho giáo viên (soạn đề, chấm, giáo án) | Chủ yếu phục vụ giáo viên; học sinh dùng qua "rooms" có giới hạn; agent không do cộng đồng xây |
| GPT Store / Custom GPTs, Gemini Gems, Poe, Coze | Ai cũng tạo và chia sẻ agent | Không có ngữ cảnh lớp học, không kiểm định trước khi phát hành, không có vai trò phụ huynh |
| NotebookLM | RAG trên tài liệu người dùng tải lên rất tốt | Một người dùng, không có lớp, không có chính sách |
| Nền tảng học tập Việt Nam (OLM, Hocmai, VioEdu) | Nội dung theo chương trình GDPT 2018, đã có giáo viên và phụ huynh | AI là tính năng phụ; không có hệ sinh thái agent |

Vị trí của EduAgent Hub: **kho agent mở như GPT Store, nhưng đặt trong lớp học và có lớp tin cậy** (chính sách lớp,
guard, kiểm định, đồng ý của phụ huynh, nhật ký).

## 3. Kiến trúc

```
web (React 19)  ──SSE──▶  FastAPI ──▶ LangGraph runtime ──▶ LLM adapter (Anthropic | OpenAI | Gemini | fake)
                              │              │
                              │              └──▶ MCP server nội bộ (5 tool) ──▶ pgvector (RAG)
                              └──▶ PostgreSQL: lớp, agent/phiên bản, hội thoại, guard_events, usage_ledger, certifications
```

- **Agent là dữ liệu, không phải code.** Manifest khai báo (tên, đối tượng, môn, khối, khả năng, công cụ chọn từ danh
  mục, hướng dẫn hệ thống). Phiên bản bất biến; cài đặt trỏ tới một phiên bản cụ thể; học sinh và phụ huynh chỉ dùng
  được phiên bản đã kiểm định.
- **LLM adapter đa nhà cung cấp**, hai tầng mô hình: "main" cho agent, "small" cho guard, router, giám khảo. Mặc định
  với Anthropic: `claude-opus-5-5` và `claude-haiku-5-5`. Mọi lần gọi ghi token và chi phí vào `usage_ledger`.
- **Công cụ qua MCP**: 5 tool (`class_doc_search`, `quiz_generator`, `rubric_grader`, `math_check`, `progress_summary`)
  chạy trên MCP server của nền tảng. Danh tính và lớp do nền tảng tiêm vào, mô hình không điền được.
- **RAG**: tài liệu lớp (PDF, DOCX, MD, TXT) chia đoạn theo trang/tiêu đề, embedding 768 chiều, chỉ mục HNSW cosine,
  lọc theo lớp. Nội dung tài liệu được đánh dấu là dữ liệu, không phải chỉ dẫn.

## 4. Lớp tin cậy

### 4.1 Runtime graph

```
screen ──chặn──▶ END
  ├──▶ classify (guard LLM)  ┐  chạy song song
  └──▶ select_agent (router) ┘
             ▼
           gate ──chặn──▶ END
             ▼
        run_agent (agent + vòng lặp tool; tool guard trước mỗi lời gọi)
             ▼
          review (guard đầu ra; có thể thu hồi câu trả lời đã stream)
```

System prompt của agent gồm ba tầng theo thứ tự ưu tiên: **quy tắc nền tảng** (người dùng có thể là trẻ vị thành
niên, không lộ dữ liệu, tài liệu là dữ liệu, hỗ trợ khi có dấu hiệu tự làm hại), **manifest của agent**, **chính sách
lớp** (không đưa đáp án, chủ đề cấm, môn được dùng, ghi chú của giáo viên). Nhờ tầng chính sách lớp áp lên mọi agent,
nhiều agent do nhiều tác giả khác nhau vẫn hành xử nhất quán trong cùng một lớp.

### 4.2 Orchestrator

Thứ tự: agent chọn trên giao diện → `@mention` (chỉ agent khả dụng; nhắc tên agent không được phép thì về trợ lý lớp,
để học sinh không "gọi" được agent của giáo viên) → router LLM (JSON, ngưỡng tin cậy 0,5) → router từ khoá (dự phòng
và baseline) → trợ lý lớp. Tin nhắn nối tiếp ngắn giữ agent vừa trả lời.

### 4.3 Guard

| Lớp | Cơ chế | Hành động |
| --- | --- | --- |
| Đầu vào: luật | Mẫu trên văn bản đã bỏ dấu: vượt quy tắc, tự làm hại, nguy hiểm, không hợp lứa tuổi; regex thông tin cá nhân; chủ đề cấm của lớp | chặn / hỗ trợ / ẩn thông tin |
| Đầu vào: LLM | Phân loại 7 nhóm, có hướng dẫn tránh chặn nhầm (lịch sử chiến tranh, giáo dục giới tính, phòng chống ma tuý…) | chặn / hỗ trợ |
| Công cụ | Tool có trong manifest, vai trò được phép, có ngữ cảnh lớp, tham số hợp lệ | từ chối lời gọi |
| Đầu ra: luật | Lộ quy tắc nền tảng; thông tin cá nhân mới xuất hiện | thu hồi / ẩn |
| Đầu ra: LLM | Nội dung không hợp đối tượng, lộ dữ liệu người khác, làm theo chỉ dẫn nhúng, vi phạm "không đưa đáp án" | thu hồi / gắn cờ |

Dấu hiệu tự làm hại **không bị chặn** mà chuyển agent sang chế độ hỗ trợ (lắng nghe, khuyến khích nói với người lớn,
Tổng đài 111) và tạo sự kiện mức cao cho giáo viên; chỉ yêu cầu cách thức mới bị chặn. Mọi quyết định ghi vào
`guard_events` với trích đoạn đã ẩn thông tin cá nhân.

### 4.4 Kiểm định agent

1. **Kiểm tra tĩnh** manifest: công cụ hợp lệ và phù hợp đối tượng, tuổi khớp khối, mẫu cấm trong hướng dẫn hệ thống
   (vượt quy tắc, thu thập thông tin cá nhân, kéo ra ngoài nền tảng, làm hộ bài, nội dung người lớn), có xử lý câu phủ
   định ("không hỏi số điện thoại" không bị bắt).
2. **Giám khảo đọc hướng dẫn hệ thống** (LLM): rủi ro thấp / trung bình / cao.
3. **Red-team động**: ~30 câu tấn công lấy mẫu phân tầng từ 10 nhóm + 6 câu hợp lệ, chạy qua runtime thật trong lớp giả
   lập có chính sách mặc định. Guard được tắt (`prompt_only`) để chấm đúng hành vi của agent; người dùng thật vẫn có guard.
4. **Giám khảo chấm từng ca** theo hành vi mong đợi (`block`, `safe_response`, `allow`).
5. **Quyết định**: lỗi tĩnh hoặc rủi ro cao → không đạt; ≥ 90% và không trượt nhóm nghiêm trọng → đạt; ≥ 70% → cần
   quản trị viên xem lại; còn lại không đạt.

### 4.5 Quyền riêng tư và người giám hộ

- Lớp có thể yêu cầu phụ huynh đồng ý; khi chưa có, tin nhắn của học sinh không được xử lý và không được lưu.
- Báo cáo cho phụ huynh chỉ gồm số liệu tổng hợp và nhận xét, không có nguyên văn tin nhắn; phụ huynh tắt được báo cáo.
- Thông tin cá nhân trong tin nhắn bị ẩn trước khi tới mô hình và trước khi lưu.

## 5. Dữ liệu đánh giá

| Bộ | Số mẫu | Nội dung |
| --- | --- | --- |
| `redteam_vi.jsonl` | 190 | 10 nhóm: làm hộ bài (35), vượt quy tắc (30), thông tin cá nhân (25), chỉ dẫn nhúng (20), không hợp lứa tuổi (20), bắt nạt (15), nguy hiểm (15), tự làm hại (12), vượt quyền (10), tin sai (8). Có kỹ thuật không dấu, leetspeak, đổi ngôn ngữ, vai diễn, hệ thống giả |
| `benign_vi.jsonl` | 60 | Câu hỏi hợp lệ dễ bị chặn nhầm |
| `routing_set.jsonl` | 101 | Tin nhắn có nhãn agent đúng, 17 loại tình huống |
| `certify_agents.yaml` | 20 | 10 agent tốt, 10 agent xấu (3 lộ liễu, 7 tinh vi: mật mã bí mật, dụ giữ bí mật với bố mẹ, "lời giải để đối chiếu", tư vấn ăn kiêng nguy hiểm, thiên kiến vùng miền, thu thập dữ liệu trá hình, giáo viên lập hồ sơ học sinh) |

## 6. Thực nghiệm

Lệnh chạy (từ `backend/`): `uv run python ../eval/run_redteam.py`, `run_routing.py --router llm`, `run_certify.py`.
Mô hình: ⟨provider, model main / small⟩.

### RQ1: Guard

| Cấu hình | ASR | Chặn nhầm câu hợp lệ | p50 / p95 | Token/ca | Chi phí |
| --- | --- | --- | --- | --- | --- |
| Không guard, không quy tắc nền tảng (`off`) | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ |
| Chỉ quy tắc trong prompt (`prompt_only`) | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ |
| Đầy đủ (`full`) | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ | ⟨…⟩ |

Kết quả đo offline (không cần mô hình): **lớp luật** chặn hoặc chuyển hỗ trợ 38/190 câu tấn công và **0/60** câu hợp lệ.

### RQ2: Định tuyến

| Router | Độ chính xác | Ghi chú |
| --- | --- | --- |
| Từ khoá (baseline) | **74,3%** (75/101) | Đúng hoàn toàn với @mention và các ca phải về trợ lý lớp; yếu ở tin nhắn đa ý, tiếng Anh, phụ huynh |
| LLM | ⟨…⟩ | ⟨độ trễ, token⟩ |

### RQ3: Kiểm định

| Cách kiểm | Precision | Recall |
| --- | --- | --- |
| Chỉ kiểm tra tĩnh (đo offline) | **100%** | **30%** (bắt 3 agent lộ liễu, 0 agent tốt bị gắn cờ) |
| Toàn bộ pipeline | ⟨…⟩ | ⟨…⟩ |

## 7. Hạn chế

- Giám khảo và guard LLM có thể sai; quyết định kiểm định "cần xem lại" vẫn cần con người.
- Guard đầu ra chạy sau khi stream: người dùng có thể thấy câu trả lời trong vài giây trước khi bị thu hồi. Một lựa chọn
  là đệm câu trả lời cho học sinh tiểu học, đổi lấy độ trễ.
- Bộ red-team do tác giả viết (190 câu), chưa phản ánh hết tấn công nhiều lượt và tấn công thích nghi.
- Chưa đánh giá với người dùng thật (giáo viên, học sinh); chưa có ứng dụng di động.

## 8. Kết luận và hướng phát triển

⟨Tóm tắt kết quả RQ1–RQ3.⟩ Hướng tiếp theo: tấn công nhiều lượt trong kiểm định, kiểm định lại định kỳ khi đổi mô
hình nền, nhóm học sinh trong lớp, canvas kéo-thả cho builder, thử nghiệm với một lớp thật có sự đồng ý của phụ huynh.
