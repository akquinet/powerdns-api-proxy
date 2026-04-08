import logging
import logging.handlers
import json
from os import getenv
from sys import stderr

LOG_LEVEL = getenv("LOG_LEVEL") or "DEBUG"
LOG_FORMAT = getenv("LOG_FORMAT", "text").lower()  # text or json

logging_format = (
    "%(levelname)s - %(asctime)s - %(name)s - "
    + "%(filename)s - %(funcName)s - %(lineno)s - %(message)s"
)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, str | int | dict] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
        }

        # Special handling for audit logs
        if hasattr(record, "audit"):
            log_data["event_type"] = "audit"
            log_data["audit"] = record.audit
        else:
            # Regular logs include full context
            log_data["event_type"] = "log"
            log_data["logger"] = record.name
            log_data["message"] = record.getMessage()
            log_data["module"] = record.module
            log_data["function"] = record.funcName
            log_data["line"] = record.lineno

            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class AuditLogger(logging.Logger):
    """Custom logger with audit() method"""

    def audit(
        self,
        environment: str,
        method: str,
        path: str,
        status_code: int,
        payload: dict | None = None,
        query_params: dict | None = None,
    ):
        """Log audit events with structured data"""
        # Skip payload logging for sensitive endpoints
        if payload is not None and any(
            sensitive in path for sensitive in ["/cryptokeys", "/tsigkeys"]
        ):
            payload = None

        audit_data = {
            "environment": environment,
            "method": method,
            "path": path,
            "status_code": status_code,
        }
        if payload is not None:
            audit_data["payload"] = payload
        if query_params is not None and query_params:
            audit_data["query_params"] = query_params

        # Build message with optional query_params/payload info
        msg_parts = [f"AUDIT: {environment} {method} {path} {status_code}"]
        if query_params:
            msg_parts.append(f"query_params={query_params}")
        if payload is not None:
            msg_parts.append(f"payload={payload}")

        self.info(
            " ".join(msg_parts),
            extra={"audit": audit_data},
            stacklevel=2,
        )


logging.setLoggerClass(AuditLogger)

if LOG_FORMAT == "json":
    default_formatter: logging.Formatter = JSONFormatter()
else:
    default_formatter = logging.Formatter(logging_format)

default_stream_handler = logging.StreamHandler(stderr)
default_stream_handler.setLevel(LOG_LEVEL)
default_stream_handler.setFormatter(default_formatter)

logger: AuditLogger = logging.getLogger("powerdns_api_proxy")  # type: ignore
logger.addHandler(default_stream_handler)

LOG_FILE = getenv("LOG_FILE", "log")
if LOG_FILE and LOG_FILE.lower() != "false":
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=LOG_FILE, maxBytes=1000**2 * 100, backupCount=5
        )
        file_handler.setLevel(LOG_LEVEL)
        file_handler.setFormatter(default_formatter)
        logger.addHandler(file_handler)
    except OSError as e:
        logger.error(f"Failed to enable file logging to {LOG_FILE}: {e}")

logger.setLevel("DEBUG")
