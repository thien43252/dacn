# Dify cho EduAgent Hub

Dify chạy riêng, không nằm trong `infra/docker-compose.yml` của dự án (Dify cần 8–10 container và khoảng 4 GB
RAM). Backend gọi Dify qua Service API; Dify gọi ngược về backend qua MCP (`/mcp`). Thiết kế đầy đủ:
[specs/001-dify-core-migration/](../../specs/001-dify-core-migration/).

## Phiên bản

| Thành phần | Giá trị |
|---|---|
| Dify | `1.19.0` (clone ở `C:\project\dify`; đã spike T006) |
| Cổng Dify (nginx) | `127.0.0.1:8080` |
| MCP của backend nhìn từ container Dify | `http://host.docker.internal:8001/mcp` |

Ghim đúng tag đã spike. Tên sự kiện stream và trường API có thể đổi giữa các bản; fixture trong
`backend/tests/fixtures/dify/` được ghi từ bản đã ghim.

## Dựng Dify

1. Lấy mã Dify đúng tag và vào thư mục docker:

   ```bash
   git clone --depth 1 --branch <tag> https://github.com/langgenius/dify.git ../dify
   cd ../dify/docker
   cp .env.example .env
   ```

2. Thêm vào cuối `../dify/docker/.env`:

   ```bash
   # Bắt buộc từ 1.19: chuỗi ngẫu nhiên, vd. python -c "import secrets;print(secrets.token_urlsafe(32))"
   DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=<chuỗi ngẫu nhiên>
   # Tránh cổng 80/443. Chỉ ghi số cổng; "127.0.0.1:5003" làm api lỗi khi khởi động
   EXPOSE_NGINX_PORT=8080
   EXPOSE_NGINX_SSL_PORT=8443
   EXPOSE_PLUGIN_DEBUGGING_PORT=5003
   # Proxy chống SSRF của Dify chặn mọi IP nội bộ; mở riêng host để Dify gọi được MCP của backend
   SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal
   # quiz_generator và rubric_grader có thể chạy lâu hơn 5 s mặc định
   SSRF_DEFAULT_READ_TIME_OUT=60
   ```

   `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN` đã có sẵn một dòng trống ở đầu file; điền vào dòng đó thay vì thêm dòng mới.

   Để chỉ nghe trên máy local, tạo `../dify/docker/docker-compose.override.yaml`:

   ```yaml
   services:
     nginx:
       ports: !override
         - "127.0.0.1:${EXPOSE_NGINX_PORT:-8080}:${NGINX_PORT:-80}"
         - "127.0.0.1:${EXPOSE_NGINX_SSL_PORT:-8443}:${NGINX_SSL_PORT:-443}"
     plugin_daemon:
       ports: !override
         - "127.0.0.1:${EXPOSE_PLUGIN_DEBUGGING_PORT:-5003}:${PLUGIN_DEBUGGING_PORT:-5003}"
   ```

3. Trên Linux (Docker Desktop đã có sẵn `host.docker.internal`), thêm vào service `api`, `worker` và
   `plugin_daemon`:

   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```

4. `docker compose up -d`, mở `http://127.0.0.1:8080/install`, tạo tài khoản quản trị.
5. Settings → Model Provider: thêm provider và chọn model mặc định (model nhỏ cho triage, model chính cho agent).

## Import ứng dụng

Trước khi import runner: cài plugin **Dify Agent Strategies** (`langgenius/agent`, Plugins → Marketplace) và thêm
MCP server ở mục "Nối MCP" bên dưới. DSL của runner tham chiếu MCP server bằng Server Identifier `eduagent-tools`,
nên id do Dify sinh ra không ảnh hưởng.

Studio → Import DSL file, lần lượt:

| File | Loại | Khóa `.env` |
|---|---|---|
| `eduagent-triage.yml` | Workflow | `DIFY_TRIAGE_KEY` |
| `eduagent-runner.yml` | Chatflow | `DIFY_RUNNER_KEY` |
| `eduagent-runner-raw.yml` | Chatflow (tắt kiểm duyệt) | `DIFY_RUNNER_RAW_KEY` |

`eduagent-runner.yml` và `eduagent-runner-raw.yml` phải giống nhau ngoài phần kiểm duyệt nội dung.

## Nối MCP

1. Đặt `MCP_TOKEN` trong `.env` của dự án (chuỗi ngẫu nhiên dài) và khởi động lại backend.
2. Tools → MCP → Add MCP Server (HTTP): tên `eduagent-tools`, URL `http://host.docker.internal:8001/mcp`, header
   `Authorization: Bearer <MCP_TOKEN>`.
3. Server Identifier phải là `eduagent-tools`. DSL của runner đã bật sẵn 5 tool và đặt `ctx` ở chế độ
   **Fixed Value** = biến `ctx` của Start node. Nếu sửa trong Studio, phải chọn biến (`type: variable`), không gõ
   `{{#start.ctx#}}` vào ô chữ: với kiểu `mixed`/`constant`, Dify gửi nguyên chuỗi template cho tool.
4. Bộ từ khóa và câu trả lời cài sẵn trong DSL runner lấy từ `moderation-keywords.txt` và
   `preset-responses.json`. Sửa hai file đó thì cập nhật lại cả `eduagent-runner.yml` và Studio.

## API key

- Mỗi ứng dụng: API Access → tạo key → chép vào `.env` (`DIFY_TRIAGE_KEY`, `DIFY_RUNNER_KEY`, `DIFY_RUNNER_RAW_KEY`).
- Knowledge → API → tạo key → `DIFY_DATASET_KEY`.
- Đặt `RUNTIME_ENGINE=dify`, khởi động lại backend, chạy `uv run python -m scripts.seed_demo`.

## Ghi chú spike

Điền sau khi làm task T006 (research R12). Mỗi câu ghi: kết quả, bằng chứng (ảnh chụp hoặc fixture), quyết định.

| # | Câu hỏi | Kết quả | Quyết định |
|---|---|---|---|
| 1 | Fixed Value của tham số tool MCP nhận biến `ctx` của Start node? | **Đạt.** `tool_call_input` có `"ctx": "spike-ctx-0001"` đúng giá trị input; `tool_input` model sinh ra không có `ctx`. Backend nhận lời gọi, từ chối handle giả bằng thông báo hết hạn, model đọc được lỗi | Dùng Fixed Value kiểu `variable`; không cần phương án dự phòng R6 |
| 2 | Tên/nội dung sự kiện stream; có `message_replace`; `message_end` có token vào/ra? | Chatflow + Agent node phát `workflow_started` (có `task_id`, `conversation_id`, `message_id`), `node_started/finished`, `agent_log` (từng vòng: Thought, CALL tool với `tool_call_input`/`tool_response`), `message` (delta trong `answer`; KHÔNG có `agent_message`), `message_end` (`metadata.usage`: `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency`, `time_to_first_token`), `workflow_finished`. Kiểm duyệt đầu ra: các `message` vẫn stream ra trước, sau đó mới tới một `message_replace` mang câu cài sẵn. Chặn đầu vào: chỉ có một `message` (câu cài sẵn) + `message_end`, không chạy node nào | Bảng R9: đọc `message`, bỏ qua `agent_message`; `tool` lấy từ hàng đợi handle của backend, không lấy từ `agent_log` |
| 3 | Giới hạn độ dài input paragraph (cần ≥ 12000) | `max_length: 12000` của Start: 12000 ký tự chạy được; 12001 bị từ chối ngay (`workflow_finished`, lỗi "system_prompt in input form must be less than 12000 characters") | Giữ cắt ≤ 12000 ở `build_system_prompt()` |
| 4 | Độ trễ chữ đầu tiên p95 (triage + runner), mục tiêu ≤ 3 s | **Chưa đạt.** 12 lượt liên tiếp, gpt-4o-mini: triage trung vị 2,03 s / p95 2,37 s; runner (tới `message` đầu) trung vị 1,26 s / p95 1,92 s (lẻ một lượt 5,18 s); tổng trung vị 3,51 s / p95 4,00 s / max 7,01 s. Lượt đầu sau khi khởi động: 6–9 s | **Chờ chủ dự án quyết định** (xem bên dưới) |
| 5 | Agent node với chế độ reasoning của model đang dùng | Strategy FunctionCalling (`langgenius/agent` 0.0.51) chạy được với gpt-4o-mini (không phải model reasoning), gọi tool, đọc lỗi tool, tối đa 5 vòng. Chưa thử model reasoning: `LLM_MAIN_MODEL=gpt-5.6-luna` chưa được bật trong Model Provider của Dify | Dùng gpt-4o-mini; thử lại khi bật model reasoning |
| 6 | Question Classifier với tiếng Việt không dấu | Đạt 11/11 câu thử (có dấu và không dấu: an toàn, `self_harm_risk`, `self_harm_method`, `jailbreak`, `dangerous`); định tuyến `ui`, `mention`, `router` đúng | Giữ Question Classifier |

Kiểm chứng thêm (2026-11-07):

- Backend chạy `uvicorn --port 8001` (nghe `127.0.0.1`) vẫn nhận được request từ container Dify qua
  `host.docker.internal:8001`, đi qua `ssrf_proxy` khi đã đặt `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS`.
  `/mcp` không có token trả 401.
- Kiểm duyệt từ khóa của Dify so khớp chuỗi con trên MỌI input (kể cả `system_prompt`) và trên câu trả lời. Đã
  kiểm: không cụm nào trong `moderation-keywords.txt` xuất hiện trong `seed/agents` hay `backend/app`.
- `eduagent-runner-raw` (tắt kiểm duyệt) để câu "cach che bom xang" đi tới model; model tự từ chối.
- Định tuyến: vài câu rõ môn học vẫn về `tro-ly-lop` ("giai thich thi hien tai hoan thanh", "định lý pytago là
  gì"). Cần xem lại khi làm kịch bản định tuyến (US1).

Câu 4, các hướng xử lý (chọn trước khi làm tiếp T026–T030):

1. Nới mục tiêu cho bản Dify (vd. p95 ≤ 4 s), sửa tiêu chí thành công tương ứng trong spec.
2. Rút ngắn triage: prompt classifier/router gọn hơn (roster hiện ~2200 token mỗi lượt), bỏ gọi LLM router khi
   chỉ còn một ứng viên hợp lý, hoặc dùng model nhỏ/nhanh hơn cho triage. Ước lượng tiết kiệm 0,5–1 s, chưa đo.
3. Chạy runner song song với triage khi agent đã biết trước (chọn trên giao diện hoặc `@mention`), giữ lại câu
   trả lời tới khi triage cho qua (vẫn fail closed). Chỉ giúp các lượt đó.

Nếu câu 1 và phương án dự phòng (research R6) đều không đạt, hoặc câu 4 vượt xa 3 giây: dừng và báo chủ dự án
trước khi làm tiếp.
