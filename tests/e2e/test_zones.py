"""Zone and record permission matrix over real HTTP."""

import httpx
import pytest

from tests.e2e.fake_pdns import FakePowerDNS


def _rrset(name: str) -> dict:
    return {
        "name": name,
        "type": "TXT",
        "changetype": "REPLACE",
        "ttl": 3600,
        "records": [{"content": "e2e", "disabled": False}],
        "comments": [],
    }


def test_zone_listing_filtered_for_plain_environment(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get("/api/v1/servers/localhost/zones", headers=auth["plain"])
    assert response.status_code == 200
    assert [zone["name"] for zone in response.json()] == ["plain.example.com."]


def test_zone_listing_returns_everything_for_global_environment(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get("/api/v1/servers/localhost/zones", headers=auth["global"])
    assert response.status_code == 200
    names = {zone["name"] for zone in response.json()}
    assert {"other.example.com.", "plain.example.com.", "ro.example.com."} <= names


def test_get_zone_happy_path(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get(
        "/api/v1/servers/localhost/zones/plain.example.com.", headers=auth["plain"]
    )
    assert response.status_code == 200
    assert response.json()["name"] == "plain.example.com."


def test_get_zone_not_allowed(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get(
        "/api/v1/servers/localhost/zones/other.example.com.", headers=auth["plain"]
    )
    assert response.status_code == 403
    assert response.json()["error"] == "Zone not allowed"


def test_get_zone_passes_through_404(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get(
        "/api/v1/servers/localhost/zones/unknown.example.com.", headers=auth["global"]
    )
    assert response.status_code == 404
    assert response.json()["error"] == "Not Found"


def test_patch_rrset_happy_path(
    client: httpx.Client,
    auth: dict[str, dict[str, str]],
    fake_pdns: FakePowerDNS,
) -> None:
    response = client.patch(
        "/api/v1/servers/localhost/zones/writable.example.com.",
        headers=auth["global"],
        json={"rrsets": [_rrset("www.writable.example.com.")]},
    )
    assert response.status_code == 204
    assert fake_pdns.received(
        "PATCH", "/api/v1/servers/localhost/zones/writable.example.com."
    )


def test_patch_rrset_rejected_for_read_only_zone(
    client: httpx.Client,
    auth: dict[str, dict[str, str]],
    fake_pdns: FakePowerDNS,
) -> None:
    response = client.patch(
        "/api/v1/servers/localhost/zones/ro.example.com.",
        headers=auth["readonly"],
        json={"rrsets": [_rrset("ro.example.com.")]},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "RRSET update not allowed with read only token"
    assert not fake_pdns.received(
        "PATCH", "/api/v1/servers/localhost/zones/ro.example.com."
    )


def test_patch_rrset_rejected_outside_record_allowlist(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.patch(
        "/api/v1/servers/localhost/zones/writable.example.com.",
        headers=auth["global"],
        json={"rrsets": [_rrset("other.writable.example.com.")]},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "RRSET other.writable.example.com. not allowed"


@pytest.mark.parametrize("action", ["notify", "rectify"])
def test_notify_rectify_allowed_for_writable_zone(
    client: httpx.Client,
    auth: dict[str, dict[str, str]],
    fake_pdns: FakePowerDNS,
    action: str,
) -> None:
    response = client.put(
        f"/api/v1/servers/localhost/zones/writable.example.com./{action}",
        headers=auth["global"],
    )
    assert response.status_code == 204
    assert fake_pdns.received(
        "PUT", f"/api/v1/servers/localhost/zones/writable.example.com./{action}"
    )


@pytest.mark.parametrize("action", ["notify", "rectify"])
def test_notify_rectify_rejected_for_read_only_zone(
    client: httpx.Client,
    auth: dict[str, dict[str, str]],
    fake_pdns: FakePowerDNS,
    action: str,
) -> None:
    response = client.put(
        f"/api/v1/servers/localhost/zones/ro.example.com./{action}",
        headers=auth["readonly"],
    )
    assert response.status_code == 403
    assert response.json()["error"] == "Zone is read only"
    assert not fake_pdns.received(
        "PUT", f"/api/v1/servers/localhost/zones/ro.example.com./{action}"
    )


def test_delete_zone_allowed_for_admin(
    client: httpx.Client,
    auth: dict[str, dict[str, str]],
    fake_pdns: FakePowerDNS,
) -> None:
    response = client.delete(
        "/api/v1/servers/localhost/zones/managed.example.com.", headers=auth["admin"]
    )
    assert response.status_code == 204
    assert fake_pdns.received(
        "DELETE", "/api/v1/servers/localhost/zones/managed.example.com."
    )


def test_delete_zone_rejected_for_non_admin(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.delete(
        "/api/v1/servers/localhost/zones/plain.example.com.", headers=auth["admin"]
    )
    assert response.status_code == 403
    assert response.json()["error"] == "Zone not allowed"
