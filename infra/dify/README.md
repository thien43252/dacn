# Dify cho EduAgent Hub

Dify chạy riêng, không nằm trong `infra/docker-compose.yml` của dự án (Dify cần 8–10 container và khoảng 4 GB
RAM). Backend gọi Dify qua Service API; Dify gọi ngược về backend qua MCP (`/mcp`). Thiết kế đầy đủ:
[specs/001-dify-core-migration/](../../specs/001-dify-core-migration/).

## Phiên bản

| Thành phần | Giá trị |
|---|---|
| Dify | **TODO(spike): ghi tag chính xác sau T006**, tối thiểu `1.13.3` |
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

2. Trong `../dify/docker/.env`, đổi cổng nginx để không đụng cổng của dự án:

   ```bash
   EXPOSE_NGINX_PORT=8080
   EXPOSE_NGINX_SSL_PORT=8443
   ```

   Muốn chỉ nghe trên máy local thì sửa phần `ports` của service `nginx` trong `docker-compose.yaml` thành
   `"127.0.0.1:${EXPOSE_NGINX_PORT:-80}:${NGINX_PORT:-80}"`.

3. Trên Linux (Docker Desktop đã có sẵn `host.docker.internal`), thêm vào service `api`, `worker` và
   `plugin_daemon`:

   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```

4. `docker compose up -d`, mở `http://127.0.0.1:8080/install`, tạo tài khoản quản trị.
5. Settings → Model Provider: thêm provider và chọn model mặc định (model nhỏ cho triage, model chính cho agent).

## Import ứng dụng

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
3. Trong Agent node của runner và runner-raw: bật 5 tool, đặt tham số `ctx` của mỗi tool ở chế độ **Fixed Value**
   = biến `ctx` của Start node.

## API key

- Mỗi ứng dụng: API Access → tạo key → chép vào `.env` (`DIFY_TRIAGE_KEY`, `DIFY_RUNNER_KEY`, `DIFY_RUNNER_RAW_KEY`).
- Knowledge → API → tạo key → `DIFY_DATASET_KEY`.
- Đặt `RUNTIME_ENGINE=dify`, khởi động lại backend, chạy `uv run python -m scripts.seed_demo`.

## Ghi chú spike

Điền sau khi làm task T006 (research R12). Mỗi câu ghi: kết quả, bằng chứng (ảnh chụp hoặc fixture), quyết định.

| # | Câu hỏi | Kết quả | Quyết định |
|---|---|---|---|
| 1 | Fixed Value của tham số tool MCP nhận biến `ctx` của Start node? | TODO | |
| 2 | Tên/nội dung sự kiện stream; có `message_replace`; `message_end` có token vào/ra? | TODO | |
| 3 | Giới hạn độ dài input paragraph (cần ≥ 12000) | TODO | |
| 4 | Độ trễ chữ đầu tiên p95 (triage + runner), mục tiêu ≤ 3 s | TODO | |
| 5 | Agent node với chế độ reasoning của model đang dùng | TODO | |
| 6 | Question Classifier với tiếng Việt không dấu | TODO | |

Nếu câu 1 và phương án dự phòng (research R6) đều không đạt, hoặc câu 4 vượt xa 3 giây: dừng và báo chủ dự án
trước khi làm tiếp.
