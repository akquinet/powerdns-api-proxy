"""Info, health, and metrics endpoints over real HTTP."""

import httpx

from tests.e2e.fake_pdns import FakePowerDNS


def test_info_allowed_returns_configured_zones(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get("/info/allowed", headers=auth["plain"])
    assert response.status_code == 200
    assert [zone["name"] for zone in response.json()["zones"]] == ["plain.example.com."]


def test_health_checks_upstream_pdns(
    client: httpx.Client, fake_pdns: FakePowerDNS
) -> None:
    response = client.get("/health/pdns")
    assert response.status_code == 200
    assert response.json()["details"] == "Upstream PowerDNS API seems to work :)"
    assert fake_pdns.received("GET", "/api/v1/servers")


def test_metrics_rejected_without_credentials(client: httpx.Client) -> None:
    response = client.get("/metrics")
    assert response.status_code == 401


def test_metrics_allowed_for_metrics_proxy_environment(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    response = client.get("/metrics", auth=("monitoring", tokens["monitoring"]))
    assert response.status_code == 200


def test_metrics_rejected_for_environment_without_metrics_proxy(
    client: httpx.Client, tokens: dict[str, str]
) -> None:
    response = client.get("/metrics", auth=("plain", tokens["plain"]))
    assert response.status_code == 403
