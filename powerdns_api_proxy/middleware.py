import json
import os

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from powerdns_api_proxy.config import get_environment_for_token, load_config
from powerdns_api_proxy.logging import logger

_config = load_config()


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
        except Exception:
            pass

        # Store request body for logging (only for write operations)
        payload = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Read raw request body bytes; FastAPI/Starlette will cache the body for downstream handlers
                body_bytes = await request.body()
                if body_bytes:
                    payload = json.loads(body_bytes)
            except Exception:
                pass

        query_params = dict(request.query_params) if request.query_params else None

        path = request.url.path.replace("/api/v1/servers/localhost", "")
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
            )
