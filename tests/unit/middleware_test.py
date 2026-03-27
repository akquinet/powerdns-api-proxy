import pytest
from fastapi.testclient import TestClient

from powerdns_api_proxy.proxy import app


@pytest.fixture
def client():
    return TestClient(app)


def test_middleware_logs_get_request(client, caplog):
    # This will fail auth but middleware should still log
    client.get(
        "/api/v1/servers/localhost/zones",
        headers={"X-API-Key": "invalid"},
    )

    # Check audit log was created
    audit_records = [r for r in caplog.records if hasattr(r, "audit")]
    assert len(audit_records) > 0

    audit = audit_records[0].audit
    assert audit["method"] == "GET"
    assert "/zones" in audit["path"]


def test_middleware_logs_post_request_with_payload(client, caplog):
    payload = {"name": "test.com", "kind": "Native"}

    client.post(
        "/api/v1/servers/localhost/zones",
        json=payload,
        headers={"X-API-Key": "invalid"},
    )

    audit_records = [r for r in caplog.records if hasattr(r, "audit")]
    assert len(audit_records) > 0

    audit = audit_records[0].audit
    assert audit["method"] == "POST"
    assert audit["payload"] == payload


def test_middleware_logs_query_params(client, caplog):
    client.get(
        "/api/v1/servers/localhost/zones?rrsets=true",
        headers={"X-API-Key": "invalid"},
    )

    audit_records = [r for r in caplog.records if hasattr(r, "audit")]
    assert len(audit_records) > 0

    audit = audit_records[0].audit
    assert audit["query_params"] == {"rrsets": "true"}
