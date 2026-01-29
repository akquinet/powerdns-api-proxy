import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, audit_log_path: str):
        self.audit_log_path = Path(audit_log_path)

    def log_change(
        self,
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

        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_unauthorized(
        self,
        method: str,
        path: str,
        status_code: int,
    ):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": "UNAUTHORIZED",
            "method": method,
            "path": path,
            "payload": None,
            "status_code": status_code,
        }

        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
