import json
import logging
from io import StringIO

import pytest

from powerdns_api_proxy.logging import AuditLogger, JSONFormatter


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
