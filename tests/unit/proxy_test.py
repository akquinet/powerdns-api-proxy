import os
from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from powerdns_api_proxy.models import (
    NotAuthorizedException,
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
)
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
    "/api/v1/servers/localhost/configuration",
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
