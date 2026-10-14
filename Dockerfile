FROM docker.io/python:3.14.1-slim@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY powerdns_api_proxy /app/powerdns_api_proxy
RUN uv sync --frozen --no-dev


FROM docker.io/python:3.14.1-slim@sha256:b823ded4377ebb5ff1af5926702df2284e53cecbc6e3549e93a19d8632a1897e

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY powerdns_api_proxy /app/powerdns_api_proxy

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN : \
    && adduser -u 1000 --disabled-password --gecos "" appuser \
    && chown -R appuser /app && chmod -R 0750 /app
USER appuser


CMD ["python", "-m", "powerdns_api_proxy"]
