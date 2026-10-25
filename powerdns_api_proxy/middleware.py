import json
import os

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from powerdns_api_proxy.config import get_environment_for_token, load_config
from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.metrics import AUTH_FAILURES_TOTAL, AUTH_RATE_LIMITED_TOTAL
from powerdns_api_proxy.rate_limit import AuthFailureRateLimiter, RateLimitConfig

_config = load_config()

AUDIT_LOG_CLIENT_IP = os.getenv("AUDIT_LOG_CLIENT_IP", "false").lower() == "true"

_rate_limiter = AuthFailureRateLimiter(RateLimitConfig.from_env())

_PROTECTED_PATHS = ("/api", "/health/pdns")
_PROTECTED_PREFIXES = ("/api/v1/", "/info/")


def _audit_path(path: str) -> str:
    return path.replace("/api/v1/servers/localhost", "")


def _is_token_protected(path: str) -> bool:
    return path in _PROTECTED_PATHS or path.startswith(_PROTECTED_PREFIXES)


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically log all API requests and their response status code"""

    async def dispatch(self, request: Request, call_next):
        if os.getenv("AUDIT_LOGGING", "true").lower() == "false":
            return await call_next(request)

        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        environment_name = "UNAUTHENTICATED"
        try:
            token = request.headers.get("X-API-Key", "")
            if token:
                environment = get_environment_for_token(_config, token)
                environment_name = environment.name
        except Exception:  # noqa: BLE001  # audit logging must never fail a request
            logger.debug("Could not resolve environment for audit logging")

        # Store request body for logging (only for write operations)
        payload = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Read raw request body bytes; FastAPI/Starlette will cache the body for downstream handlers
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

        path = _audit_path(request.url.path)
        status_code = 500
        try:
            # Call the actual endpoint
            response: Response = await call_next(request)
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
                environment_name,
                request.method,
                path,
                status_code,
                payload,
                query_params,
                client_ip,
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests from IPs with too many failed token authentications.

    This middleware must be the outermost user middleware. Blocked requests then
    skip the audit and metrics token lookups as well as every auth hash, and the
    default HTTP instrumentator does not count the 429 responses it produces.
    """

    def __init__(
        self,
        app,
        limiter: AuthFailureRateLimiter | None = None,
    ):
        super().__init__(app)
        self.limiter = limiter if limiter is not None else _rate_limiter

    async def dispatch(self, request: Request, call_next):
        if not self.limiter.config.enabled or not _is_token_protected(request.url.path):
            return await call_next(request)

        key = request.client.host if request.client else "unknown"
        retry_after = self.limiter.retry_after(key)
        if retry_after is not None:
            AUTH_RATE_LIMITED_TOTAL.inc()
            self._audit_blocked(request)
            return JSONResponse(
                {"error": "Too many failed authentication attempts"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)

        if getattr(request.state, "token_authenticated", False):
            self.limiter.record_success(key)
        elif response.status_code == 401 and request.headers.get("X-API-Key"):
            AUTH_FAILURES_TOTAL.inc()
            self.limiter.record_failure(key)

        return response

    @staticmethod
    def _audit_blocked(request: Request) -> None:
        if os.getenv("AUDIT_LOGGING", "true").lower() == "false":
            return

        if AUDIT_LOG_CLIENT_IP:
            client_ip = request.client.host if request.client else "unknown"
        else:
            client_ip = None

        logger.audit(
            environment="RATE_LIMITED",
            method=request.method,
            path=_audit_path(request.url.path),
            status_code=429,
            query_params=dict(request.query_params) if request.query_params else None,
            client_ip=client_ip,
        )
