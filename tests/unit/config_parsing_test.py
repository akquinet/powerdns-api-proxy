import tempfile
from pathlib import Path

from powerdns_api_proxy.config import load_config


def test_index_html_from_yaml_single_line():
    config_content = """
pdns_api_url: "https://test.example.com"
pdns_api_token: "testtoken123"
index_html: "<html><body><h1>PowerDNS API Proxy</h1></body></html>"
environments:
  - name: "Test"
    token_sha512: "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
    zones:
      - name: "example.com"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write(config_content)
        f.flush()

        config_path = Path(f.name)
        config = load_config(config_path)
        assert (
            config.index_html == "<html><body><h1>PowerDNS API Proxy</h1></body></html>"
        )
        assert config.index_enabled is True


def test_index_html_from_yaml_multiline():
    config_content = """
pdns_api_url: "https://test.example.com"
pdns_api_token: "testtoken123"
index_html: |
  <html>
    <body>
      <h1>Custom Page</h1>
    </body>
  </html>
environments:
  - name: "Test"
    token_sha512: "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
    zones:
      - name: "example.com"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write(config_content)
        f.flush()

        config_path = Path(f.name)
        config = load_config(config_path)
        assert "<h1>Custom Page</h1>" in config.index_html
        assert config.index_enabled is True


def test_index_disabled_from_yaml():
    config_content = """
pdns_api_url: "https://test.example.com"
pdns_api_token: "testtoken123"
index_enabled: false
environments:
  - name: "Test"
    token_sha512: "127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d"
    zones:
      - name: "example.com"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as f:
        f.write(config_content)
        f.flush()

        config_path = Path(f.name)
        config = load_config(config_path)
        assert config.index_enabled is False
