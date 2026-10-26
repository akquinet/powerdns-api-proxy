import os

import anyio
import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# Must be set before importing the proxy, which loads the config at import time
os.environ["PROXY_CONFIG_PATH"] = "./config-example.yml"

from powerdns_api_proxy import middleware
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


VALID_TOKEN = "lashflkashlfgkashglashglashgl"


def test_middleware_logs_post_request_with_payload(client, caplog):
    payload = {"name": "test.com", "kind": "Native"}

    client.post(
        "/api/v1/servers/localhost/zones",
        json=payload,
        headers={"X-API-Key": VALID_TOKEN},
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


def _audit_record(caplog):
    audit_records = [r for r in caplog.records if hasattr(r, "audit")]
    assert len(audit_records) > 0
    return audit_records[0].audit


def test_middleware_does_not_log_payload_without_valid_token(client, caplog):
    """An unauthenticated caller must not be able to write bodies to the log."""
    client.post(
        "/api/v1/servers/localhost/zones",
        json={"name": "test.com", "junk": "x" * 100},
        headers={"X-API-Key": "invalid"},
    )

    audit = _audit_record(caplog)
    assert audit["environment"] == "UNAUTHENTICATED"
    assert "payload" not in audit


def test_middleware_truncates_large_payload(client, caplog):
    """Payloads are capped so one request cannot flood or rotate the audit log."""
    client.post(
        "/api/v1/servers/localhost/zones",
        json={"name": "test.com", "junk": "x" * 5000},
        headers={"X-API-Key": VALID_TOKEN},
    )

    audit = _audit_record(caplog)
    assert isinstance(audit["payload"], str)
    assert audit["payload"].startswith("<truncated payload: ")


def test_middleware_rejects_oversized_body_before_buffering(client, caplog):
    """The body limit applies before authentication and is never read/logged."""
    body = b'{"name": "' + b"a" * middleware.MAX_REQUEST_BODY_SIZE + b'"}'

    response = client.post(
        "/api/v1/servers/localhost/zones",
        content=body,
        headers={"X-API-Key": "invalid", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {"error": "Request body too large"}

    audit = _audit_record(caplog)
    assert audit["environment"] == "UNAUTHENTICATED"
    assert audit["status_code"] == 413
    assert "payload" not in audit


def _asgi_get_without_client(target_app, path):
    """Invoke the ASGI app directly with no ``client`` key in the scope.

    Some ASGI transports (e.g. unix sockets) omit it, which makes
    ``request.client`` None.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"x-api-key", b"invalid")],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        pass

    anyio.run(target_app, scope, receive, send)


def test_middleware_logs_forwarded_client_ip(caplog, monkeypatch):
    """The reverse-proxy path: uvicorn rewrites the peer from X-Forwarded-For."""
    monkeypatch.setattr(middleware, "AUDIT_LOG_CLIENT_IP", True)
    proxied_app = ProxyHeadersMiddleware(app, trusted_hosts="testclient")
    proxied_client = TestClient(proxied_app)

    proxied_client.get(
        "/api/v1/servers/localhost/zones",
        headers={"X-API-Key": "invalid", "X-Forwarded-For": "203.0.113.9"},
    )

    assert _audit_record(caplog)["client_ip"] == "203.0.113.9"


def test_middleware_logs_rightmost_untrusted_hop_of_forwarded_chain(
    caplog, monkeypatch
):
    """A hop the client forged on the left must not win over the real one."""
    monkeypatch.setattr(middleware, "AUDIT_LOG_CLIENT_IP", True)
    proxied_app = ProxyHeadersMiddleware(app, trusted_hosts="testclient,10.0.0.7")
    proxied_client = TestClient(proxied_app)

    proxied_client.get(
        "/api/v1/servers/localhost/zones",
        headers={
            "X-API-Key": "invalid",
            # 198.51.100.5 is client-supplied and untrustworthy, 10.0.0.7 is our
            # own proxy, so 203.0.113.9 is the first hop we can actually vouch for
            "X-Forwarded-For": "198.51.100.5, 203.0.113.9, 10.0.0.7",
        },
    )

    assert _audit_record(caplog)["client_ip"] == "203.0.113.9"


def test_middleware_omits_client_ip_by_default(client, caplog, monkeypatch):
    """Client IPs are personal data and must not be logged unless opted in."""
    monkeypatch.setattr(middleware, "AUDIT_LOG_CLIENT_IP", False)
    client.get(
        "/api/v1/servers/localhost/zones",
        headers={"X-API-Key": "invalid"},
    )

    audit = _audit_record(caplog)
    assert "client_ip" not in audit
    # the rest of the audit trail is untouched
    assert audit["method"] == "GET"
    assert "/zones" in audit["path"]


def test_middleware_marks_client_ip_unknown_when_peer_unknown(caplog, monkeypatch):
    """A transport without a peer address must not raise; mark it unknown."""
    monkeypatch.setattr(middleware, "AUDIT_LOG_CLIENT_IP", True)

    _asgi_get_without_client(app, "/api/v1/servers/localhost/zones")

    assert _audit_record(caplog)["client_ip"] == "unknown"
