# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install dependencies first, separately from app code, so dependency
# resolution is cached across builds that only change source files.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --no-dev

EXPOSE 8000

# UV_NO_SYNC=1 above is what matters: without it, `uv run` re-resolves and
# re-syncs (including downloading the dev dependency group) against uv.lock
# on every container start, which is both wasted time and a runtime
# dependency on network access that a container should not have.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["uv", "run", "uvicorn", "argus.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
