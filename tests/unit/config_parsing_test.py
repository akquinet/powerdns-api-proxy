import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from powerdns_api_proxy.config import load_config

TOKEN = (
    "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf"
    "1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
)

CONFIG_PREFIX = """
pdns_api_url: "https://test.example.com"
pdns_api_token: "testtoken123"
"""

ENV_PREFIX = f"""
environments:
  - name: "Test"
    token_sha512: "{TOKEN}"
"""


def _load(tail: str):
    """Loads a config assembled from the shared YAML prefix plus `tail`."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write(CONFIG_PREFIX + tail)
        f.flush()
        return load_config(Path(f.name))


def test_index_html_from_yaml_single_line():
    config = _load(
        'index_html: "<html><body><h1>PowerDNS API Proxy</h1></body></html>"\n'
        + ENV_PREFIX
        + '    zones:\n      - name: "example.com"\n'
    )
    assert config.index_html == "<html><body><h1>PowerDNS API Proxy</h1></body></html>"
    assert config.index_enabled is True


def test_index_html_from_yaml_multiline():
    config = _load(
        """index_html: |
  <html>
    <body>
      <h1>Custom Page</h1>
    </body>
  </html>
"""
        + ENV_PREFIX
        + '    zones:\n      - name: "example.com"\n'
    )
    assert "<h1>Custom Page</h1>" in config.index_html
    assert config.index_enabled is True


def test_index_disabled_from_yaml():
    config = _load(
        "index_enabled: false\n"
        + ENV_PREFIX
        + '    zones:\n      - name: "example.com"\n'
    )
    assert config.index_enabled is False


@pytest.mark.parametrize(
    "zone",
    [
        'name: "example.com"\n        read_only: true\n        admin: true\n',
        'name: "example.com"\n        read_only: true\n        cryptokeys: true\n',
    ],
    ids=["admin", "cryptokeys"],
)
def test_read_only_zone_with_write_flag_rejected_from_yaml(zone):
    with pytest.raises(ValueError, match="read_only"):
        _load(ENV_PREFIX + "    zones:\n      - " + zone)


def test_admin_zone_with_global_read_only_accepted_from_yaml():
    config = _load(
        ENV_PREFIX
        + '    global_read_only: true\n    zones:\n      - name: "example.com"\n        admin: true\n'
    )
    assert config.environments[0].global_read_only is True
    assert config.environments[0].zones[0].admin is True


def test_zone_attributes_from_yaml():
    config = _load(
        ENV_PREFIX
        + """    zones:
      - name: "example.com"
        kind: "Master"
        account: "public"
        catalog: "default-catalog.invalid"
      - name: "other.example.com"
"""
    )
    zones = config.environments[0].zones
    assert zones[0].kind == "Master"
    assert zones[0].account == "public"
    assert zones[0].catalog == "default-catalog.invalid"
    assert zones[1].kind == ""
    assert zones[1].account == ""
    assert zones[1].catalog == ""


def test_attribute_only_zone_from_yaml():
    config = _load(ENV_PREFIX + '    zones:\n      - kind: "Master"\n')
    zone = config.environments[0].zones[0]
    assert zone.name == ""
    assert zone.kind == "Master"


def test_zone_without_name_or_filter_from_yaml_raises():
    with pytest.raises(ValidationError):
        _load(
            ENV_PREFIX
            + '    zones:\n      - description: "no name and no attribute filter"\n'
        )


def test_zone_with_invalid_regex_from_yaml_raises():
    with pytest.raises(ValidationError, match="invalid regex"):
        _load(ENV_PREFIX + '    zones:\n      - name: "["\n        regex: true\n')
