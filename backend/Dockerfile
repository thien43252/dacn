# Build context = repo root (the app reads ../seed and ../eval). Multi-arch: works on Oracle ARM and x86.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY seed/ /app/seed/
COPY eval/ /app/eval/
RUN chmod +x /app/backend/scripts/entrypoint.sh

EXPOSE 8001
ENTRYPOINT ["/app/backend/scripts/entrypoint.sh"]
