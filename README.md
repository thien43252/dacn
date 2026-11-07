# EduAgent Hub

Nền tảng mở (B2C) để giáo viên tạo lớp, thêm học sinh và phụ huynh, rồi cài agent AI từ Hub vào lớp. Trọng tâm là
lớp tin cậy: định tuyến theo lớp có chính sách lớp, guardrail nhiều lớp, và certification pipeline kiểm định agent trước
khi lên Hub. Lõi agent (guardrail, định tuyến, vòng lặp agent, kho tri thức của lớp) chạy trên Dify tự dựng. Đồ án cá
nhân, chạy local trên dữ liệu demo.

## Kiến trúc

```text
web (React 19) ──SSE──▶ FastAPI (backend/)
                         │  đăng nhập, lớp, đồng ý phụ huynh, ẩn thông tin cá nhân, nhật ký guard, sổ chi phí
                         │
                         ├──▶ Dify: eduagent-triage   (an toàn + chọn agent, workflow)
                         ├──▶ Dify: eduagent-runner   (agent, kiểm duyệt từ khóa, stream câu trả lời)
                         ├──▶ Dify: eduagent-review   (kiểm tra câu trả lời theo chính sách lớp)
                         └──▶ Dify: Knowledge API     (mỗi lớp một kho tri thức)
                                   │
       Dify gọi lại ◀──MCP /mcp───┘  5 tool của nền tảng, qua tool guard và handle ngắn hạn
```

Backend chỉ giữ phần thuộc về quyền và dữ liệu cá nhân: cổng đồng ý của phụ huynh, ẩn số điện thoại, mật khẩu, địa chỉ
trước khi gửi đi, tool guard, ghi `guard_events` và chi phí. Mọi bước kiểm duyệt nội dung và chọn agent nằm trong các
app Dify ở [`infra/dify/`](infra/dify/); hợp đồng giữa hai bên ở
[`specs/001-dify-core-migration/contracts/`](specs/001-dify-core-migration/contracts/). Giám khảo kiểm định, báo cáo
phụ huynh, `quiz_generator` và `rubric_grader` vẫn gọi mô hình qua LLM adapter của backend.

## Cấu trúc

| Thư mục    | Nội dung                                                                                                         |
| ------------ | ----------------------------------------------------------------------------------------------------------------- |
| `web/`     | React 19 + Vite + plain CSS. UI kế thừa từ Vinschool Capstone Studio (team-8), đã cắt phần nghiệp vụ cũ |
| `backend/` | FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL. Gọi Dify (`app/runtime/`), MCP server (`app/tools/`), certify |
| `infra/`   | Docker Compose cho Postgres (cổng host 5433); `infra/dify/`: DSL các app Dify, từ khóa kiểm duyệt, hướng dẫn dựng |
| `eval/`    | Dataset red-team tiếng Việt, routing set, script thực nghiệm                                                  |
| `seed/`    | Manifest agent mẫu, dữ liệu lớp demo                                                                          |
| `docs/`    | Thiết kế và báo cáo                                                                                          |

## Chạy local

Cần Node.js, Python 3.11, [uv](https://docs.astral.sh/uv/), Docker Desktop và một khóa API của nhà cung cấp mô hình
cho Dify (đang dùng OpenAI `gpt-4o-mini` và `text-embedding-3-small`).

1. Dựng Dify (khoảng 30 phút lần đầu) theo [infra/dify/README.md](infra/dify/README.md): chạy bộ compose chính thức ở
   `127.0.0.1:8080`, cài plugin, import 4 DSL, nối MCP `eduagent-tools`, rồi chép các khóa API vào `.env`
   (`DIFY_TRIAGE_KEY`, `DIFY_RUNNER_KEY`, `DIFY_RUNNER_RAW_KEY`, `DIFY_REVIEW_KEY`, `DIFY_DATASET_KEY`, `MCP_TOKEN`).
2. Chạy nền tảng:

```bash
cp .env.example .env   # rồi điền các khóa DIFY_* và MCP_TOKEN ở bước 1

# Database
docker compose -f infra/docker-compose.yml up -d --wait

# Backend (http://127.0.0.1:8001)
cd backend
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_demo   # 4 tài khoản demo, mật khẩu Demo123!; đẩy tài liệu mẫu vào Dify
uv run uvicorn app.main:app --reload --port 8001

# Frontend (http://127.0.0.1:5173, proxy /api -> 8001)
cd web
npm install
npm run dev
```

## Kiểm tra

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
# Chạy cùng bộ test trên Postgres (bắt lỗi khác biệt so với SQLite):
TEST_DATABASE_URL=postgresql+asyncpg://eduagent:eduagent@127.0.0.1:5433/eduagent_test uv run pytest -q
cd web && npm test && npm run build
```

Test backend không cần database, Dify hay API key: Dify được giả lập bằng phản hồi ghi từ Dify thật
(`backend/tests/fixtures/dify/`), LLM adapter là `fake`. Test có mark `dify` chỉ chạy khi đặt `DIFY_BASE_URL` trong môi
trường (`DIFY_BASE_URL=http://127.0.0.1:8080 uv run pytest -m dify`).

## Trạng thái

Theo kế hoạch 12 tuần ([docs/PLAN.md](docs/PLAN.md)). Tuần 4 đến tuần 11 mô tả lõi đầu tiên, chạy trong backend; sau
đó lõi được chuyển sang Dify (mục cuối).

- Tuần 1: khung repo, UI đã rebrand, 4 vai trò, backend skeleton, migration bật pgvector.
- Tuần 2: đăng nhập bằng cookie httpOnly, phân quyền theo vai trò, seed demo; dataset `eval/` (190 red-team, 60 đối chứng,
  101 định tuyến).
- Tuần 3: lớp học, mã lớp, thành viên, liên kết phụ huynh bằng mã của con, đồng ý của phụ huynh (chặn agent khi chưa
  đồng ý), chính sách lớp.
- Tuần 4: LLM adapter (Anthropic, OpenAI, Gemini, `fake`), runtime LangGraph, chat qua SSE, sổ ghi token/chi phí.
- Tuần 5: tài liệu lớp (PDF/DOCX/TXT/MD) chia đoạn và embed vào pgvector (HNSW cosine); MCP server nội bộ với 5 tool
  (`class_doc_search`, `quiz_generator`, `rubric_grader`, `math_check`, `progress_summary`) đi qua tool guard.
- Tuần 6: manifest agent, 7 agent nền tảng (`seed/agents`), Agent Hub, cài vào lớp hoặc cá nhân, trình tạo agent có
  phiên bản bất biến, tạo bản sao và phòng thử (sandbox). Học sinh và phụ huynh chỉ dùng được phiên bản đã kiểm định.
- Tuần 7: orchestrator chọn agent theo thứ tự: agent chọn trên UI, `@mention`, router LLM (model nhỏ, JSON), router từ
  khoá (dự phòng và baseline), rồi `tro-ly-lop`. Chính sách lớp giới hạn môn được dùng. Đo bằng
  `uv run python ../eval/run_routing.py [--router llm]` (router từ khoá: 74% trên `routing_set`).
- Tuần 8: guard 3 lớp: đầu vào (luật + phân loại LLM, chạy song song với router; ẩn số điện thoại, mật khẩu, địa chỉ;
  chủ đề cấm của lớp; dấu hiệu tự làm hại thì trả lời hỗ trợ kèm Tổng đài 111), tool guard, đầu ra (luật + LLM, thu hồi
  câu trả lời đã stream). Mọi quyết định ghi vào `guard_events`; nhật ký cho giáo viên (theo lớp) và admin (kèm chi phí).
  `GUARD_MODE=full|prompt_only|off` để so sánh ở tuần 11.
- Tuần 9: pipeline kiểm định: kiểm tra tĩnh manifest, giám khảo LLM đọc hướng dẫn hệ thống, chạy ~36 tình huống
  red-team và câu hỏi hợp lệ qua runtime thật, giám khảo LLM chấm từng ca, rồi quyết định
  đạt / cần xem lại / không đạt. Admin duyệt hàng đợi "cần xem lại". Agent đạt và được đăng sẽ lên Hub.
- Tuần 10: báo cáo học tập cho phụ huynh (số liệu tổng hợp, nhận xét bằng LLM hoặc theo mẫu, cảnh báo cần trò chuyện
  với con, không có nguyên văn tin nhắn; tắt được trong mục đồng ý), tab "Tiến độ" của lớp cho giáo viên, seed lịch sử
  học và hai agent giáo viên để demo kiểm định.
- Tuần 11: script thực nghiệm `eval/run_redteam.py`, `run_routing.py`, `run_certify.py` và bộ 20 agent có nhãn
  (`eval/certify_agents.yaml`); xem [eval/README.md](eval/README.md).
- Tuần 12: kịch bản demo [docs/DEMO.md](docs/DEMO.md), bản nháp báo cáo [docs/BAO-CAO.md](docs/BAO-CAO.md), test e2e
  Playwright cho luồng demo (`cd web && npm run test:e2e`, cần server đang chạy).
- Chuyển lõi sang Dify ([specs/001-dify-core-migration/](specs/001-dify-core-migration/)): triage (an toàn + định
  tuyến), runner có kiểm duyệt từ khóa, review theo chính sách lớp, kho tri thức Dify cho từng lớp (trích dẫn nguồn trong
  câu trả lời), câu hỏi gợi ý tiếp theo, tool đi qua MCP over HTTP. Lõi cũ, bảng `document_chunks` (migration 0007) và
  dependency `langgraph` đã bị xóa. Bảng so sánh hai lõi ở [docs/BAO-CAO.md](docs/BAO-CAO.md).

Khi chạy với `LLM_PROVIDER=fake`, giám khảo không chấm được nên kiểm định luôn ra "cần xem lại" (trừ khi kiểm tra tĩnh
đã loại); số liệu thật cần khoá API.

## Dùng mô hình thật

Agent, triage và review dùng mô hình đã cấu hình trong Dify (Settings > Model Provider; xem
[infra/dify/README.md](infra/dify/README.md)). Nếu đổi model trong Dify, đặt `DIFY_TRIAGE_MODEL` và `DIFY_RUNNER_MODEL`
cho khớp để sổ chi phí ghi đúng tên.

Phần còn chạy trong backend (giám khảo kiểm định, báo cáo phụ huynh, `quiz_generator`, `rubric_grader`) dùng LLM
adapter. Mặc định `LLM_PROVIDER=fake` (chạy offline, trả lời giả). Để dùng Claude, đặt trong `.env`:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...        # model mặc định: claude-opus-5-5 (main), claude-haiku-5-5 (giám khảo)
```

Kiểm tra nhanh: `cd backend && uv run python -m scripts.check_llm`.

## Tracing (Langfuse)

Tắt mặc định. Tạo project trên [Langfuse](https://cloud.langfuse.com) (hoặc self-host), lấy API key rồi đặt trong `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=           # trống = Langfuse Cloud EU; https://us.cloud.langfuse.com hoặc http://localhost:3000
```

Mỗi lượt chat (và mỗi case kiểm định) là một trace với span `triage`, `run_agent` (kèm tool) và `review`. Trace gắn
`user_id`, `session_id` = id cuộc hội thoại, và id tin nhắn, id hội thoại phía Dify để tìm cùng lượt đó trong log của
Dify. Bước bị chặn có level `WARNING`; case kiểm định có score `certify_outcome`. Các bước bên trong app Dify do Dify tự
trace (bật Langfuse trong Dify, xem [infra/dify/README.md](infra/dify/README.md) mục Tracing). Lời gọi mô hình của
backend là generation (token, chi phí). Mọi chuỗi gửi đi đều qua bộ ẩn thông tin cá nhân (`app/tracing.py`).

## Ghi chú bản quyền

Mascot trong `web/src/assets/mascots` theo MIT (xem `LICENSE` cùng thư mục). Ảnh minh họa trong
`web/src/assets/illustrations` kế thừa từ team-8; `ASSET_SOURCES.md` chỉ ghi nguồn cho `creative-team.svg` (Storyset,
cần ghi công). Cần xác minh nguồn các ảnh `derived/*.webp` trước khi công khai.
