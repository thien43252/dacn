# EduAgent Hub

Nền tảng mở (B2C) để giáo viên tạo lớp, thêm học sinh và phụ huynh, rồi cài agent AI từ Hub vào lớp. Trọng tâm là
lớp tin cậy: orchestrator theo lớp có chính sách lớp, guardrails 3 lớp, và certification pipeline kiểm định agent trước
khi lên Hub. Đồ án cá nhân, chạy local trên dữ liệu demo.

## Cấu trúc

| Thư mục | Nội dung |
| --- | --- |
| `web/` | React 19 + Vite + plain CSS. UI kế thừa từ Vinschool Capstone Studio (team-8), đã cắt phần nghiệp vụ cũ |
| `backend/` | FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL + pgvector. Core AI (LangGraph, guard, certify) trong `app/` |
| `infra/` | Docker Compose cho Postgres + pgvector (cổng host 5433) |
| `eval/` | Dataset red-team tiếng Việt, routing set, script thực nghiệm |
| `seed/` | Manifest agent mẫu, dữ liệu lớp demo |
| `docs/` | Thiết kế và báo cáo |

## Chạy local

Cần Node.js, Python 3.11, [uv](https://docs.astral.sh/uv/) và Docker Desktop.

```bash
cp .env.example .env

# Database
docker compose -f infra/docker-compose.yml up -d --wait

# Backend (http://127.0.0.1:8001)
cd backend
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_demo   # 4 tài khoản demo, mật khẩu Demo123!
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

Test backend không cần database hay API key (LLM adapter `fake`).

## Trạng thái

Theo kế hoạch 12 tuần ([docs/PLAN.md](docs/PLAN.md)).

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

Chọn agent hiện theo `@mention` hoặc rơi về `tro-ly-lop`; router bằng LLM là tuần 7, guard đầu vào/đầu ra là tuần 8.

## Dùng mô hình thật

Mặc định `LLM_PROVIDER=fake` (chạy offline, trả lời giả). Để dùng Claude, đặt trong `.env`:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...        # model mặc định: claude-opus-5-5 (agent), claude-haiku-5-5 (guard, router)
EMBEDDING_PROVIDER=openai    # hoặc gemini; Anthropic không có API embedding
OPENAI_API_KEY=...
```

Đổi provider embedding thì cần xử lý lại tài liệu (nút "Xử lý lại" hoặc tải lên lại), vì vector của mỗi mô hình khác nhau.

## Ghi chú bản quyền

Mascot trong `web/src/assets/mascots` theo MIT (xem `LICENSE` cùng thư mục). Ảnh minh họa trong
`web/src/assets/illustrations` kế thừa từ team-8; `ASSET_SOURCES.md` chỉ ghi nguồn cho `creative-team.svg` (Storyset,
cần ghi công). Cần xác minh nguồn các ảnh `derived/*.webp` trước khi công khai.
