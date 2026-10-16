import logging
from pathlib import Path

from powerdns_api_proxy.config import ConfigHolder

TOKEN_A_SHA512 = "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"  # noqa: E501
TOKEN_B_SHA512 = "1954a12ef0bf45b3a1797437509037f178af846d880115d57668a8aaa05732deedcbbd02bfa296b4f4e043b437b733fd6131933cfdc0fb50c4cf7f9f2bdaa836"  # noqa: E501


def _config_content(environment: str, token_sha512: str) -> str:
    return f"""
pdns_api_url: "https://test.example.com"
pdns_api_token: "secret-upstream-token"
environments:
  - name: "{environment}"
    token_sha512: "{token_sha512}"
    zones:
      - name: "example.com"
"""


def _holder(tmp_path: Path, monkeypatch, environment: str = "Test 1") -> ConfigHolder:
    config_path = tmp_path / "config.yml"
    config_path.write_text(_config_content(environment, TOKEN_A_SHA512))
    monkeypatch.setenv("PROXY_CONFIG_PATH", str(config_path))
    return ConfigHolder()


def test_get_loads_config_and_caches(tmp_path, monkeypatch):
    holder = _holder(tmp_path, monkeypatch)

    config = holder.get()
    assert [environment.name for environment in config.environments] == ["Test 1"]

    (tmp_path / "config.yml").write_text(_config_content("Changed", TOKEN_B_SHA512))
    assert holder.get() is config


def test_reload_swaps_config(tmp_path, monkeypatch):
    holder = _holder(tmp_path, monkeypatch)
    assert holder.reload() is True
    assert [environment.name for environment in holder.get().environments] == ["Test 1"]

    (tmp_path / "config.yml").write_text(_config_content("Test 2", TOKEN_B_SHA512))

    assert holder.reload() is True
    config = holder.get()
    assert [environment.name for environment in config.environments] == ["Test 2"]
    assert TOKEN_B_SHA512 in config.token_env_map


def test_reload_keeps_previous_config_on_invalid_yaml(tmp_path, monkeypatch, caplog):
    holder = _holder(tmp_path, monkeypatch)
    previous = holder.get()

    (tmp_path / "config.yml").write_text("environments: [")

    with caplog.at_level(logging.ERROR):
        assert holder.reload() is False

    assert holder.get() is previous
    assert "keeping the previous configuration" in caplog.text


def test_reload_keeps_previous_config_on_invalid_schema(tmp_path, monkeypatch, caplog):
    holder = _holder(tmp_path, monkeypatch)
    previous = holder.get()

    (tmp_path / "config.yml").write_text(_config_content("Broken", "tooshort"))

    with caplog.at_level(logging.ERROR):
        assert holder.reload() is False

    assert holder.get() is previous
    assert "keeping the previous configuration" in caplog.text


def test_reload_logs_environment_names_without_secrets(tmp_path, monkeypatch, caplog):
    holder = _holder(tmp_path, monkeypatch)

    (tmp_path / "config.yml").write_text(_config_content("Rotated", TOKEN_B_SHA512))

    with caplog.at_level(logging.INFO):
        assert holder.reload() is True

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "Rotated" in messages
    assert "secret-upstream-token" not in messages
    assert TOKEN_B_SHA512 not in messages
