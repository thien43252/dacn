# Research: Chuyển lõi agent sang Dify

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Ngày**: 2026-11-06

Mỗi mục ghi theo dạng Quyết định / Lý do / Phương án đã cân nhắc. Những điểm còn phụ thuộc vào hành vi thực tế
của phiên bản Dify cài đặt được gom ở mục R12 (spike) và PHẢI kiểm chứng trước khi làm phần tương ứng.

## R1. Chia lõi thành hai ứng dụng Dify: `eduagent-triage` và `eduagent-runner`

**Quyết định**: Mỗi lượt chat gọi hai ứng dụng Dify nối tiếp:

1. `eduagent-triage` (Workflow, chế độ blocking): kiểm duyệt đầu vào bằng bộ phân loại an toàn và định tuyến chọn
   agent, hai nhánh chạy song song trong workflow. Trả về JSON có cấu trúc: `verdict`, `category`, `reason`,
   `agent`, `route_reason`.
2. `eduagent-runner` (Chatflow, chế độ streaming): nhận hướng dẫn hệ thống của agent đã chọn, chạy Agent node có
   tool MCP, bật kiểm duyệt đầu vào/đầu ra cấp ứng dụng và gợi ý câu hỏi tiếp theo. Giữ bộ nhớ hội thoại.

**Lý do**:
- Định tuyến, phân loại an toàn và kiểm duyệt đều chạy trong Dify, đúng yêu cầu "dùng của Dify cung cấp".
- Tin nhắn bị chặn ở triage không bao giờ tới mô hình của agent (FR-008), vì backend không gọi runner nữa.
- Kết quả triage là dữ liệu có cấu trúc, nên backend ghi `guard_events` chính xác (FR-012) mà không phải đoán từ
  văn bản trả lời.
- Hướng dẫn hệ thống của agent (tối đa 8000 ký tự) chỉ gửi cho đúng agent đã chọn, không phải gửi cả danh sách.
- Hai bước giống cấu trúc hiện tại (classify ∥ route → gate → run_agent), nên thứ tự sự kiện SSE giữ nguyên.

**Phương án đã cân nhắc**:
- *Một chatflow duy nhất, Dify gọi HTTP về backend để lấy hướng dẫn hệ thống của agent đã chọn*: bị loại vì cần
  endpoint gọi ngược, logic chia đôi và khó test offline.
- *Một chatflow, gửi hướng dẫn hệ thống của mọi agent ứng viên làm input*: bị loại vì 7+ agent × 8000 ký tự vượt
  giới hạn input và tốn token.
- *Mỗi agent một ứng dụng Dify*: bị loại vì vi phạm FR-017 (agent giáo viên tạo phải chạy được ngay, không cấu
  hình tay) và khó quản lý phiên bản bất biến.

## R2. Định tuyến: LLM node có đầu ra cấu trúc thay vì Question Classifier

**Quyết định**: Trong `eduagent-triage`:
- Một Code node xử lý trước: nếu có `requested_agent` (UI chọn) hoặc `@mention` hợp lệ thì dùng luôn.
- Nếu không, một LLM node (model nhỏ) đọc danh sách agent ứng viên (`roster`: slug, tên, mô tả, khả năng, môn) và
  `previous_agent`, trả JSON `{"agent", "reason"}`.
- Một Code node cuối kiểm tra slug có trong `roster`; nếu không thì dùng `tro-ly-lop`.

Backend chỉ gửi các agent đã cài cho lớp/cá nhân và thuộc môn lớp cho phép (FR-003), nên Dify không thể chọn agent
ngoài danh sách đó.

**Lý do**: Question Classifier của Dify khai báo lớp tĩnh trong DSL. Danh sách agent thay đổi theo lớp và giáo
viên có thể tạo agent mới, nên cần danh sách truyền vào theo từng lượt.

**Phương án đã cân nhắc**: Question Classifier theo môn (toán, văn, anh…) rồi Code node map sang agent. Bị loại vì
một môn có nhiều agent (`gia-su-toan` và `tao-de`) và phân loại theo môn bỏ mất thông tin `capabilities`.

## R3. Guardrail: ba lớp đều do Dify cung cấp

**Quyết định**:

| Lớp | Thành phần Dify | Bắt được |
|---|---|---|
| Đầu vào 1 | Question Classifier "an toàn" trong `eduagent-triage` với các nhãn `safe`, `self_harm_risk`, `self_harm_method`, `jailbreak`, `dangerous`, `age_inappropriate` | Chặn hoặc chuyển sang chế độ hỗ trợ |
| Đầu vào 2 | Kiểm duyệt nội dung cấp ứng dụng của `eduagent-runner` (bộ từ khóa, và OpenAI Moderation nếu có khóa) | Từ khóa rõ ràng lọt qua bộ phân loại |
| Đầu ra | Kiểm duyệt đầu ra cấp ứng dụng của `eduagent-runner` (cùng cấu hình) | Câu trả lời vi phạm; Dify thay nội dung đã stream |

- Bộ luật chung cho mọi lớp (FR-013). Danh sách từ khóa nằm trong một file duy nhất
  `infra/dify/moderation-keywords.txt`, được nhúng vào DSL và được backend dùng lại để lọc câu hỏi gợi ý (R8).
- `self_harm_method` → chặn và trả lời hỗ trợ có Tổng đài 111. `self_harm_risk` → không chặn; backend truyền
  `safety_note=true` cho runner để agent trả lời ấm áp kèm 111 (FR-010), giống hành vi hiện nay.
- Mọi kết quả khác `safe` được backend ghi vào `guard_events` với `detector="dify_classifier"` (triage) hoặc
  `detector="dify_moderation"` (kiểm duyệt cấp ứng dụng), theo data-model.md.

**Lý do**: Đúng lựa chọn của người dùng (guard của Dify, luật chung). Question Classifier cho nhãn rõ ràng, đủ để
ghi nhật ký và để phân biệt self-harm với các loại chặn khác. Kiểm duyệt cấp ứng dụng là cơ chế duy nhất của Dify
có thể thay câu trả lời đã stream.

**Hệ quả được chấp nhận và sẽ đo ở bước so sánh (FR-024)**:
- Mất chủ đề cấm riêng từng lớp (đã chốt trong clarification).
- Kiểm duyệt "không đưa đáp án" cho học sinh trước đây do LLM review ở backend; giờ chỉ còn ở hướng dẫn hệ thống
  (chính sách lớp vẫn được đưa vào prompt). Tỉ lệ vi phạm sẽ thấy trong `run_certify.py` / `run_redteam.py`.
- Từ khóa của Dify so khớp chuỗi con, không bỏ dấu tiếng Việt như `rules.py`. File từ khóa vì vậy liệt kê cả dạng
  có dấu và không dấu.

**Phương án đã cân nhắc**:
- *Kiểm duyệt kiểu API extension trỏ về backend*: bị loại vì thực chất là guard của backend, trái yêu cầu.
- *LLM node review đầu ra sau Agent node*: bị loại vì Answer node đã stream xong trước khi review chạy, không thu
  hồi được qua cơ chế stream chuẩn.

## R4. Ẩn thông tin cá nhân vẫn chạy ở backend, trước khi gửi sang Dify

**Quyết định**: Backend giữ hàm `redact()` (số điện thoại, email, mật khẩu, số giấy tờ, địa chỉ) và áp dụng cho
tin nhắn trước khi gọi triage. Bản đã ẩn là bản duy nhất được lưu, gửi Dify và gửi tracing. Phần còn lại của
`app/guard/rules.py` và `app/guard/classifier.py` chỉ phục vụ engine cũ và bị xóa ở bước dọn dẹp.

**Lý do**: FR-011 và FR-005a yêu cầu thông tin cá nhân bị ẩn *trước khi* gửi tới Dify và trước khi vào bộ nhớ hội
thoại của Dify. Không thành phần nào của Dify chạy trước khi Dify nhận tin nhắn, nên việc này không thể giao cho
Dify. Đây là bảo vệ quyền riêng tư khi truyền dữ liệu, không phải guardrail nội dung.

## R5. Bộ nhớ hội thoại do Dify giữ

**Quyết định**: `conversations.dify_conversation_id` lưu mã hội thoại của runner. Lượt đầu gửi
`conversation_id=""`, lấy mã từ sự kiện stream đầu tiên rồi lưu lại. Lượt sau gửi lại mã đó, không gửi lịch sử.
Agent node bật memory với cửa sổ 12 tin nhắn (bằng `HISTORY_MESSAGES` hiện tại).

- Nếu Dify trả lỗi không tìm thấy hội thoại (Dify được dựng lại hoặc dữ liệu bị xóa), backend gửi lại lượt đó
  với hội thoại mới, cập nhật mã và phát sự kiện `notice` kiểu `context_reset`.
- Kiểm định và eval luôn dùng hội thoại mới cho mỗi tình huống (FR-019).
- `user` gửi sang Dify là id người dùng của nền tảng (FR-016).

**Lý do**: Đúng clarification. Trạng thái hội thoại Dify chỉ gồm văn bản đã ẩn thông tin cá nhân (R4).

**Lưu ý**: Đổi agent giữa chừng trong cùng một hội thoại vẫn dùng chung bộ nhớ; hướng dẫn hệ thống mới được truyền
qua input mỗi lượt nên agent mới vẫn đúng vai.

## R6. Tool: MCP qua HTTP, tham số `ctx` cố định bằng biến workflow

**Quyết định**:
- Mount MCP server của nền tảng (`app/tools/server.py`) vào FastAPI tại `/mcp` (streamable HTTP), xác thực bằng
  `Authorization: Bearer <MCP_TOKEN>`.
- Trong Agent node của runner, tham số `ctx` của cả 5 tool đặt ở chế độ **Fixed Value** = biến `{{#start.ctx#}}`.
  Mô hình không nhìn thấy và không điền `ctx`.
- Backend tạo handle sau khi triage chọn xong agent. Handle chứa người dùng, vai trò, lớp, agent và danh sách tool
  agent được cấp, có TTL 10 phút và bị hủy khi lượt kết thúc.
- Kiểm tra quyền tool (FR-014) và ghi `tool_calls` / `guard_events` chuyển vào handler MCP. Handler đẩy sự kiện
  `tool` (start/done/denied/error) vào hàng đợi theo `message_id` để SSE hiển thị đúng thời điểm.

**Lý do**: Tài liệu Dify cho phép đặt tham số tool MCP trong Agent node ở chế độ Auto hoặc Fixed Value, và Fixed
Value nhận biến. Kiểm tra quyền tool là phân quyền theo vai trò và lớp, không phải guardrail nội dung, nên vẫn ở
nền tảng (FR-015).

**Phương án dự phòng** (nếu spike cho thấy Fixed Value không nhận biến): handle ngắn hạn, gắn với một tin nhắn, đưa
vào hướng dẫn hệ thống; server từ chối mọi handle sai. Ghi rõ đánh đổi trong báo cáo.

## R7. Tài liệu lớp: mỗi lớp một kho tri thức Dify, tra cứu qua tool `class_doc_search`

**Quyết định**:
- Khi lớp có tài liệu đầu tiên, backend tạo một kho tri thức Dify cho lớp (Knowledge API) và lưu
  `classes.dify_dataset_id`.
- Tải lên, xử lý lại và xóa tài liệu được đồng bộ sang Dify (tạo tài liệu từ file, xem trạng thái indexing, xóa
  tài liệu). Trạng thái tài liệu trên giao diện lấy từ trạng thái indexing của Dify (FR-021).
- `class_doc_search` (và phần tra tài liệu của `quiz_generator`) gọi API retrieve của Dify trên đúng kho của
  `ToolContext.class_id`. Mã kho do backend lấy từ lớp, không bao giờ do mô hình chọn, nên lớp B không thể đọc kho
  của lớp A (FR-020, FR-021a). Lượt chat cá nhân không có lớp nên tool bị từ chối như hiện nay.
- Kết quả retrieve có tên tài liệu, vị trí và đoạn văn; backend dùng chúng làm trích dẫn (R8).
- Bảng `document_chunks` và embedding pgvector chỉ còn phục vụ engine cũ, bị xóa ở bước dọn dẹp.

**Lý do**: Knowledge Retrieval node của Dify chọn kho tĩnh trong DSL, không đổi theo lượt được. Lọc theo metadata
bằng biến có tồn tại nhưng có lỗi ở một số bản 1.13.x, và chỉ dùng được khi gộp mọi lớp vào một kho, trái
clarification "mỗi lớp một kho". Tra cứu qua tool giữ được kho riêng từng lớp, giữ cơ chế cách ly đã test, và tool
vẫn hiện trên giao diện như trước.

**Phương án đã cân nhắc**:
- *Một kho chung, lọc metadata `class_id` bằng biến*: bị loại (trái clarification, phụ thuộc bản Dify).
- *HTTP Request node trong runner gọi API retrieve với `dataset_id` từ input*: khả thi nhưng tra cứu ở mọi lượt kể
  cả khi không cần, và cần thêm khóa API kho tri thức bên trong DSL.

## R8. Gợi ý câu hỏi và trích dẫn

**Quyết định**:
- Bật "Suggested questions after answer" trong runner. Sau khi câu trả lời hoàn tất và không bị chặn, backend gọi
  API lấy gợi ý theo `message_id` của Dify, bỏ mọi câu chứa từ khóa trong `moderation-keywords.txt` (cùng bộ luật
  với kiểm duyệt đầu ra, FR-022), giữ tối đa 3 câu, rồi phát sự kiện SSE `suggestions`.
- Trích dẫn: backend gom kết quả của các lần gọi `class_doc_search` trong lượt (tài liệu, vị trí, đoạn trích ≤ 300
  ký tự), phát sự kiện SSE `citations` trước `done`, và lưu vào `chat_messages.meta`.
- Câu trả lời bị chặn hoặc thu hồi: không phát `suggestions` và `citations`.

**Lý do**: Dify chỉ trả `retriever_resources` khi dùng Knowledge Retrieval node, mà R7 không dùng node đó. Gợi ý
câu hỏi không đi qua kiểm duyệt đầu ra của Dify, nên lọc lại bằng chính bộ từ khóa của Dify.

## R9. Ánh xạ sự kiện stream của Dify sang SSE của nền tảng

**Quyết định**: Giữ nguyên giao thức SSE với web (`operation`, `conversation`, `agent`, `notice`, `text_delta`,
`text_reset`, `tool`, `done`, `error`), thêm `suggestions`, `citations` và loại `notice` mới `context_reset`.

| Sự kiện Dify (runner) | Xử lý trong backend |
|---|---|
| `message` / `agent_message` | `text_delta` (generation 0, `text_offset` theo UTF-16) |
| `message_replace` | kiểm duyệt đầu ra đã thay câu trả lời → `text_reset` + `text_delta` generation 1, ghi `guard_events` stage `output` |
| `agent_thought` có tool | bỏ qua; sự kiện tool lấy từ handler MCP (R6) |
| `message_end` | lấy `metadata.usage` → `usage_ledger` purpose `agent`; lấy `message_id` của Dify |
| `error`, HTTP lỗi, timeout | `status="error"`, giữ phần đã stream |
| `workflow_started`, `node_*`, `ping` | ghi span tracing hoặc bỏ qua |

- Kiểm duyệt đầu vào của runner bắt được: Dify trả nguyên văn câu trả lời cài sẵn. Backend nhận ra bằng cách so
  với câu trả lời cài sẵn trong cấu hình (cùng file nguồn với DSL), đặt `status="blocked"`, `blocked_stage="input"`.
- Người dùng bấm dừng hoặc đóng tab: backend gọi API stop với `task_id` của Dify (FR-006).
- Token của triage lấy từ `total_tokens` của workflow run → purpose `triage`.

## R10. Giữ engine cũ phía sau cờ cấu hình

**Quyết định**: Thêm `runtime_engine: Literal["langgraph", "dify"] = "langgraph"`. `app/runtime/engine.py`
có `run_turn()` chọn engine; `chat/router.py`, sandbox của builder và `certify/pipeline.py` chỉ gọi `run_turn()`.
Khi so sánh xong (FR-024, FR-025) mới đổi mặc định sang `dify`, rồi xóa `graph.py`, `runtime/router.py`,
`guard/classifier.py`, phần chặn của `guard/rules.py`, `document_chunks` và dependency `langgraph`.

**Lý do**: FR-025, và để `eval/` chạy được cả hai engine trên cùng dataset.

## R11. Kiểm định chạy qua Dify

**Quyết định**: Pipeline kiểm định gọi thẳng runner với `requested_agent` cố định và hội thoại mới cho mỗi tình
huống. Để chấm chính agent (tương đương `guard_mode="prompt_only"` hiện nay), kiểm định dùng ứng dụng thứ ba
`eduagent-runner-raw`: cùng DSL với runner nhưng tắt kiểm duyệt cấp ứng dụng. Giám khảo LLM vẫn chạy ở backend qua
`app/llm` như hiện nay.

**Lý do**: Kiểm duyệt cấp ứng dụng không bật/tắt được theo request. Nếu kiểm định chạy qua runner có kiểm duyệt,
điểm số đo guard của Dify chứ không đo agent. Cả hai ứng dụng sinh từ cùng một file DSL nguồn, nên hành vi agent
giống nhau.

## R12. Spike bắt buộc trước khi triển khai (bước 0)

Dựng Dify bản ổn định mới nhất (≥ 1.13.3) và trả lời:

1. Fixed Value của tham số tool MCP trong Agent node có nhận biến `{{#start.ctx#}}` không? (R6; không → dùng dự phòng)
2. Tên và nội dung chính xác của các sự kiện stream của chatflow có Agent node; có `message_replace` khi kiểm
   duyệt đầu ra chặn không; `message_end` có đủ token vào/ra không? (R9)
3. Giới hạn độ dài của input kiểu paragraph (cần ≥ 12000 ký tự cho hướng dẫn hệ thống). (R1)
4. Độ trễ thêm vào cho chữ đầu tiên (triage blocking + runner) có đạt SC-004 (≤ 3 giây ở p95) không?
5. Agent node có hỗ trợ chế độ reasoning của model đang dùng không? (commit `946bf1d`)
6. Question Classifier có phân loại đúng tin nhắn tiếng Việt không dấu không? (edge case trong spec)

Kết quả ghi vào `infra/dify/README.md` mục "Ghi chú spike". Nếu câu 1 và phương án dự phòng đều không đạt, hoặc
câu 4 vượt xa SC-004, dừng lại và báo người dùng trước khi làm tiếp.

## R13. Hạ tầng Dify

**Quyết định**:
- Dùng `docker/docker-compose.yaml` chính thức của Dify, chạy riêng, ghim phiên bản trong `infra/dify/README.md`.
- nginx của Dify đổi sang `127.0.0.1:8080`. Container Dify gọi MCP của backend qua
  `http://host.docker.internal:8001/mcp` (backend chạy cổng 8001 theo README; Linux thêm `extra_hosts`).
- Repo lưu: DSL của ba ứng dụng (`infra/dify/*.yml`), `moderation-keywords.txt`, README dựng lại. Import DSL một
  lần qua giao diện Dify khi dựng, rồi chép API key vào `.env` (FR-026).
- `.env.example` thêm `RUNTIME_ENGINE`, `DIFY_BASE_URL`, `DIFY_TRIAGE_KEY`, `DIFY_RUNNER_KEY`,
  `DIFY_RUNNER_RAW_KEY`, `DIFY_DATASET_KEY`, `DIFY_TIMEOUT_S`, `MCP_TOKEN`, `MCP_PUBLIC_URL`.
- Tracing: span `triage` và `run_agent` bọc lời gọi Dify; bật tích hợp Langfuse trong Dify và gắn `message_id` vào
  metadata để nối hai trace.

**Lý do**: Dify cần 8–10 container và ~4 GB RAM; tách riêng để không ảnh hưởng `infra/docker-compose.yml`.

## R14. Kiểm thử offline

**Quyết định**:
- `app/runtime/dify_client.py` nhận `httpx.AsyncClient` qua tham số, test dùng `httpx.MockTransport`.
- Fixture ghi từ Dify thật trong spike: `backend/tests/fixtures/dify/*.sse` (trả lời thường, có tool, tool bị từ
  chối, `message_replace`, lỗi giữa chừng) và `*.json` (triage: safe, block, self-harm, routing).
- Test MCP qua HTTP: thiếu token, sai handle, handle hết hạn, sai vai trò, tool không được cấp.
- Test tích hợp với Dify thật đánh dấu `@pytest.mark.dify`, chỉ chạy khi có `DIFY_BASE_URL`.
- Bộ test hiện có vẫn chạy với `runtime_engine=langgraph` cho tới bước dọn dẹp.

**Lý do**: FR-027 (test không cần Dify chạy).
