import json
import logging
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from powerdns_api_proxy.logging import AuditLogger, JSONFormatter

PROJECT_ROOT = Path(__file__).resolve().parents[2]

LOGGING_PROBE = """
import powerdns_api_proxy.logging as proxy_logging

proxy_logging.logger.info("file logging probe")
"""


def _run_logging_probe(cwd: Path, log_file: Path | None = None) -> None:
    """Import the logging module in a clean process and emit one record."""
    env = os.environ.copy()
    env.pop("LOG_FILE", None)
    env["LOG_LEVEL"] = "INFO"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(PROJECT_ROOT)
    )

    if log_file is not None:
        env["LOG_FILE"] = str(log_file)

    completed = subprocess.run(
        [sys.executable, "-c", LOGGING_PROBE],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.fixture
def json_logger():
    """Create a logger with JSON formatter and string stream"""
    logger = AuditLogger("test")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    stream = StringIO()
    handler.stream = stream
    logger.addHandler(handler)

    return logger, stream


def test_audit_log_text_format(caplog):
    logger = logging.getLogger("test_audit_text")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_text"):
        logger.audit("Test1", "PATCH", "/zones/example.com", 204, {"rrsets": []})

    record = caplog.records[0]
    assert "AUDIT: Test1 PATCH /zones/example.com 204" in record.message
    assert "payload={'rrsets': []}" in record.message
    assert record.audit["environment"] == "Test1"
    assert record.audit["status_code"] == 204


def test_audit_log_text_format_with_query_params(caplog):
    logger = logging.getLogger("test_audit_query_text")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_query_text"):
        logger.audit("Test1", "GET", "/search-data", 200, query_params={"q": "test"})

    record = caplog.records[0]
    assert "AUDIT: Test1 GET /search-data 200" in record.message
    assert "query_params={'q': 'test'}" in record.message


def test_audit_log_text_format_no_extras(caplog):
    logger = logging.getLogger("test_audit_plain")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_plain"):
        logger.audit("Test1", "DELETE", "/zones/test.com", 403)

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 DELETE /zones/test.com 403"
    assert "payload" not in record.message
    assert "query_params" not in record.message


def test_audit_log_json_format(json_logger):
    logger, stream = json_logger

    logger.audit("Test1", "DELETE", "/zones/test.com", 403)
    log_data = json.loads(stream.getvalue().split("\n")[0])

    assert log_data["event_type"] == "audit"
    assert log_data["audit"] == {
        "environment": "Test1",
        "method": "DELETE",
        "path": "/zones/test.com",
        "status_code": 403,
    }
    assert "message" not in log_data
    assert "module" not in log_data

    stream.truncate(0)
    stream.seek(0)
    payload = {"rrsets": [{"name": "test.example.com"}]}
    logger.audit("Test1", "PATCH", "/zones/example.com", 204, payload)
    log_data = json.loads(stream.getvalue())
    assert log_data["audit"]["payload"] == payload

    stream.truncate(0)
    stream.seek(0)
    query_params = {"q": "example.com", "max": 10}
    logger.audit("Test1", "GET", "/search-data", 200, query_params=query_params)
    log_data = json.loads(stream.getvalue())
    assert log_data["audit"]["query_params"] == query_params
    assert log_data["audit"]["method"] == "GET"


def test_regular_log_json_format(json_logger):
    logger, stream = json_logger
    logger.info("Regular log message")

    log_data = json.loads(stream.getvalue())

    assert log_data["event_type"] == "log"
    assert log_data["message"] == "Regular log message"
    assert "module" in log_data
    assert "audit" not in log_data


def test_audit_log_skips_sensitive_payloads(caplog):
    logger = logging.getLogger("test_audit_cryptokeys")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_cryptokeys"):
        logger.audit(
            "Test1", "POST", "/zones/example.com/cryptokeys", 201, {"content": "secret"}
        )

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 POST /zones/example.com/cryptokeys 201"
    assert "payload" not in record.audit


def test_audit_log_skips_tsigkeys_payloads(caplog):
    logger = logging.getLogger("test_audit_tsigkeys")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_tsigkeys"):
        logger.audit("Test1", "PUT", "/tsigkeys/key1", 200, {"key": "secret"})

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 PUT /tsigkeys/key1 200"
    assert "payload" not in record.audit


def test_audit_log_text_format_with_client_ip(caplog):
    logger = logging.getLogger("test_audit_client_ip_text")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_client_ip_text"):
        logger.audit("Test1", "DELETE", "/zones/test.com", 403, client_ip="203.0.113.9")

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 203.0.113.9 DELETE /zones/test.com 403"
    assert record.audit["client_ip"] == "203.0.113.9"


def test_audit_log_text_format_client_ip_precedes_optional_extras(caplog):
    logger = logging.getLogger("test_audit_client_ip_extras")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_client_ip_extras"):
        logger.audit(
            "Test1",
            "PATCH",
            "/zones/example.com",
            204,
            {"rrsets": []},
            client_ip="203.0.113.9",
        )

    record = caplog.records[0]
    assert record.message == (
        "AUDIT: Test1 203.0.113.9 PATCH /zones/example.com 204 payload={'rrsets': []}"
    )


def test_audit_log_json_format_with_client_ip(json_logger):
    logger, stream = json_logger

    logger.audit("Test1", "PATCH", "/zones/example.com", 204, client_ip="203.0.113.9")
    log_data = json.loads(stream.getvalue())

    assert log_data["audit"] == {
        "environment": "Test1",
        "client_ip": "203.0.113.9",
        "method": "PATCH",
        "path": "/zones/example.com",
        "status_code": 204,
    }
    # client_ip is reported next to the identity it belongs to
    assert list(log_data["audit"])[:2] == ["environment", "client_ip"]


def test_audit_log_omits_client_ip_when_not_provided(caplog):
    """Regression guard: existing callers and log parsers must be unaffected."""
    logger = logging.getLogger("test_audit_client_ip_absent")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_client_ip_absent"):
        logger.audit("Test1", "DELETE", "/zones/test.com", 403)

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 DELETE /zones/test.com 403"
    assert "client_ip" not in record.audit


def test_audit_log_keeps_unknown_marker_out_of_the_text_message(caplog):
    """Only real addresses go into the text line; the marker stays JSON-only."""
    logger = logging.getLogger("test_audit_client_ip_unknown")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_client_ip_unknown"):
        logger.audit("Test1", "GET", "/zones", 401, client_ip="unknown")

    record = caplog.records[0]
    assert record.message == "AUDIT: Test1 GET /zones 401"
    assert record.audit["client_ip"] == "unknown"


def test_audit_log_keeps_payload_for_zone_named_like_sensitive_endpoint(caplog):
    logger = logging.getLogger("test_audit_zone_name_collision")
    logger.setLevel(logging.INFO)
    logger.__class__ = AuditLogger

    with caplog.at_level(logging.INFO, logger="test_audit_zone_name_collision"):
        logger.audit(
            "Test1",
            "PATCH",
            "/zones/tsigkeys.example.com./rrsets",
            200,
            {"rrsets": []},
        )

    record = caplog.records[0]
    assert "payload" in record.audit


def test_no_log_file_written_when_log_file_unset(tmp_path: Path):
    _run_logging_probe(tmp_path)

    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path / "log").exists()


def test_log_file_written_when_log_file_set(tmp_path: Path):
    log_file = tmp_path / "proxy.log"

    _run_logging_probe(tmp_path, log_file)

    assert "file logging probe" in log_file.read_text()
    assert not (tmp_path / "log").exists()
