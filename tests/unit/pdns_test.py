import asyncio
import logging
from unittest.mock import patch

import pytest

from powerdns_api_proxy.exceptions import UpstreamException
from powerdns_api_proxy.pdns import PDNSConnector, PDNSResponse


class _AsyncContextManager:
    """Minimal async context manager yielding a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.request_kwargs: dict = {}

    def request(self, *args, **kwargs):
        self.request_kwargs = kwargs
        return _AsyncContextManager(self._response)


def _run_request(path: str, payload: dict, response_text: str):
    connector = PDNSConnector("http://pdns.example", "upstream-token")
    session = _FakeSession(_FakeResponse(response_text))
    with patch(
        "powerdns_api_proxy.pdns.aiohttp.ClientSession",
        return_value=_AsyncContextManager(session),
    ):
        asyncio.run(connector.request("POST", path, payload=payload))


def test_tsigkey_payload_is_not_logged(caplog):
    """The secret of a TSIG key must not end up in the logs"""
    with caplog.at_level(logging.DEBUG, logger="powerdns_api_proxy"):
        _run_request(
            "/api/v1/servers/localhost/tsigkeys",
            {"name": "test", "key": "SUPER_SECRET_TSIG_KEY"},
            '{"key": "SUPER_SECRET_TSIG_KEY"}',
        )
    assert "SUPER_SECRET_TSIG_KEY" not in caplog.text
    assert "<redacted>" in caplog.text


def test_cryptokey_response_is_not_logged(caplog):
    """The private key of a CryptoKey must not end up in the logs"""
    with caplog.at_level(logging.DEBUG, logger="powerdns_api_proxy"):
        _run_request(
            "/api/v1/servers/localhost/zones/example.com./cryptokeys/1",
            {},
            '{"privatekey": "SUPER_SECRET_PRIVATE_KEY"}',
        )
    assert "SUPER_SECRET_PRIVATE_KEY" not in caplog.text
    assert "<redacted>" in caplog.text


def test_other_paths_are_still_logged(caplog):
    """Requests without key material keep their previous log output"""
    with caplog.at_level(logging.DEBUG, logger="powerdns_api_proxy"):
        _run_request(
            "/api/v1/servers/localhost/zones/example.com.",
            {"rrsets": [{"name": "test.example.com."}]},
            '{"name": "example.com."}',
        )
    assert "test.example.com." in caplog.text
    assert "<redacted>" not in caplog.text


def test_zone_named_like_sensitive_endpoint_is_still_logged(caplog):
    """A zone whose name merely contains 'tsigkeys' must not be redacted"""
    with caplog.at_level(logging.DEBUG, logger="powerdns_api_proxy"):
        _run_request(
            "/api/v1/servers/localhost/zones/tsigkeys.example.com./rrsets",
            {"rrsets": [{"name": "test.tsigkeys.example.com."}]},
            '{"name": "tsigkeys.example.com."}',
        )
    assert "test.tsigkeys.example.com." in caplog.text
    assert "<redacted>" not in caplog.text


def test_upstream_requests_do_not_follow_redirects():
    """aiohttp forwards custom headers to the redirect target, so following a
    redirect would hand the upstream X-API-Key to that location."""
    connector = PDNSConnector("http://pdns.example", "upstream-token")
    session = _FakeSession(_FakeResponse("[]"))
    with patch(
        "powerdns_api_proxy.pdns.aiohttp.ClientSession",
        return_value=_AsyncContextManager(session),
    ):
        asyncio.run(connector.get("/api/v1/servers"))
    assert session.request_kwargs["allow_redirects"] is False


def test_upstream_redirect_is_reported_as_upstream_error():
    """A 3xx must not be treated as a successful upstream answer."""
    with pytest.raises(UpstreamException):
        PDNSResponse("", 302).raise_for_error()
