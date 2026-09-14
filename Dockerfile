FROM docker.io/python:3.14.6-slim@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144

WORKDIR /app

# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app
ENV PATH=/venv/bin:$PATH
RUN : \
    && python3 -m venv /venv \
    && pip --no-cache-dir install -r requirements.txt

COPY . /app

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN : \
    && adduser -u 1000 --disabled-password --gecos "" appuser \
    && chown -R appuser /app && chmod -R 0750 /app
USER appuser


CMD ["python", "-m", "powerdns_api_proxy"]
