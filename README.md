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
uv run uvicorn app.main:app --reload --port 8001

# Frontend (http://127.0.0.1:5173, proxy /api -> 8001)
cd web
npm install
npm run dev
```

## Kiểm tra

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd web && npm test && npm run build
```

Test backend không cần database hay API key (LLM adapter `fake`).

## Trạng thái

Theo kế hoạch 12 tuần. Tuần 1: khung repo, UI đã rebrand, 4 vai trò (giáo viên, học sinh, phụ huynh, quản trị viên)
với các màn giữ chỗ, backend skeleton có health check và migration bật pgvector.

## Ghi chú bản quyền

Mascot trong `web/src/assets/mascots` theo MIT (xem `LICENSE` cùng thư mục). Ảnh minh họa trong
`web/src/assets/illustrations` kế thừa từ team-8; `ASSET_SOURCES.md` chỉ ghi nguồn cho `creative-team.svg` (Storyset,
cần ghi công). Cần xác minh nguồn các ảnh `derived/*.webp` trước khi công khai.
