import json
from datetime import datetime, timezone
from pathlib import Path

from powerdns_api_proxy.logging import logger


def log_change(
    audit_log_path: str,
    environment_name: str,
    method: str,
    path: str,
    payload: dict | None,
    status_code: int,
):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": environment_name,
        "method": method,
        "path": path,
        "payload": payload,
        "status_code": status_code,
    }

    logger.info(f"{environment_name} {method} {path} -> {status_code}")

    with open(Path(audit_log_path), "a") as f:
        f.write(json.dumps(entry) + "\n")
