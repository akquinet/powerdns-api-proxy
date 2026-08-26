import hashlib
import json
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

from powerdns_api_proxy.exceptions import NotAuthorizedException
from powerdns_api_proxy.proxy import app

client = TestClient(app)


dummy_proxy_zone = ProxyConfigZone(name="test.example.com.")
dummy_proxy_environment_token = "lashflkashlfgkashglashglashgl"
dummy_proxy_environment_token_sha512 = "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"  # noqa: E501
dummy_proxy_environment_token2 = "aslkghlskdhglkwhegklwhelghwleghwle"
dummy_proxy_environment_token2_sha512 = "1954a12ef0bf45b3a1797437509037f178af846d880115d57668a8aaa05732deedcbbd02bfa296b4f4e043b437b733fd6131933cfdc0fb50c4cf7f9f2bdaa836"  # noqa: E501

dummy_proxy_environment = ProxyConfigEnvironment(
    name="Test 1",
    zones=[dummy_proxy_zone],
    token_sha512=dummy_proxy_environment_token_sha512,
)
dummy_proxy_environment2 = ProxyConfigEnvironment(
    name="Test 2",
    zones=[dummy_proxy_zone],
    token_sha512=dummy_proxy_environment_token2_sha512,
)
dummy_proxy_config = ProxyConfig(
    pdns_api_token="blaaa",
    pdns_api_url="bluub",
    environments=[dummy_proxy_environment, dummy_proxy_environment2],
)

os.environ["PROXY_CONFIG_PATH"] = "./config-example.yml"


@pytest.fixture()
def fixture_patch_dummy_config() -> Generator[None, None, None]:
    with patch("powerdns_api_proxy.config.load_config") as load_config_patch:
        load_config_patch.return_value = dummy_proxy_config
        yield


@pytest.fixture()
def fixture_patch_pdns() -> Generator[AsyncMock, None, None]:
    with patch("powerdns_api_proxy.proxy.PDNSConnector") as pdns_patch:
        pdns_patch = AsyncMock()
        yield pdns_patch


def test_index_default_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PowerDNS API Proxy" in response.text


def test_index_custom_html():
    custom_html = "<html><body><h1>Custom Page</h1></body></html>"
    custom_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[dummy_proxy_environment],
        index_html=custom_html,
    )

    with patch("powerdns_api_proxy.proxy.config", custom_config):
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == custom_html
        assert "<h1>Custom Page</h1>" in response.text


def test_index_disabled():
    custom_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[dummy_proxy_environment],
        index_enabled=False,
    )

    with patch("powerdns_api_proxy.proxy.config", custom_config):
        response = client.get("/")
        assert response.status_code == 404


def test_api_root(fixture_patch_dummy_config):
    answer = client.get("/api", headers={"X-API-Key": dummy_proxy_environment_token})
    data = answer.json()
    print(data)
    assert answer.status_code == 200
    assert 1 == data[0].get("version")
    assert data[0].get("compatibility")


def _wrong_token_request(client: TestClient, method: str, path: str):
    answer = client.request(method, path, headers={"X-API-Key": "alsdjlkasjdlld"})
    print(answer.json())
    assert answer.status_code == 401
    assert answer.json()["error"] == NotAuthorizedException().detail


def _token_missing_request(client: TestClient, method: str, path: str):
    answer = client.request(method, path)
    print(answer.json())
    assert answer.status_code == 422


get_routes = [
    "/info/allowed",
    "/info/zone-allowed",
    "/api",
    "/api/v1/servers",
    "/api/v1/servers/localhost",
    "/api/v1/servers/localhost/config",
    "/api/v1/servers/localhost/config/api-key",
    "/api/v1/servers/localhost/statistics",
    "/api/v1/servers/localhost/zones",
    "/api/v1/servers/localhost/zones/test.example.com.",
    "/api/v1/servers/localhost/search-data?q='test.example.com.'",
]


@pytest.mark.parametrize("path", get_routes)
def test_api_get_wrong_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _wrong_token_request(client, "GET", path)


@pytest.mark.parametrize("path", get_routes)
def test_api_get_missing_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _token_missing_request(client, "GET", path)


post_routes = ["/api/v1/servers/localhost/zones"]


@pytest.mark.parametrize("path", post_routes)
def test_api_post_wrong_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _wrong_token_request(client, "POST", path)


@pytest.mark.parametrize("path", post_routes)
def test_api_post_missing_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _token_missing_request(client, "POST", path)


put_routes = [
    "/api/v1/servers/localhost/zones/test-zone.example.com.",
    "/api/v1/servers/localhost/zones/test-zone.example.com./notify",
    "/api/v1/servers/localhost/zones/test-zone.example.com./rectify",
]


@pytest.mark.parametrize("path", put_routes)
def test_api_put_wrong_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _wrong_token_request(client, "PUT", path)


@pytest.mark.parametrize("path", put_routes)
def test_api_put_missing_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _token_missing_request(client, "PUT", path)


patch_routes = ["/api/v1/servers/localhost/zones/test-zone.example.com."]


@pytest.mark.parametrize("path", patch_routes)
def test_api_patch_wrong_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _wrong_token_request(client, "PATCH", path)


@pytest.mark.parametrize("path", patch_routes)
def test_api_patch_missing_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _token_missing_request(client, "PATCH", path)


delete_routes = ["/api/v1/servers/localhost/zones/test-zone.example.com."]


@pytest.mark.parametrize("path", delete_routes)
def test_api_delete_wrong_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _wrong_token_request(client, "DELETE", path)


@pytest.mark.parametrize("path", delete_routes)
def test_api_delete_missing_token(path, fixture_patch_dummy_config, fixture_patch_pdns):
    _token_missing_request(client, "DELETE", path)


def _sha512(token: str) -> str:
    return hashlib.sha512(token.encode()).hexdigest()


class _FakePdnsResponse:
    """Minimal stand-in for an aiohttp.ClientResponse, as consumed by
    powerdns_api_proxy.pdns.handle_pdns_response."""

    def __init__(self, status_code: int, data):
        self.status = status_code
        self.url = "http://pdns.example/"
        self._data = data

    async def text(self):
        return json.dumps(self._data)


def _rrset_payload(zone_name: str, record_name: str) -> dict:
    return {
        "name": zone_name,
        "kind": "Native",
        "rrsets": [
            {
                "name": record_name,
                "type": "TXT",
                "ttl": 3600,
                "changetype": "REPLACE",
                "records": [{"content": '"test"', "disabled": False}],
            }
        ],
    }


def test_create_zone_with_disallowed_rrset_forbidden():
    """
    A token with admin rights on a zone but a restricted `records` list must
    not be able to smuggle unrestricted rrsets into the zone via the initial
    zone-creation payload (PowerDNS accepts an `rrsets` array on zone
    creation, bypassing the per-record write scope enforced on PATCH).
    """
    token = "restricted-token-for-zone-creation-test"
    zone = ProxyConfigZone(
        name="restricted.example.com.",
        admin=True,
        records=["allowed.restricted.example.com."],
    )
    environment = ProxyConfigEnvironment(
        name="Restricted",
        zones=[zone],
        token_sha512=_sha512(token),
    )
    restricted_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )
    payload = _rrset_payload(
        "restricted.example.com.", "notallowed.restricted.example.com."
    )
    post_mock = AsyncMock()

    with (
        patch("powerdns_api_proxy.config.load_config", return_value=restricted_config),
        patch("powerdns_api_proxy.proxy.config", restricted_config),
        patch("powerdns_api_proxy.proxy.pdns.post", post_mock),
    ):
        answer = client.post(
            "/api/v1/servers/localhost/zones",
            json=payload,
            headers={"X-API-Key": token},
        )
    assert answer.status_code == 403
    assert "notallowed.restricted.example.com." in answer.json()["error"]
    post_mock.assert_not_called()


def test_create_zone_with_allowed_rrset_succeeds():
    token = "restricted-token-for-zone-creation-test-2"
    zone = ProxyConfigZone(
        name="restricted2.example.com.",
        admin=True,
        records=["allowed.restricted2.example.com."],
    )
    environment = ProxyConfigEnvironment(
        name="Restricted2",
        zones=[zone],
        token_sha512=_sha512(token),
    )
    restricted_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )
    payload = _rrset_payload(
        "restricted2.example.com.", "allowed.restricted2.example.com."
    )
    fake_response = _FakePdnsResponse(201, payload)

    with (
        patch("powerdns_api_proxy.config.load_config", return_value=restricted_config),
        patch("powerdns_api_proxy.proxy.config", restricted_config),
        patch(
            "powerdns_api_proxy.proxy.pdns.post", AsyncMock(return_value=fake_response)
        ),
    ):
        answer = client.post(
            "/api/v1/servers/localhost/zones",
            json=payload,
            headers={"X-API-Key": token},
        )
    assert answer.status_code == 201


def test_create_zone_with_zonefile_forbidden_for_record_restricted_token():
    """
    PowerDNS also accepts a BIND style zonefile in the `zone` field on zone
    creation. Its contents cannot be validated against the record
    restrictions of the token, so it must be rejected for tokens that do not
    have write access to all records of the zone.
    """
    token = "restricted-token-for-zone-creation-test-4"
    zone = ProxyConfigZone(
        name="restricted4.example.com.",
        admin=True,
        records=["allowed.restricted4.example.com."],
    )
    environment = ProxyConfigEnvironment(
        name="Restricted4",
        zones=[zone],
        token_sha512=_sha512(token),
    )
    restricted_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )
    payload = {
        "name": "restricted4.example.com.",
        "kind": "Native",
        "zone": "evil.restricted4.example.com. 3600 IN A 192.0.2.1\n",
    }
    post_mock = AsyncMock()

    with (
        patch("powerdns_api_proxy.config.load_config", return_value=restricted_config),
        patch("powerdns_api_proxy.proxy.config", restricted_config),
        patch("powerdns_api_proxy.proxy.pdns.post", post_mock),
    ):
        answer = client.post(
            "/api/v1/servers/localhost/zones",
            json=payload,
            headers={"X-API-Key": token},
        )
    assert answer.status_code == 403
    post_mock.assert_not_called()


def test_create_zone_with_zonefile_allowed_for_unrestricted_token():
    """
    A token with write access to all records of the zone may still create the
    zone from a zonefile.
    """
    token = "restricted-token-for-zone-creation-test-5"
    zone = ProxyConfigZone(name="restricted5.example.com.", admin=True)
    assert zone.all_records
    environment = ProxyConfigEnvironment(
        name="Restricted5",
        zones=[zone],
        token_sha512=_sha512(token),
    )
    restricted_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )
    payload = {
        "name": "restricted5.example.com.",
        "kind": "Native",
        "zone": "www.restricted5.example.com. 3600 IN A 192.0.2.1\n",
    }
    fake_response = _FakePdnsResponse(201, payload)

    with (
        patch("powerdns_api_proxy.config.load_config", return_value=restricted_config),
        patch("powerdns_api_proxy.proxy.config", restricted_config),
        patch(
            "powerdns_api_proxy.proxy.pdns.post", AsyncMock(return_value=fake_response)
        ),
    ):
        answer = client.post(
            "/api/v1/servers/localhost/zones",
            json=payload,
            headers={"X-API-Key": token},
        )
    assert answer.status_code == 201


def test_create_zone_without_rrsets_succeeds():
    token = "restricted-token-for-zone-creation-test-3"
    zone = ProxyConfigZone(
        name="restricted3.example.com.",
        admin=True,
        records=["allowed.restricted3.example.com."],
    )
    environment = ProxyConfigEnvironment(
        name="Restricted3",
        zones=[zone],
        token_sha512=_sha512(token),
    )
    restricted_config = ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )
    payload = {"name": "restricted3.example.com.", "kind": "Native"}
    fake_response = _FakePdnsResponse(201, payload)

    with (
        patch("powerdns_api_proxy.config.load_config", return_value=restricted_config),
        patch("powerdns_api_proxy.proxy.config", restricted_config),
        patch(
            "powerdns_api_proxy.proxy.pdns.post", AsyncMock(return_value=fake_response)
        ),
    ):
        answer = client.post(
            "/api/v1/servers/localhost/zones",
            json=payload,
            headers={"X-API-Key": token},
        )
    assert answer.status_code == 201
