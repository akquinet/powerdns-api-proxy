from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from powerdns_api_proxy.middleware import RateLimitMiddleware
from powerdns_api_proxy.models import (
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
)
from powerdns_api_proxy.proxy import app as proxy_app
from powerdns_api_proxy.rate_limit import AuthFailureRateLimiter, RateLimitConfig

# Same token and hash as tests/unit/proxy_test.py, kept local so the modules stay
# independent.
TOKEN = "lashflkashlfgkashglashglashgl"
TOKEN_SHA512 = (
    "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf"
    "1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
)

DUMMY_CONFIG = ProxyConfig(
    pdns_api_token="blaaa",
    pdns_api_url="bluub",
    environments=[
        ProxyConfigEnvironment(
            name="Test",
            zones=[ProxyConfigZone(name="test.example.com.")],
            token_sha512=TOKEN_SHA512,
        )
    ],
)


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_limiter(
    auth_failures: int = 3,
    window_seconds: int = 60,
    enabled: bool = True,
) -> tuple[AuthFailureRateLimiter, FakeClock]:
    clock = FakeClock()
    config = RateLimitConfig(
        enabled=enabled,
        auth_failures=auth_failures,
        window_seconds=window_seconds,
    )
    return AuthFailureRateLimiter(config, clock=clock), clock


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_config_defaults():
    config = RateLimitConfig.from_env({})
    assert config == RateLimitConfig(enabled=True, auth_failures=20, window_seconds=60)


def test_config_env_overrides():
    config = RateLimitConfig.from_env(
        {
            "RATE_LIMIT_ENABLED": "no",
            "RATE_LIMIT_AUTH_FAILURES": "5",
            "RATE_LIMIT_WINDOW_SECONDS": "10",
        }
    )
    assert config == RateLimitConfig(enabled=False, auth_failures=5, window_seconds=10)


def test_config_empty_strings_use_defaults():
    config = RateLimitConfig.from_env(
        {
            "RATE_LIMIT_ENABLED": "",
            "RATE_LIMIT_AUTH_FAILURES": "",
            "RATE_LIMIT_WINDOW_SECONDS": "",
        }
    )
    assert config == RateLimitConfig()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_config_boolean_values(raw, expected):
    config = RateLimitConfig.from_env({"RATE_LIMIT_ENABLED": raw})
    assert config.enabled is expected


def test_config_invalid_boolean_raises():
    with pytest.raises(ValueError, match="RATE_LIMIT_ENABLED"):
        RateLimitConfig.from_env({"RATE_LIMIT_ENABLED": "maybe"})


@pytest.mark.parametrize(
    "name", ["RATE_LIMIT_AUTH_FAILURES", "RATE_LIMIT_WINDOW_SECONDS"]
)
@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", " "])
def test_config_invalid_integers_raise(name, value):
    with pytest.raises(ValueError, match=name):
        RateLimitConfig.from_env({name: value})


# ---------------------------------------------------------------------------
# Limiter
# ---------------------------------------------------------------------------


def test_first_failures_allowed_then_blocked():
    limiter, _ = make_limiter(auth_failures=3)

    for _ in range(3):
        assert limiter.retry_after("ip") is None
        limiter.record_failure("ip")

    assert limiter.retry_after("ip") == 60


def test_retry_after_reflects_elapsed_time():
    limiter, clock = make_limiter(auth_failures=1, window_seconds=60)
    limiter.record_failure("ip")

    clock.advance(25.5)
    assert limiter.retry_after("ip") == 35


def test_retry_after_never_below_one_second():
    limiter, clock = make_limiter(auth_failures=1, window_seconds=60)
    limiter.record_failure("ip")

    clock.advance(59.5)
    assert limiter.retry_after("ip") == 1


def test_expired_window_allows_again():
    limiter, clock = make_limiter(auth_failures=2, window_seconds=60)
    limiter.record_failure("ip")
    limiter.record_failure("ip")
    assert limiter.retry_after("ip") is not None

    clock.advance(60)
    assert limiter.retry_after("ip") is None

    limiter.record_failure("ip")
    assert limiter.retry_after("ip") is None


def test_record_failure_restarts_expired_window():
    limiter, clock = make_limiter(auth_failures=5, window_seconds=60)
    limiter.record_failure("ip")
    clock.advance(61)
    limiter.record_failure("ip")

    window = limiter._windows["ip"]
    assert window.failures == 1
    assert window.started == clock.now


def test_success_clears_failures():
    limiter, _ = make_limiter(auth_failures=2)
    limiter.record_failure("ip")
    limiter.record_failure("ip")
    assert limiter.retry_after("ip") is not None

    limiter.record_success("ip")
    assert limiter.retry_after("ip") is None


def test_keys_are_isolated():
    limiter, _ = make_limiter(auth_failures=1)
    limiter.record_failure("ip-a")
    assert limiter.retry_after("ip-a") is not None
    assert limiter.retry_after("ip-b") is None


def test_disabled_limiter_is_a_no_op():
    limiter, _ = make_limiter(auth_failures=1, enabled=False)

    for _ in range(100):
        limiter.record_failure("ip")

    assert limiter.retry_after("ip") is None
    assert limiter._windows == {}
    limiter.record_success("ip")


def test_expired_entries_are_cleaned_up():
    limiter, clock = make_limiter(auth_failures=2)
    for index in range(5):
        limiter.record_failure(f"ip-{index}")
    assert len(limiter._windows) == 5

    clock.advance(60)
    limiter.record_failure("new")
    assert set(limiter._windows) == {"new"}


# ---------------------------------------------------------------------------
# Middleware behavior with a minimal app
# ---------------------------------------------------------------------------


def make_protected_app(counter: dict[str, int]) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/servers")
    async def protected():
        counter["calls"] += 1
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return app


def test_blocked_request_returns_429_without_calling_downstream():
    limiter, _ = make_limiter(auth_failures=1)
    counter = {"calls": 0}
    client = TestClient(RateLimitMiddleware(make_protected_app(counter), limiter))

    limiter.record_failure("testclient")
    response = client.get("/api/v1/servers", headers={"X-API-Key": "wrong"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"error": "Too many failed authentication attempts"}
    assert counter["calls"] == 0


def test_wrong_token_consumes_budget():
    limiter, _ = make_limiter(auth_failures=1)
    client = TestClient(RateLimitMiddleware(make_protected_app({"calls": 0}), limiter))

    response = client.get("/api/v1/servers", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    assert limiter.retry_after("testclient") == 60


def test_missing_token_does_not_consume_budget():
    limiter, _ = make_limiter(auth_failures=1)
    client = TestClient(RateLimitMiddleware(make_protected_app({"calls": 0}), limiter))

    response = client.get("/api/v1/servers")

    assert response.status_code == 401
    assert limiter.retry_after("testclient") is None


def test_forwarded_addresses_get_independent_buckets():
    limiter, _ = make_limiter(auth_failures=1)
    counter = {"calls": 0}
    app = ProxyHeadersMiddleware(
        RateLimitMiddleware(make_protected_app(counter), limiter),
        trusted_hosts="testclient",
    )
    client = TestClient(app)

    first = client.get(
        "/api/v1/servers",
        headers={"X-API-Key": "wrong", "X-Forwarded-For": "203.0.113.1"},
    )
    assert first.status_code == 401

    blocked = client.get(
        "/api/v1/servers",
        headers={"X-API-Key": "wrong", "X-Forwarded-For": "203.0.113.1"},
    )
    assert blocked.status_code == 429

    other = client.get(
        "/api/v1/servers",
        headers={"X-API-Key": "wrong", "X-Forwarded-For": "203.0.113.2"},
    )
    assert other.status_code == 401


# ---------------------------------------------------------------------------
# Integration with the real app
# ---------------------------------------------------------------------------


def make_real_client(limiter: AuthFailureRateLimiter) -> TestClient:
    return TestClient(RateLimitMiddleware(proxy_app, limiter))


def test_real_app_blocks_after_limit():
    limiter, _ = make_limiter(auth_failures=2)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        blocked = client.get("/api/v1/servers", headers={"X-API-Key": "wrong"})

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_successful_authentication_resets_counter():
    limiter, _ = make_limiter(auth_failures=2)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert client.get("/api", headers={"X-API-Key": TOKEN}).status_code == 200

        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 429
        )


def test_public_endpoint_does_not_reset_counter():
    limiter, _ = make_limiter(auth_failures=2)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert client.get("/health").status_code == 200
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 429
        )


def test_blocked_ip_also_blocks_valid_token():
    limiter, _ = make_limiter(auth_failures=1)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        response = client.get("/api", headers={"X-API-Key": TOKEN})

    assert response.status_code == 429


def test_blocked_request_writes_audit_log(caplog):
    limiter, _ = make_limiter(auth_failures=1)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        client.get("/api/v1/servers/localhost/zones", headers={"X-API-Key": "wrong"})
        client.get("/api/v1/servers/localhost/zones", headers={"X-API-Key": "wrong"})

    blocked = [
        record.audit
        for record in caplog.records
        if hasattr(record, "audit")
        and record.audit.get("environment") == "RATE_LIMITED"
    ]

    assert len(blocked) == 1
    assert blocked[0]["status_code"] == 429
    assert blocked[0]["path"] == "/zones"
    assert blocked[0]["method"] == "GET"


def test_metrics_count_failures_and_blocks():
    failures_before = REGISTRY.get_sample_value("auth_failures_total") or 0.0
    blocked_before = REGISTRY.get_sample_value("auth_rate_limited_total") or 0.0

    limiter, _ = make_limiter(auth_failures=1)
    client = make_real_client(limiter)

    with patch("powerdns_api_proxy.config.load_config", return_value=DUMMY_CONFIG):
        assert (
            client.get("/api/v1/servers", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert client.get("/api", headers={"X-API-Key": TOKEN}).status_code == 429

    failures_after = REGISTRY.get_sample_value("auth_failures_total") or 0.0
    blocked_after = REGISTRY.get_sample_value("auth_rate_limited_total") or 0.0

    assert failures_after - failures_before == 1
    assert blocked_after - blocked_before == 1
