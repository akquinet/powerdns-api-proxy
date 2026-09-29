import os
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from powerdns_api_proxy.models import (
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
)
from powerdns_api_proxy.pdns import PDNSResponse

os.environ["PROXY_CONFIG_PATH"] = "./config-example.yml"

from powerdns_api_proxy.proxy import app  # noqa: E402

client = TestClient(app)

api_key = "lashflkashlfgkashglashglashgl"
api_key_sha512 = "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"  # noqa: E501

environment = ProxyConfigEnvironment(
    name="subzones",
    token_sha512=api_key_sha512,
    zones=[
        ProxyConfigZone(name="example.com.", subzones=True),
        ProxyConfigZone(name="münchen.example.de.", subzones=True),
    ],
)
proxy_config = ProxyConfig(
    pdns_api_token="upstream",
    pdns_api_url="http://127.0.0.1:1",
    environments=[environment],
)
headers = {"X-API-Key": api_key}
rrsets = {
    "rrsets": [
        {
            "name": "www.other.org.",
            "type": "A",
            "changetype": "REPLACE",
            "ttl": 60,
            "records": [{"content": "192.0.2.1", "disabled": False}],
        }
    ]
}


@pytest.fixture()
def upstream() -> Generator[AsyncMock, None, None]:
    pdns = AsyncMock()
    with (
        patch("powerdns_api_proxy.config.load_config", return_value=proxy_config),
        patch("powerdns_api_proxy.proxy.config", proxy_config),
        patch("powerdns_api_proxy.proxy.pdns", pdns),
        patch(
            "powerdns_api_proxy.proxy.handle_pdns_response",
            AsyncMock(return_value=PDNSResponse({}, 204)),
        ),
    ):
        yield pdns


@pytest.mark.parametrize(
    "zone_id",
    [
        "other.org.%3F.example.com.",
        "other.org.%23.example.com.",
        "other.org.%25.example.com.",
        "other.org.%5C.example.com.",
        "other.org.%20.example.com.",
        "other.org.%0A.example.com.",
    ],
)
@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_zone_id_injection_rejected(upstream, method, zone_id):
    path = f"/api/v1/servers/localhost/zones/{zone_id}"
    response = client.request(method, path, headers=headers, json=rrsets)
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid value for path parameter zone_id"
    assert not upstream.method_calls


def test_subzone_patch_still_forwarded(upstream):
    response = client.patch(
        "/api/v1/servers/localhost/zones/sub.example.com.",
        headers=headers,
        json={"rrsets": [dict(rrsets["rrsets"][0], name="www.sub.example.com.")]},
    )
    assert response.status_code == 204
    upstream.patch.assert_awaited_once()
    assert (
        upstream.patch.await_args.args[0]
        == "/api/v1/servers/localhost/zones/sub.example.com."
    )


def test_cryptokey_id_injection_rejected(upstream):
    response = client.get(
        "/api/v1/servers/localhost/zones/example.com./cryptokeys/1%3Fx",
        headers=headers,
    )
    assert response.status_code == 400
    assert not upstream.method_calls


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/servers/other",
        "/api/v1/servers/other/zones",
        "/api/v1/servers/other/zones/example.com.",
    ],
)
def test_unknown_server_id(upstream, path):
    response = client.get(path, headers=headers)
    assert response.status_code == 404
    assert not upstream.method_calls


def test_utf8_zone_id_forwarded(upstream):
    response = client.patch(
        "/api/v1/servers/localhost/zones/münchen.example.de.",
        headers=headers,
        json={"rrsets": [dict(rrsets["rrsets"][0], name="www.münchen.example.de.")]},
    )
    assert response.status_code == 204
    upstream.patch.assert_awaited_once()
    assert (
        upstream.patch.await_args.args[0]
        == "/api/v1/servers/localhost/zones/münchen.example.de."
    )


def test_utf8_zone_id_injection_rejected(upstream):
    response = client.patch(
        "/api/v1/servers/localhost/zones/münchen.other.org.%3Fexample.de.",
        headers=headers,
        json=rrsets,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid value for path parameter zone_id"
    assert not upstream.method_calls
