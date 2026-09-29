import uvicorn

from powerdns_api_proxy.__main__ import main


def _captured_uvicorn_kwargs(monkeypatch):
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main()
    return captured


def test_main_enables_proxy_headers_explicitly(monkeypatch):
    """The trust boundary must live in our code, not in a uvicorn default."""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)

    captured = _captured_uvicorn_kwargs(monkeypatch)

    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "127.0.0.1"


def test_main_reads_forwarded_allow_ips_from_env(monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.244.0.0/16")

    captured = _captured_uvicorn_kwargs(monkeypatch)

    assert captured["forwarded_allow_ips"] == "10.244.0.0/16"
