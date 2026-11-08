import json
import os

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from powerdns_api_proxy.config import get_environment_for_token, load_config
from powerdns_api_proxy.logging import logger

# PowerDNS rejects request bodies above webserver-max-bodysize (2 MB by
# default). Match that limit so the proxy never buffers more than the upstream
# would accept. Bodies without Content-Length are limited while streaming by
# RequestBodyLimitMiddleware (see proxy.py).
MAX_REQUEST_BODY_SIZE = 2 * 1024 * 1024

AUDIT_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

_config = load_config()

AUDIT_LOG_CLIENT_IP = os.getenv("AUDIT_LOG_CLIENT_IP", "false").lower() == "true"


def _content_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically log all API requests and their response status code"""

    async def dispatch(self, request: Request, call_next):
        if os.getenv("AUDIT_LOGGING", "true").lower() == "false":
            return await call_next(request)

        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        environment = None
        token = request.headers.get("X-API-Key", "")
        if token:
            try:
                environment = get_environment_for_token(_config, token)
            except Exception:  # noqa: BLE001  # audit logging must never fail a request
                logger.debug("Could not resolve environment for audit logging")

        # The audit trail must not become an unauthenticated memory or disk
        # sink: bodies are only buffered for authenticated requests, and only
        # when the declared size is known and within the limit. Streaming
        # bodies without Content-Length are left to RequestBodyLimitMiddleware.
        payload = None
        body_too_large = False
        content_length = _content_length(request)
        if request.method in AUDIT_BODY_METHODS:
            if content_length is not None and content_length > MAX_REQUEST_BODY_SIZE:
                body_too_large = True
            elif environment is not None and content_length is not None:
                try:
                    # Read raw request body bytes; FastAPI/Starlette will cache
                    # the body for downstream handlers.
                    body_bytes = await request.body()
                    if body_bytes:
                        payload = json.loads(body_bytes)
                except Exception:  # noqa: BLE001  # audit logging must never fail a request
                    logger.debug("Could not read request body for audit logging")

        query_params = dict(request.query_params) if request.query_params else None

        # Opt-in: client IPs are personal data (GDPR/DSGVO), so they are only
        # recorded when AUDIT_LOG_CLIENT_IP=true. When the peer address is
        # unavailable it is recorded as "unknown". Reflects X-Forwarded-For when
        # uvicorn's proxy_headers trusts the immediate peer -- see
        # FORWARDED_ALLOW_IPS in the README. request.client is None on
        # transports that omit "client" from the ASGI scope.
        if AUDIT_LOG_CLIENT_IP:
            client_ip = request.client.host if request.client else "unknown"
        else:
            client_ip = None

        path = request.url.path.replace("/api/v1/servers/localhost", "")
        status_code = 500
        try:
            # Reject before reading so an oversized body is never buffered.
            if body_too_large:
                response: Response = JSONResponse(
                    {"error": "Request body too large"},
                    status_code=413,
                )
            else:
                response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # Ensure that exceptions are logged as 500 responses while allowing
            # FastAPI/Starlette's normal exception handling to proceed.
            logger.exception("Unhandled exception during request processing")
            raise
        finally:
            # Log the request, even if an exception occurred
            logger.audit(
                environment.name if environment else "UNAUTHENTICATED",
                request.method,
                path,
                status_code,
                payload,
                query_params,
                client_ip,
            )
