# Backend image for the timetable API. Uses uv (the project's only package
# manager) via the official Astral image, so the same pyproject.toml/uv.lock
# that drive local `uv sync` drive the container. Startups run migrations
# through docker/entrypoint.sh before serving, so `docker compose up` on a
# fresh Postgres volume lands on a migrated schema (same as `alembic upgrade
# head` locally).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached unless pyproject.toml / uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the app code + migration entrypoint.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
