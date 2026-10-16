"""Fixtures for the end-to-end suite.

Spawns a real uvicorn proxy process and a fake PowerDNS upstream on
127.0.0.1 free ports; everything is hermetic and Docker-free.
"""

import hashlib
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import yaml

from tests.e2e.fake_pdns import FakePowerDNS

TOKENS = {
    "readonly": "e2e-readonly-token",
    "global": "e2e-global-token",
    "admin": "e2e-admin-token",
    "plain": "e2e-plain-token",
    "monitoring": "e2e-monitoring-token",
}


def _sha512(token: str) -> str:
    return hashlib.sha512(token.encode()).hexdigest()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _config(pdns_url: str) -> dict:
    return {
        "pdns_api_url": pdns_url,
        "pdns_api_token": "e2e-upstream-token",
        "environments": [
            {
                "name": "readonly",
                "token_sha512": _sha512(TOKENS["readonly"]),
                "zones": [{"name": "ro.example.com.", "read_only": True}],
            },
            {
                "name": "global",
                "token_sha512": _sha512(TOKENS["global"]),
                "global_read_only": True,
                "zones": [
                    {
                        "name": "writable.example.com.",
                        "records": ["www.writable.example.com."],
                    }
                ],
            },
            {
                "name": "admin",
                "token_sha512": _sha512(TOKENS["admin"]),
                "zones": [{"name": "managed.example.com.", "admin": True}],
            },
            {
                "name": "plain",
                "token_sha512": _sha512(TOKENS["plain"]),
                "zones": [
                    {
                        "name": "plain.example.com.",
                        "records": ["www.plain.example.com."],
                    }
                ],
            },
            {
                "name": "monitoring",
                "token_sha512": _sha512(TOKENS["monitoring"]),
                "metrics_proxy": True,
            },
        ],
    }


@pytest.fixture(scope="session")
def auth() -> dict[str, dict[str, str]]:
    return {name: {"X-API-Key": token} for name, token in TOKENS.items()}


@pytest.fixture(scope="session")
def tokens() -> dict[str, str]:
    return dict(TOKENS)


@pytest.fixture(scope="session")
def fake_pdns() -> Iterator[FakePowerDNS]:
    fake = FakePowerDNS(_free_port())
    fake.start()
    fake.wait_ready()
    yield fake
    fake.stop()


@pytest.fixture(scope="session")
def proxy_url(fake_pdns: FakePowerDNS, tmp_path_factory) -> Iterator[str]:
    port = _free_port()
    tmp_dir = tmp_path_factory.mktemp("e2e")
    config_path = tmp_dir / "config.yml"
    config_path.write_text(yaml.safe_dump(_config(fake_pdns.url)))
    log_path = tmp_dir / "proxy.log"

    env = {
        **os.environ,
        "PROXY_CONFIG_PATH": str(config_path),
        "LOG_FILE": "false",
        "LISTEN_HOST": "127.0.0.1",
        "LISTEN_PORT": str(port),
    }
    env.pop("SENTRY_DSN", None)

    url = f"http://127.0.0.1:{port}"
    with log_path.open("w") as log_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", "powerdns_api_proxy"],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_proxy(url, proc, log_path)
            yield url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _wait_for_proxy(url: str, proc: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"proxy exited with {proc.returncode}:\n{log_path.read_text()[-2000:]}"
            )
        try:
            if httpx.get(f"{url}/", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"proxy did not become ready:\n{log_path.read_text()[-2000:]}")


@pytest.fixture(scope="session")
def client(proxy_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=proxy_url, timeout=5) as client:
        yield client


@pytest.fixture(autouse=True)
def _reset_fake_pdns(fake_pdns: FakePowerDNS) -> Iterator[None]:
    fake_pdns.requests.clear()
    yield
