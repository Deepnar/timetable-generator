#!/bin/sh
# Container entrypoint: run pending migrations, then serve the API.
# Uses `uv run` so the synced .venv is used exactly like local dev.
set -e

echo "[entrypoint] applying pending migrations"
uv run alembic upgrade head

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
