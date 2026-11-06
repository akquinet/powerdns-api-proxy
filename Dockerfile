FROM docker.io/python:3.15.0-slim@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY powerdns_api_proxy /app/powerdns_api_proxy
RUN uv sync --frozen --no-dev


FROM docker.io/python:3.15.0-slim@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

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

EXPOSE 8000

CMD ["python", "-m", "powerdns_api_proxy"]
