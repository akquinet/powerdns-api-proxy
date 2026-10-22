import asyncio
import json
import os
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from powerdns_api_proxy.exceptions import (
    InvalidPathParameterException,
    NotAuthorizedException,
    ZoneReadOnlyException,
)
from powerdns_api_proxy.models import (
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
)
from powerdns_api_proxy.proxy import app, resolve_zone_entry

client = TestClient(app)


dummy_proxy_zone = ProxyConfigZone(name="test.example.com.")
dummy_proxy_environment_token = "lashflkashlfgkashglashglashgl"
dummy_proxy_environment_token_sha512 = "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
dummy_proxy_environment_token2 = "aslkghlskdhglkwhegklwhelghwleghwle"
dummy_proxy_environment_token2_sha512 = "1954a12ef0bf45b3a1797437509037f178af846d880115d57668a8aaa05732deedcbbd02bfa296b4f4e043b437b733fd6131933cfdc0fb50c4cf7f9f2bdaa836"

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


def test_health_liveness_without_token():
    answer = client.get("/health")
    assert answer.status_code == 200
    assert answer.json() == {"status": "ok"}


def test_health_pdns_missing_token():
    _token_missing_request(client, "GET", "/health/pdns")


def test_health_pdns_wrong_token():
    _wrong_token_request(client, "GET", "/health/pdns")


def test_health_pdns_valid_token(fixture_patch_dummy_config):
    pdns_response = MagicMock()
    pdns_response.status = 200
    with patch(
        "powerdns_api_proxy.proxy.pdns.get",
        new_callable=AsyncMock,
        return_value=pdns_response,
    ) as get:
        answer = client.get(
            "/health/pdns", headers={"X-API-Key": dummy_proxy_environment_token}
        )
    assert answer.status_code == 200
    get.assert_awaited_once()


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
    assert answer.status_code == 401
    assert answer.json()["error"] == NotAuthorizedException().detail


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


def _config(*zones, **env_kwargs) -> ProxyConfig:
    environment = ProxyConfigEnvironment(
        name="Test Env",
        zones=list(zones),
        token_sha512=dummy_proxy_environment_token_sha512,
        **env_kwargs,
    )
    return ProxyConfig(
        pdns_api_token="blaaa",
        pdns_api_url="bluub",
        environments=[environment],
    )


def _writable_global_read_only_config() -> ProxyConfig:
    return _config(
        ProxyConfigZone(
            name="writable.example.com.", records=["writable.example.com."]
        ),
        global_read_only=True,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/servers/localhost/zones/test.example.com./notify",
        "/api/v1/servers/localhost/zones/test.example.com./rectify",
    ],
)
def test_notify_rectify_rejected_for_read_only_zone(path, fixture_patch_pdns):
    config = _config(ProxyConfigZone(name="test.example.com.", read_only=True))
    with (
        patch("powerdns_api_proxy.proxy.config", config),
        patch("powerdns_api_proxy.config.load_config", return_value=config),
    ):
        answer = client.put(path, headers={"X-API-Key": dummy_proxy_environment_token})
    assert answer.status_code == 403
    assert answer.json()["error"] == ZoneReadOnlyException().detail


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/servers/localhost/zones/writable.example.com./notify",
        "/api/v1/servers/localhost/zones/writable.example.com./rectify",
    ],
)
def test_notify_rectify_allowed_for_listed_zone_in_global_read_only(path):
    pdns_response = MagicMock()
    pdns_response.raise_for_error.return_value = 204
    config = _writable_global_read_only_config()
    with (
        patch("powerdns_api_proxy.proxy.config", config),
        patch("powerdns_api_proxy.config.load_config", return_value=config),
        patch("powerdns_api_proxy.proxy.pdns.put", new_callable=AsyncMock) as put,
        patch(
            "powerdns_api_proxy.proxy.handle_pdns_response",
            new_callable=AsyncMock,
            return_value=pdns_response,
        ),
    ):
        answer = client.put(path, headers={"X-API-Key": dummy_proxy_environment_token})
    assert answer.status_code == 204
    put.assert_awaited_once()


def test_patch_allowed_for_listed_zone_in_global_read_only():
    pdns_response = MagicMock()
    pdns_response.raise_for_error.return_value = 204
    payload = {
        "rrsets": [
            {
                "name": "writable.example.com.",
                "type": "TXT",
                "changetype": "REPLACE",
                "ttl": 3600,
                "records": [{"content": "test", "disabled": False}],
                "comments": [],
            }
        ]
    }
    config = _writable_global_read_only_config()
    with (
        patch("powerdns_api_proxy.proxy.config", config),
        patch("powerdns_api_proxy.config.load_config", return_value=config),
        patch(
            "powerdns_api_proxy.proxy.pdns.patch", new_callable=AsyncMock
        ) as patch_call,
        patch(
            "powerdns_api_proxy.proxy.handle_pdns_response",
            new_callable=AsyncMock,
            return_value=pdns_response,
        ),
    ):
        answer = client.patch(
            "/api/v1/servers/localhost/zones/writable.example.com.",
            headers={"X-API-Key": dummy_proxy_environment_token},
            json=payload,
        )
    assert answer.status_code == 204
    patch_call.assert_awaited_once_with(
        "/api/v1/servers/localhost/zones/writable.example.com.",
        payload=payload,
    )


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


class _FakeUpstreamResponse:
    def __init__(self, data, status: int = 200):
        self._data = data
        self.status = status
        self.url = "https://pdns.example.com/"

    async def text(self) -> str:
        return json.dumps(self._data)


def _regex_zone(**zone_kwargs) -> ProxyConfigZone:
    return ProxyConfigZone(name=".*\\.example.com", regex=True, **zone_kwargs)


def _get_zone(zone: str, upstream: AsyncMock):
    with patch("powerdns_api_proxy.proxy.pdns", upstream):
        return client.get(
            f"/api/v1/servers/localhost/zones/{zone}",
            headers={"X-API-Key": dummy_proxy_environment_token},
        )


def _get_cryptokeys(zone: str, token: str, upstream: AsyncMock):
    with patch("powerdns_api_proxy.proxy.pdns", upstream):
        return client.get(
            f"/api/v1/servers/localhost/zones/{zone}/cryptokeys",
            headers={"X-API-Key": token},
        )


def _post_zone(config_obj: ProxyConfig, upstream: AsyncMock):
    create_response = MagicMock()
    create_response.data = {}
    create_response.raise_for_error.return_value = 201
    with (
        patch("powerdns_api_proxy.proxy.config", config_obj),
        patch("powerdns_api_proxy.proxy.pdns", upstream),
        patch(
            "powerdns_api_proxy.proxy.handle_pdns_response",
            new_callable=AsyncMock,
            return_value=create_response,
        ),
    ):
        return client.post(
            "/api/v1/servers/localhost/zones",
            headers={"X-API-Key": dummy_proxy_environment_token},
            json={"name": "new.example.com.", "kind": "Native"},
        )


def _zone_allowed(zone: str, config_obj: ProxyConfig, upstream: AsyncMock):
    with (
        patch("powerdns_api_proxy.proxy.config", config_obj),
        patch("powerdns_api_proxy.proxy.pdns", upstream),
    ):
        return client.get(
            f"/info/zone-allowed?zone={zone}",
            headers={"X-API-Key": dummy_proxy_environment_token},
        )


@pytest.mark.parametrize(
    "zone",
    [
        _regex_zone(kind="Master"),
        ProxyConfigZone(kind="Master"),
    ],
    ids=["named", "attribute-only"],
)
def test_zone_attr_filter_rejects_mismatching_zone(zone):
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse({"kind": "Slave"}))
    with patch("powerdns_api_proxy.proxy.config", _config(zone)):
        answer = _get_zone("slave.example.com.", upstream)
    assert answer.status_code == 403
    assert upstream.get.call_count == 1
    assert upstream.get.call_args.kwargs["params"] == {"rrsets": "false"}


@pytest.mark.parametrize(
    "zone",
    [
        _regex_zone(kind="Master"),
        ProxyConfigZone(kind="Master"),
    ],
    ids=["named", "attribute-only"],
)
def test_zone_attr_filter_allows_matching_zone(zone):
    zone_data = {"name": "master.example.com.", "kind": "Master"}
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        side_effect=[
            _FakeUpstreamResponse(zone_data),
            _FakeUpstreamResponse(zone_data),
        ]
    )
    with patch("powerdns_api_proxy.proxy.config", _config(zone)):
        answer = _get_zone("master.example.com.", upstream)
    assert answer.status_code == 200
    assert upstream.get.call_count == 2


def test_zone_attr_filter_skipped_without_filters():
    zone_data = {"name": "slave.example.com.", "kind": "Slave"}
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse(zone_data))
    with patch("powerdns_api_proxy.proxy.config", _config(_regex_zone())):
        answer = _get_zone("slave.example.com.", upstream)
    assert answer.status_code == 200
    assert upstream.get.call_count == 1


def test_zone_attr_filter_rejects_mismatching_delete():
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse({"kind": "Slave"}))
    with (
        patch(
            "powerdns_api_proxy.proxy.config",
            _config(_regex_zone(kind="Master", admin=True)),
        ),
        patch("powerdns_api_proxy.proxy.pdns", upstream),
    ):
        answer = client.delete(
            "/api/v1/servers/localhost/zones/slave.example.com.",
            headers={"X-API-Key": dummy_proxy_environment_token},
        )
    assert answer.status_code == 403
    upstream.delete.assert_not_awaited()


def test_cryptokeys_attr_filter_rejects_mismatching_zone():
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse({"kind": "Slave"}))
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(_regex_zone(kind="Master", cryptokeys=True)),
    ):
        answer = _get_cryptokeys(
            "slave.example.com.", dummy_proxy_environment_token, upstream
        )
    assert answer.status_code == 403
    assert upstream.get.call_count == 1


def test_cryptokeys_attr_filter_allows_matching_zone():
    zone_data = {"name": "master.example.com.", "kind": "Master"}
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        side_effect=[
            _FakeUpstreamResponse(zone_data),
            _FakeUpstreamResponse([{"id": 1}]),
        ]
    )
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(_regex_zone(kind="Master", cryptokeys=True)),
    ):
        answer = _get_cryptokeys(
            "master.example.com.", dummy_proxy_environment_token, upstream
        )
    assert answer.status_code == 200
    assert upstream.get.call_count == 2


def test_cryptokeys_unlisted_zone_allowed_in_global_read_only():
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse([{"id": 1}]))
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(global_read_only=True, global_cryptokeys=True),
    ):
        answer = _get_cryptokeys(
            "unlisted.example.com.", dummy_proxy_environment_token, upstream
        )
    assert answer.status_code == 200
    assert upstream.get.call_count == 1


def test_attr_entry_does_not_fetch_for_plain_name_zone():
    zone_data = {"name": "plain.example.com.", "kind": "Slave"}
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse(zone_data))
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(
            ProxyConfigZone(name="plain.example.com."), ProxyConfigZone(kind="Master")
        ),
    ):
        answer = _get_zone("plain.example.com.", upstream)
    assert answer.status_code == 200
    assert upstream.get.call_count == 1


def test_zone_allowed_by_second_attribute_only_entry():
    zone_data = {"name": "slave.example.com.", "kind": "Slave", "account": "public"}
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        side_effect=[
            _FakeUpstreamResponse(zone_data),
            _FakeUpstreamResponse(zone_data),
        ]
    )
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(ProxyConfigZone(kind="Master"), ProxyConfigZone(account="public")),
    ):
        answer = _get_zone("slave.example.com.", upstream)
    assert answer.status_code == 200
    assert upstream.get.call_count == 2


def test_matching_attribute_only_entry_supplies_permissions():
    zone_data = {"name": "slave.example.com.", "kind": "Slave", "account": "public"}
    fetch_response = MagicMock()
    fetch_response.data = zone_data
    fetch_response.raise_for_error.return_value = 200
    delete_response = MagicMock()
    delete_response.data = {}
    delete_response.raise_for_error.return_value = 204
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse(zone_data))
    with (
        patch(
            "powerdns_api_proxy.proxy.config",
            _config(
                ProxyConfigZone(kind="Master"),
                ProxyConfigZone(account="public", admin=True),
            ),
        ),
        patch("powerdns_api_proxy.proxy.pdns", upstream),
        patch(
            "powerdns_api_proxy.proxy.handle_pdns_response",
            new_callable=AsyncMock,
            side_effect=[fetch_response, delete_response],
        ),
    ):
        answer = client.delete(
            "/api/v1/servers/localhost/zones/slave.example.com.",
            headers={"X-API-Key": dummy_proxy_environment_token},
        )
    assert answer.status_code == 204
    assert upstream.get.call_count == 1
    upstream.delete.assert_awaited_once()


def test_named_attribute_mismatch_does_not_fall_back_to_wildcard():
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        return_value=_FakeUpstreamResponse(
            {"name": "slave.example.com.", "kind": "Slave", "account": "public"}
        )
    )
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(_regex_zone(kind="Master"), ProxyConfigZone(account="public")),
    ):
        answer = _get_zone("slave.example.com.", upstream)
    assert answer.status_code == 403


@pytest.mark.parametrize(
    "zone_name",
    ["unlisted.example.com.", "slave.example.com."],
    ids=["unlisted", "attr-mismatch"],
)
def test_get_allowed_in_global_read_only(zone_name):
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        return_value=_FakeUpstreamResponse({"name": zone_name, "kind": "Native"})
    )
    with patch(
        "powerdns_api_proxy.proxy.config",
        _config(_regex_zone(kind="Master"), global_read_only=True),
    ):
        answer = _get_zone(zone_name, upstream)
    assert answer.status_code == 200
    assert upstream.get.call_count == 1


@pytest.mark.parametrize(
    "zone_name",
    ["unlisted.example.com.", "slave.example.com."],
    ids=["unlisted", "attr-mismatch"],
)
def test_patch_rejected_in_global_read_only(zone_name):
    upstream = AsyncMock()
    upstream.get = AsyncMock(return_value=_FakeUpstreamResponse({"kind": "Slave"}))
    with (
        patch(
            "powerdns_api_proxy.proxy.config",
            _config(_regex_zone(kind="Master"), global_read_only=True),
        ),
        patch("powerdns_api_proxy.proxy.pdns", upstream),
    ):
        answer = client.patch(
            f"/api/v1/servers/localhost/zones/{zone_name}",
            headers={"X-API-Key": dummy_proxy_environment_token},
            json={"rrsets": []},
        )
    assert answer.status_code == 403
    upstream.patch.assert_not_awaited()


@pytest.mark.parametrize(
    ("zones", "expected"),
    [
        (ProxyConfigZone(kind="Master", admin=True), 403),
        (ProxyConfigZone(name="new.example.com.", admin=True), 201),
        (ProxyConfigZone(name="new.example.com.", kind="Master", admin=True), 201),
    ],
    ids=["attribute-only", "named", "named-with-filter"],
)
def test_create_zone(zones, expected):
    upstream = AsyncMock()
    answer = _post_zone(_config(zones), upstream)
    assert answer.status_code == expected
    if expected == 403:
        upstream.post.assert_not_awaited()
    else:
        upstream.post.assert_awaited_once()


@pytest.mark.parametrize(
    (
        "zones",
        "global_read_only",
        "zone",
        "upstream_status",
        "upstream_data",
        "expected_allowed",
        "expected_calls",
        "expected_config",
    ),
    [
        pytest.param(
            [ProxyConfigZone(name="plain.example.com.")],
            False,
            "plain.example.com.",
            200,
            {},
            True,
            0,
            {"name": "plain.example.com."},
            id="named-no-filter",
        ),
        pytest.param(
            [ProxyConfigZone(name="example.com.", subzones=True)],
            False,
            "sub.example.com.",
            200,
            {},
            True,
            0,
            {"name": "example.com."},
            id="subzone",
        ),
        pytest.param(
            [], False, "other.example.com.", 200, {}, False, 0, None, id="unconfigured"
        ),
        pytest.param(
            [ProxyConfigZone(kind="Master")],
            False,
            "master.example.com.",
            200,
            {"kind": "Master"},
            True,
            1,
            {"kind": "Master"},
            id="attr-match",
        ),
        pytest.param(
            [ProxyConfigZone(kind="Master")],
            False,
            "slave.example.com.",
            200,
            {"kind": "Slave"},
            False,
            1,
            None,
            id="attr-mismatch",
        ),
        pytest.param(
            [_regex_zone(kind="Master")],
            False,
            "slave.example.com.",
            200,
            {"kind": "Slave"},
            False,
            1,
            None,
            id="named-mismatch",
        ),
        pytest.param(
            [ProxyConfigZone(kind="Master")],
            False,
            "gone.example.com.",
            404,
            {"error": "Could not find domain"},
            False,
            1,
            None,
            id="upstream-404",
        ),
        pytest.param(
            [],
            True,
            "unlisted.example.com.",
            200,
            {},
            True,
            0,
            None,
            id="global-read-only",
        ),
    ],
)
def test_zone_allowed(
    zones,
    global_read_only,
    zone,
    upstream_status,
    upstream_data,
    expected_allowed,
    expected_calls,
    expected_config,
):
    upstream = AsyncMock()
    upstream.get = AsyncMock(
        return_value=_FakeUpstreamResponse(upstream_data, status=upstream_status)
    )
    answer = _zone_allowed(
        zone, _config(*zones, global_read_only=global_read_only), upstream
    )
    assert answer.status_code == 200
    data = answer.json()
    assert data["allowed"] is expected_allowed
    assert upstream.get.call_count == expected_calls
    if expected_config is None:
        assert data["config"] is None
    else:
        assert data["config"] is not None
        for key, value in expected_config.items():
            assert data["config"][key] == value


@pytest.mark.parametrize(
    "zone", ["", ".", "..", "../config", "../../../servers", "foo/bar"]
)
def test_zone_allowed_rejects_unsafe_zone_param(zone):
    upstream = AsyncMock()
    answer = _zone_allowed(zone, _config(ProxyConfigZone(kind="Master")), upstream)
    assert answer.status_code == 400
    assert answer.json() == {"error": "Invalid value for path parameter zone_id"}
    upstream.get.assert_not_awaited()


def test_resolve_zone_entry_rejects_unsafe_zone_id():
    environment = _config(ProxyConfigZone(kind="Master")).environments[0]
    with pytest.raises(InvalidPathParameterException):
        asyncio.run(resolve_zone_entry(environment, "localhost", "../config"))
