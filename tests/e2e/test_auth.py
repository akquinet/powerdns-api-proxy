"""Authentication behavior over real HTTP."""

import httpx
import pytest

ROUTES = [
    ("GET", "/api"),
    ("GET", "/api/v1/servers/localhost/zones"),
    ("GET", "/info/allowed"),
    ("PUT", "/api/v1/servers/localhost/zones/plain.example.com./notify"),
    ("PATCH", "/api/v1/servers/localhost/zones/plain.example.com."),
    ("DELETE", "/api/v1/servers/localhost/zones/managed.example.com."),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_wrong_token_rejected(client: httpx.Client, method: str, path: str) -> None:
    response = client.request(method, path, headers={"X-API-Key": "wrong-token"})
    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized"


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_missing_token_rejected(client: httpx.Client, method: str, path: str) -> None:
    response = client.request(method, path)
    assert response.status_code == 422


def test_valid_token_accepted(
    client: httpx.Client, auth: dict[str, dict[str, str]]
) -> None:
    response = client.get("/api", headers=auth["plain"])
    assert response.status_code == 200
    assert response.json()[0]["version"] == 1
