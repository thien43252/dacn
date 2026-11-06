# Kế hoạch: chuyển lõi runtime từ LangGraph sang Dify

Nhánh: `feat/dify-runtime`. Tài liệu này bổ sung cho [PLAN.md](PLAN.md) và không thay thế nó.

## 1. Mục tiêu và phạm vi

- **Mục tiêu:** phần thực thi agent (gọi LLM, vòng lặp tool, stream câu trả lời) chạy trên Dify thay cho `run_agent` trong [graph.py](../backend/app/runtime/graph.py). Phần điều phối bên ngoài bỏ `StateGraph` của LangGraph, thay bằng pipeline asyncio thuần.
- **Giữ nguyên trong backend:** guard nhiều lớp, router, chính sách lớp, tool guard, `guard_events`, `ToolCallLog`, usage, RAG pgvector, pipeline kiểm định agent. Đây là phần đóng góp chính của đồ án, và hiện chỉ backend có đủ ngữ cảnh (user, role, lớp, policy) để làm.
- **Giữ nguyên với frontend:** giao thức SSE (`agent`, `notice`, `text_delta`, `text_reset`, `tool`, `done`). Web không cần sửa.
- **Không làm:** dùng knowledge base của Dify, để Dify quản lý hội thoại, hay tạo một Dify app cho mỗi agent.

### Kiến trúc đích

```
Backend FastAPI (giữ chính sách)                       Dify (thực thi agent)
──────────────────────────────────                     ─────────────────────────────
screen (rules, PII, chủ đề bị chặn)
  ├─ classify (LLM guard) ─┐  asyncio.gather
  └─ route (router)  ──────┤
gate ──────────────────────┘
run_agent_dify ── POST /v1/chat-messages (stream) ──▶  Chatflow "eduagent-runner"
   ▲  map SSE → text_delta                              Start(inputs: system_prompt,
   │                                                          history, ctx, tools)
   │                                                     Agent node (Function calling)
   │                                                          │ gọi tool qua MCP
   └── tool events (hàng đợi theo message_id) ◀── /mcp ◀──────┘
                                     MCP server của backend (streamable HTTP)
                                     tool guard + ToolCallLog chạy phía server
review (output guard, có thể thu hồi câu trả lời)
```

**Vì sao chọn mô hình lai thay vì đưa toàn bộ guard và router vào workflow Dify:** nếu guard nằm trong Dify, mỗi bước đều phải gọi HTTP ngược về backend để đọc policy và ghi log. Khi đó cả hai hệ thống đều chứa logic, khó test và khó đo. Phương án đưa toàn bộ vào Dify ghi ở mục 7 (tùy chọn).

## 2. Thiết kế chi tiết

### 2.1 Trừu tượng runtime và cờ cấu hình

- Thêm vào `config.py`: `runtime_engine: Literal["langgraph", "dify"] = "langgraph"`, cùng các khóa `dify_base_url`, `dify_api_key` (API key của app), `dify_timeout_s`, `mcp_public_url` (URL mà container Dify dùng để gọi về backend), `mcp_token`.
- Tạo `app/runtime/engine.py` với hàm `run_turn(state, ctx) -> AsyncIterator[tuple[mode, chunk]]`, trả về đúng dạng `("custom", event)` / `("values", final)` như `GRAPH.astream` hiện nay. [chat/router.py:268](../backend/app/chat/router.py#L268) và [certify/pipeline.py:155](../backend/app/certify/pipeline.py#L155) chỉ cần đổi lời gọi.
- Giữ engine `langgraph` cho đến khi đã so sánh xong hai engine ở bước 5, rồi mới xóa.

### 2.2 Pipeline điều phối không dùng LangGraph

- `app/runtime/pipeline.py`: dùng lại nguyên các hàm node `screen`, `classify`, `select_agent`, `gate`, `review`.
- Thay `get_stream_writer()` bằng `ctx.emit(event)`, trong đó `emit` đẩy vào một `asyncio.Queue`. Generator `run_turn` vừa đọc queue vừa chờ các bước chạy xong.
- `classify` và `select_agent` chạy song song bằng `asyncio.gather` (thay cho cạnh song song trong graph).
- Decorator `_traced` giữ nguyên, vì nó không phụ thuộc LangGraph.

### 2.3 Chatflow Dify "eduagent-runner"

Chỉ có một app chung. File DSL được export và commit tại `infra/dify/eduagent-runner.yml` để dựng lại được.

- **Start inputs:**
  - `system_prompt` (paragraph, tối đa 12000 ký tự; manifest cho phép 8000 ký tự cộng thêm luật nền tảng).
  - `history` (paragraph, lịch sử backend đã dựng sẵn).
  - `ctx` (handle ngữ cảnh tool).
  - `allowed_tools` (danh sách tên tool).
- **Memory của Dify: tắt.** Backend tự gửi lịch sử. Mỗi lượt vì thế không mang trạng thái, kiểm định và eval tái lập được, và tin nhắn đã ẩn PII không bao giờ lưu sang Dify.
- **Agent node:** chiến lược Function Calling, số vòng tối đa bằng 5 (tương ứng `MAX_TOOL_ROUNDS = 4`, cộng một vòng trả lời). Gắn MCP provider "eduagent-tools" trỏ tới `mcp_public_url`. Cả 5 tool đều được bật. Tool nào được phép là do tool guard phía server quyết định, và danh sách được phép cũng được nhắc trong system prompt.
- **Model:** cấu hình trong Dify. Phải dùng cùng model với `llm_main_model` để so sánh công bằng.
- Gửi `user` = id người dùng trên nền tảng để tiện tra log, không gửi email hay tên.

### 2.4 Tool: MCP qua HTTP và tool guard phía server

Đây là phần thay đổi lớn nhất. Hiện tại tool guard chạy trong [registry.py](../backend/app/tools/registry.py) trước khi gọi MCP in-process, và handle `ctx` nằm trong dict ở RAM ([context.py](../backend/app/tools/context.py)).

1. Mount [tools/server.py](../backend/app/tools/server.py) vào FastAPI tại `/mcp` qua transport streamable HTTP, xác thực bằng header `Authorization: Bearer <mcp_token>`. Dify không cần quyền truy cập rộng hơn thế.
2. Chuyển phần kiểm tra của tool guard (tool đã đăng ký, có trong manifest, đúng role, có lớp) và việc ghi `ToolCallLog` / `guard_events` vào trong handler MCP. Handler đọc `ToolContext` từ handle. Engine `langgraph` cũng đi qua đúng đường này, nên hai engine dùng chung một logic.
3. Handle: `run_agent_dify` gọi `register()` trước khi chạy và `release()` trong `finally`. Thêm TTL (ví dụ 10 phút) để handle không sống mãi khi lượt bị crash.
4. Sự kiện tool cho UI: handler MCP đẩy `{"type": "tool", status: start/done/denied/error}` vào queue của `message_id`, nên UI vẫn thấy tool đúng thời điểm. Dùng log của Dify cho việc này không chính xác bằng.
5. **Rủi ro chính cần spike:** mô hình không được tự điền hay nhìn thấy `ctx`. Kiểm tra xem Agent node có cho cố định giá trị tham số tool (lấy từ biến `{{ctx}}`) hay không. Nếu không:
   - **Phương án B:** truyền handle qua system prompt. Handle ngẫu nhiên, sống ngắn và chỉ gắn với một tin nhắn; nếu mô hình điền sai handle thì server từ chối. Ghi rõ đây là điểm đánh đổi trong báo cáo.
   - **Phương án C:** mỗi lượt cấp một URL MCP riêng `/mcp/{handle}`. Cách này chỉ dùng được nếu Dify cho phép đổi URL provider theo biến.

### 2.5 Dify client và ánh xạ stream

`app/runtime/dify_client.py` dùng `httpx.AsyncClient` để gọi `POST {dify_base_url}/v1/chat-messages` với `response_mode=streaming`, rồi parse SSE.

| Sự kiện Dify | Xử lý trong backend |
|---|---|
| `message` / `agent_message` (`answer`) | `text_delta`, tính `text_offset` theo `utf16_len` như hiện tại |
| `node_started`, `node_finished`, `agent_log` | ghi span tracing, không gửi ra UI |
| `message_end` (`metadata.usage`) | `ctx.timed("agent", Usage(...))` |
| `error` / HTTP lỗi / timeout | `status="error"`, giữ phần đã stream |
| `ping` | bỏ qua |

- Danh sách sự kiện phải kiểm tra lại với đúng phiên bản Dify cài trong spike, vì tên sự kiện của chatflow và agent app khác nhau.
- **Refusal:** Dify không trả `stop_reason`. Khi câu trả lời rỗng hoặc lỗi kiểm duyệt từ provider thì xem là `blocked_stage="model"`.
- **Hủy lượt:** khi client SSE ngắt kết nối thì gọi `POST /v1/chat-messages/{task_id}/stop`.

### 2.6 Usage, tracing, cấu hình model

- **Usage:** từ `message_end`. Guard, router và judge vẫn gọi LLM qua `app/llm` như cũ, nên bảng usage giữ đủ các mục đích (`input_guard`, `router`, `agent`, `output_guard`, `judge`).
- **Tracing:** span `run_agent` bọc lời gọi Dify. Bật thêm tích hợp Langfuse trong Dify và gắn `message_id` vào metadata để nối hai trace với nhau.
- **API key:** khóa LLM nằm ở hai nơi (`.env` cho guard/router, Dify cho agent). Ghi rõ trong `.env.example` và README.

### 2.7 Hạ tầng

- Dựng Dify bằng `docker/docker-compose.yaml` chính thức, chạy riêng, không gộp vào [infra/docker-compose.yml](../infra/docker-compose.yml). Ghim phiên bản (`DIFY_VERSION`) trong `infra/dify/README.md`.
- **Cổng:** nginx của Dify mặc định dùng cổng 80, nên đổi sang `127.0.0.1:8080`. Postgres của Dify chỉ dùng nội bộ nên không đụng cổng 5433.
- **Mạng:** container Dify gọi backend qua `http://host.docker.internal:8000/mcp`. Trên Linux cần thêm `extra_hosts`.
- **Tài nguyên:** Dify cần khoảng 8–10 container và tối thiểu khoảng 4 GB RAM. Phải thử trên máy dùng để demo.
- **Giấy phép:** Dify Open Source License (dựa trên Apache 2.0, có thêm điều kiện về multi-tenant và logo). Đồ án chỉ dùng một workspace nên ổn. Ghi lại trong báo cáo nếu sau này định triển khai thật.

## 3. Danh sách file thay đổi

| File | Thay đổi |
|---|---|
| `backend/app/config.py` | thêm `runtime_engine`, `dify_*`, `mcp_public_url`, `mcp_token` |
| `backend/app/runtime/engine.py` (mới) | `run_turn` chọn engine |
| `backend/app/runtime/pipeline.py` (mới) | pipeline asyncio, `ctx.emit` |
| `backend/app/runtime/dify_client.py` (mới) | client SSE của Dify |
| `backend/app/runtime/graph.py` | tách các node thành hàm dùng chung; xóa ở bước 6 |
| `backend/app/tools/server.py`, `registry.py`, `context.py` | MCP qua HTTP, guard và log chuyển vào handler, handle có TTL |
| `backend/app/main.py` | mount `/mcp` |
| `backend/app/chat/router.py`, `certify/pipeline.py` | gọi `run_turn` |
| `backend/tests/test_runtime_dify.py` (mới) | fixture SSE ghi sẵn, server Dify giả bằng `httpx.MockTransport` |
| `backend/tests/test_documents_tools.py` | thêm test tool guard qua MCP HTTP (thiếu token, sai handle, sai role) |
| `backend/pyproject.toml` | xóa `langgraph` ở bước 6 |
| `infra/dify/` (mới) | DSL chatflow, README dựng Dify |
| `.env.example`, `README.md`, `docs/PLAN.md`, `docs/BAO-CAO.md` | cập nhật |

## 4. Lộ trình

| Bước | Việc | Thời gian | Kết quả kiểm chứng |
|---|---|---|---|
| 0 | **Spike:** dựng Dify, tạo chatflow có Agent node với MCP trỏ về backend. Trả lời 5 câu hỏi ở mục 6 | 2–3 ngày | Ghi chú spike; một câu hỏi toán gọi được `math_check` qua Dify |
| 1 | `engine.py` và cờ cấu hình; chat và certify gọi `run_turn` | 1 ngày | Toàn bộ test hiện có pass với `runtime_engine=langgraph` |
| 2 | Pipeline asyncio thay `StateGraph` (engine `langgraph` giờ chỉ còn là "agent gọi LLM trực tiếp") | 1–2 ngày | Test chat, guard, routing pass; thứ tự sự kiện SSE không đổi |
| 3 | MCP qua HTTP, tool guard và log phía server, queue sự kiện tool, handle có TTL | 2–3 ngày | Test tool guard qua HTTP; `ToolCallLog` đủ như trước |
| 4 | `dify_client` và `run_agent_dify`; export DSL vào `infra/dify/` | 2–3 ngày | Demo chat end-to-end với `runtime_engine=dify`; thu hồi câu trả lời và thông báo PII vẫn chạy trên UI; e2e Playwright pass |
| 5 | Đo đạc: chạy `eval/run_routing.py`, `run_redteam.py`, `run_certify.py` trên cả hai engine | 2 ngày | Bảng so sánh tỉ lệ chặn, over-refusal, độ trễ p50/p95 và chi phí mỗi lượt cho báo cáo |
| 6 | Dọn dẹp: xóa `graph.py` và dependency `langgraph`; cập nhật tài liệu | 1 ngày | `grep langgraph` không còn kết quả; README dựng được từ đầu |

**Tổng:** khoảng 2,5–3 tuần làm việc. Nếu spike ở bước 0 cho thấy Dify không đáp ứng (mục 6), dừng ở đó. Bước 1–2 vẫn có ích vì chúng bỏ LangGraph mà không cần Dify.

## 5. Kiểm thử

- Test đơn vị chạy offline. Engine `dify` được test bằng transport giả phát lại file SSE ghi từ Dify thật (`tests/fixtures/dify/*.sse`). Gồm các ca: trả lời thường, có tool, tool bị từ chối, lỗi giữa chừng, timeout.
- Một test tích hợp đánh dấu `@pytest.mark.dify` chỉ chạy khi có `DIFY_BASE_URL`.
- **Bất biến phải giữ:**
  - thứ tự sự kiện SSE và `text_offset` theo UTF-16;
  - tin nhắn bị chặn ở input không bao giờ tới Dify;
  - PII đã ẩn không có trong payload gửi Dify;
  - tool sai role luôn bị từ chối và ghi `guard_events`.

## 6. Câu hỏi spike phải trả lời ở bước 0

1. Agent node có cho cố định tham số `ctx` của tool MCP bằng biến workflow, không để mô hình điền không? (quyết định chọn giữa phương án A, B, C ở mục 2.4)
2. Tên và nội dung chính xác của các sự kiện stream của chatflow có Agent node; `message_end` có đủ token vào/ra không?
3. Giới hạn độ dài input kiểu paragraph (system prompt 12k ký tự, lịch sử dài).
4. Dify thêm bao nhiêu độ trễ cho token đầu tiên so với gọi provider trực tiếp?
5. Agent node có hỗ trợ reasoning/effort của model đang dùng không? (commit `946bf1d` vừa sửa lỗi tool khi bật reasoning)

## 7. Tùy chọn: đưa cả điều phối vào Dify

Chỉ làm nếu có yêu cầu "workflow phải nằm trong Dify" (ví dụ để giáo viên tự kéo-thả).

- Chatflow: Start → HTTP node `POST /internal/guard/screen` → IF/ELSE → hai nhánh song song (HTTP `/internal/guard/classify`, HTTP `/internal/route`) → HTTP `/internal/gate` → Agent → HTTP `/internal/guard/review` → Answer.
- **Hệ quả:**
  - Thu hồi câu trả lời sau khi đã stream rất khó làm, vì Answer node stream thẳng ra. Sẽ phải bỏ stream hoặc chấp nhận review sau.
  - Mỗi lượt thêm 4–5 lần gọi HTTP.
  - Logic bị tách ở hai nơi.
  - Thí nghiệm `guard_mode` ở tuần 11 phải làm lại.
- Khuyến nghị: không làm trong phạm vi đồ án.

## 8. Rủi ro

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| Không cố định được `ctx` cho tool | Mô hình thấy handle | Phương án B: handle sống ngắn, gắn với một tin nhắn, server kiểm tra; ghi rõ trong báo cáo |
| Dify đổi API hoặc tên sự kiện giữa các phiên bản | Gãy stream | Ghim phiên bản; test bằng fixture ghi sẵn |
| Máy demo thiếu RAM | Demo chậm hoặc lỗi | Thử sớm ở bước 0; giữ engine cũ làm dự phòng đến bước 6 |
| Độ trễ tăng | Trải nghiệm kém | Đo ở bước 5; guard và router vẫn chạy song song như trước |
| Dữ liệu và key nằm ở hai nơi | Khó vận hành | Tắt memory của Dify; một tài liệu cấu hình duy nhất |
