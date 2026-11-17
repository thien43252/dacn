#!/bin/sh
set -e
alembic upgrade head
if [ "${SEED_DEMO:-1}" = "1" ]; then
  python -m scripts.seed_demo --ensure
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips="*"
