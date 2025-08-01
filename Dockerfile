FROM docker.io/python:3.13.5-slim

WORKDIR /app

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


CMD ["uvicorn", "--host", "*", "--port", "8000", "powerdns_api_proxy.proxy:app"]
