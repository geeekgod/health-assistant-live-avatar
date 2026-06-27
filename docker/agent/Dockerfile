# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1
COPY agent/pyproject.toml agent/uv.lock ./
COPY agent/livekit_worker ./livekit_worker
RUN uv sync --frozen --no-dev
ARG SKIP_DOWNLOAD=false
RUN if [ "$SKIP_DOWNLOAD" != "true" ]; then uv run python -m livekit_worker.worker download-files; fi

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Asia/Kolkata
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 gosu tzdata procps \
    && ln -sf /usr/share/zoneinfo/Asia/Kolkata /etc/localtime \
    && echo "Asia/Kolkata" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home appuser
COPY --from=build --chown=appuser:appuser /app /app
COPY docker/agent/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD [".venv/bin/python", "-m", "livekit_worker.worker", "start"]
