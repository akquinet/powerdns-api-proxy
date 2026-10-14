# PowerDNS-API-Proxy

## Description

The proxy can be used between a PowerDNS API and a client.

There is the possibility to define multiple tokens. Each token is represented by an `environment`.
A `environment` can get access to one or more zones.
Within a zone, the token can be limited to one or more records.

*Parts of this application's source code were created with assistance from an
AI coding assistant and reviewed by human contributors.*

## Usage

### Container

Containers are available under [Packages](https://github.com/akquinet/powerdns-api-proxy/pkgs/container/powerdns-api-proxy).

```bash
docker run -v config:/config \
  -e PROXY_CONFIG_PATH=/config/config.yaml \
  -e LOG_LEVEL=INFO \
  -e LOG_FORMAT=json \
  --name powerdns-api-proxy \
  ghcr.io/akquinet/powerdns-api-proxy:latest
```

### Authentication

The token is expected in the header `X-API-Key` as with the PowerDNS API.

If the token is missing a `HTTP 401` is returned.

### RBAC

If a resource is not allowed, then a `HTTP 403` comes back.

An overview of the allowed resources of a token can be seen with a `GET` on `<url>/info/allowed`.

## Configuration

The configuration takes place in YAML format.

### Base

The Upstream PowerDNS API must be maintained at the top level.

```yaml
pdns_api_url: "https://powerdns-api.example.com"
pdns_api_token: "blablub"
pdns_api_verify_ssl: True
environments:
  ...

```

### Environment

An `environment` needs a name and a SHA512 token hash.
The hash is then compared with the hashed value from the API client request.

```yaml
...
environments:
  - name: "Test1"
    token_sha512: "1954a12ef0bf45b3a1797437509037f178af846d880115d57668a8aaa05732deedcbbd02bfa296b4f4e043b437b733fd6131933cfdc0fb50c4cf7f9f2bdaa836"
    zones:
      ...
```

A token / hash pair can be created with the following commands:

```bash
token=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 40 ; echo '')
token_hash=$(echo -n "$token" | sha512sum | cut -f 1 -d " ")
echo "Token: $token\nHash: $token_hash"
```

#### Zones

Under an `environment` `zones` can be defined.

These are specified in a list.

```yaml
...
environments:
    - name: "Test1"
      description: "Test Environment"
      zones:
        - name: "example.com"
```

> Simply specifying the zone without any further settings allows `write` permissions within the zone.
> Within a zone there are **always** `read` permissions.

##### Records

Under a `zone` `records` can be defined.

Thus the token has only `write` permissions on the `records` which are specified in the list.

```yaml
...
environments:
    - name: "Test1"
      ...
      zones:
       - name: "example.com"
         records:
           - "test.example.com"
```

###### Regex

Additionally to the `records` list a `regex_records` list can be defined.
In this list regex can be to define, which records are allowed.

```yaml
...
environments:
    - name: "Test1"
      ...
      zones:
       - name: "example.com"
         regex_records:
           - "_acme-challenge.service-.*.example.com"
```

##### Services

Under a `zone` `services` can be defined.

###### ACME

The `ACME` service allows, if only single records are specified, to create an ACME challenge for them.

```yaml
...
environments:
    - name: "Test1"
      zones:
        - name: "example.com"
          records:
            - "test.example.com"
          services:
            acme: true
```

##### Admin

Under a `zone` `admin` rights can be defined.
With this it is possible to create and delete the zone.

```yaml
...
environments:
    - name: "Test1"
      zones:
        - name: "example.com"
          admin: true
```

##### Subzones

Under a `zone` the option `subzones: true` can be set.

With this it is possible that the token also gets rights on all subzones which are under the zone.

```yaml
...
environments:
    - name: "Test1"
      zones:
        - name: "example.com"
          subzones: true
```

##### Regex

Under a `zone` the option `regex: true` can be set.

That allows use regex in the zone name.

In this example all zones which end with `.example.com` are allowed.

```YAML
...
environments:
  - name: "Test1"
    zones:
     - name: ".*\\.example.com"
       regex: true
```

#### Global read

Global `read` permissions can be defined under an `environment`.

For this the `Environment` must have the option `global_read_only: true`.

This allows the token to read all zones in the PowerDNS.

```yaml
...
environments:
    - name: "Test1"
      global_read_only: true
```

#### Global search

Global `search` rights can be defined under an `environment`.

For this, the `environment` must have the `global_search: true` option.

This makes it possible to use the `/search-data` endpoint.
<https://doc.powerdns.com/authoritative/http-api/search.html>

```yaml
...
environments:
    - name: "Test1"
      global_search: true
```

#### Global TSIGKeys

Global TSIGKeys access can be defined under an `environment`.

For this the `Environment` must have the option `global_tsigkeys: true`.

This allows the token to read and modify all TSIGKeys in the PowerDNS.

```yaml
...
environments:
    - name: "Test1"
      global_tsigkeys: true
```

#### CryptoKeys (DNSSEC)

Global or zone-specific CryptoKeys access can be enabled.

This allows for reading and writing of DNSSEC key material.

```yaml
...
environments:
    - name: "Test1"
      global_cryptokeys: true
    - name: example.com
      zones:
        - name: "example.com"
          cryptokeys: true
```

#### Global Config

Global configuration access can be defined under an `environment`.

For this the `environment` must have the option `global_config: true`.

This allows the token to read PowerDNS server configuration via:

- `GET /api/v1/servers/:server_id/config` - Returns all ConfigSettings
- `GET /api/v1/servers/:server_id/config/:config_setting_name` - Retrieve a single setting

```yaml
...
environments:
    - name: "Test1"
      global_config: true
```

#### Global Statistics

Global statistics access can be defined under an `environment`.

For this the `environment` must have the option `global_statistics: true`.

This allows the token to read PowerDNS server statistics via:

- `GET /api/v1/servers/:server_id/statistics`

<https://doc.powerdns.com/authoritative/http-api/statistics.html>

```yaml
...
environments:
    - name: "Test1"
      global_statistics: true
```

### Metrics of the proxy

The proxy exposes metrics on the `/metrics` endpoint.
With the `metrics_enabled` option set to `false`, the metrics can be disabled.

The `metrics_require_auth` option can be used to disable the need for authentication for the `/metrics` endpoint.

```yaml
...
metrics_enabled: false # default is true
metrics_require_auth: false # default is true
```

#### Give an environment access to the metrics

When the `metrics_proxy` option is set to `true`, the environment has access to the `/metrics` endpoint of the proxy.

```yaml
...
environments:
    - name: "Test1"
      metrics_proxy: true
```

When `metrics_require_auth` is enabled, basic auth needs to be used.

- username: name of the environment
- password: token

#### Metrics

The [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) is used for the default metrics.

Additionally http requests per environment are counted.

### API Docs

The API documentation can be viewed at `<url>/docs`.

It can be deactivated with the `api_docs_enabled` option.

```yaml
api_docs_enabled: false # default is true
```

### Index

The index page can be deactivated with the `index_enabled` option and customized with `index_html`.

```yaml
index_enabled: false # default is true

# Single line HTML
index_html: "<html><body><h1>PowerDNS API Proxy</h1></body></html>"

# Or multiline HTML
index_html: |
  <html>
    <body>
      <h1>PowerDNS API Proxy</h1>
      <p>Custom content here</p>
    </body>
  </html>
```

## Logging

### Environment Variables

```bash
LOG_LEVEL=DEBUG            # Optional: DEBUG, INFO, WARNING, ERROR (default: DEBUG)
LOG_FORMAT=json            # Optional: "text" (default) or "json" for structured logging
LOG_FILE=/var/log/app.log  # Optional: Log file path (default: "log"), set to "false" to disable file logging
LISTEN_HOST=0.0.0.0        # Optional: Host to bind to (default: *)
LISTEN_PORT=8000           # Optional: Port to listen on (default: 8000)
AUDIT_LOGGING=true         # Optional: set to "false" to disable audit logging (default: true)
AUDIT_LOG_CLIENT_IP=false  # Optional: set to "true" to include client IPs in audit logs (default: false)
FORWARDED_ALLOW_IPS=127.0.0.1  # Optional: peers trusted to set X-Forwarded-For (default: 127.0.0.1)
```

When `LOG_FORMAT=json` is set, all logs (application and uvicorn access logs) will be output in JSON format.

Set `AUDIT_LOGGING=false` to disable automatic audit logging of API requests.

Client IP addresses are personal data, so they are **not** logged by default.
Set `AUDIT_LOG_CLIENT_IP=true` to include them. This does not affect the uvicorn
access log, which logs the client address independently; to suppress IPs entirely,
raise the log level of the `uvicorn.access` logger as well.

### Audit Logging

All API operations (GET, POST, PUT, PATCH, DELETE) are automatically logged to stderr with structured data via middleware.

This includes both successful operations and forbidden attempts (HTTP 403).

Each audit log entry contains:

- `timestamp`: ISO 8601 timestamp
- `level`: Log level (INFO)
- `event_type`: "audit" for easy filtering
- `audit`: Structured audit data object containing:
  - `environment`: Name of the authenticated environment/token
  - `client_ip`: IP address of the client that made the request. Only present when `AUDIT_LOG_CLIENT_IP=true`; `"unknown"` when the peer address is unavailable, otherwise omitted. See [Running Behind a Reverse Proxy](#running-behind-a-reverse-proxy).
  - `method`: HTTP method (GET, POST, PUT, PATCH, DELETE)
  - `path`: Resource path that was accessed/modified
  - `status_code`: HTTP response status code
  - `payload`: Request payload (optional, for write operations; omitted for sensitive endpoints like `/cryptokeys` and `/tsigkeys`)
  - `query_params`: Query parameters (optional, for GET requests)

In addition, the upstream request and response logs for the `/cryptokeys` and
`/tsigkeys` endpoints replace the body with `<redacted>`, because they carry
DNSSEC private key and TSIG secret material.

#### Text Format (default)

```
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 PATCH /zones/example.com 204 payload={'rrsets': []}
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 GET /zones 200 query_params={'rrsets': 'true'}
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 DELETE /zones/test.com 403
```

With `AUDIT_LOG_CLIENT_IP=true`, the client IP is reported next to the environment.
The text format only prints a real address, never the `unknown` marker:

```
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 203.0.113.9 PATCH /zones/example.com 204 payload={'rrsets': []}
```

#### JSON Format (set LOG_FORMAT=json)

```json
{"timestamp": "2026-03-26T11:39:29", "level": "INFO", "event_type": "audit", "audit": {"environment": "Test1", "method": "PATCH", "path": "/zones/example.com", "status_code": 204, "payload": {"rrsets": [...]}}}
```

With `AUDIT_LOG_CLIENT_IP=true`, `client_ip` is reported next to the environment:

```json
{"timestamp": "2026-03-26T11:39:29", "level": "INFO", "event_type": "audit", "audit": {"environment": "Test1", "client_ip": "203.0.113.9", "method": "PATCH", "path": "/zones/example.com", "status_code": 204, "payload": {"rrsets": [...]}}}
```

#### Analyzing Audit Logs

With JSON format enabled, you can use `jq` to filter and analyze audit logs:

```bash
# Filter only audit events
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit")'

# Filter by environment
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit" and .audit.environment == "Test1")'

# Filter by HTTP method
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit" and .audit.method == "PATCH")'

# Filter by zone
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit" and (.audit.path | contains("/zones/example.com")))'

# Extract only key audit fields
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit") | {timestamp, environment: .audit.environment, method: .audit.method, path: .audit.path, status: .audit.status_code}'

# Show failed attempts (403)
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit" and .audit.status_code == 403)'

# Filter by client IP (requires AUDIT_LOG_CLIENT_IP=true)
docker logs powerdns-api-proxy 2>&1 | jq 'select(.event_type == "audit" and .audit.client_ip == "203.0.113.9")'
```

### Running Behind a Reverse Proxy

When the proxy runs behind a reverse proxy, `client_ip` comes from
`request.client.host`, which uvicorn rewrites from `X-Forwarded-For` only when the
immediate peer is listed in `FORWARDED_ALLOW_IPS` (default: `127.0.0.1`). Trusted
addresses become the `client_ip` and the uvicorn access-log address; untrusted
headers are ignored and the real TCP peer is used.

Set `FORWARDED_ALLOW_IPS` to the address of the reverse proxy that connects to this
service (CIDR ranges and comma-separated hosts are supported):

```bash
FORWARDED_ALLOW_IPS=10.244.0.0/16      # CIDR ranges are supported
FORWARDED_ALLOW_IPS=10.0.0.7,10.0.0.8  # or a comma-separated list of hosts
```

Minimal nginx configuration:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Avoid `FORWARDED_ALLOW_IPS=*`: it trusts every peer and lets any client forge its
own `client_ip`. Note that `$proxy_add_x_forwarded_for` *appends* to whatever the
client sent, which is correct behind another proxy but lets a direct client
prepend a forged hop; at the edge, overwrite the header instead
(`proxy_set_header X-Forwarded-For $remote_addr;`). With several hops, list every
intermediate proxy in `FORWARDED_ALLOW_IPS`.

## Development

[uv](https://docs.astral.sh/uv/) is the recommended tool for Python package
management in this repository.

### Install dependencies

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and sync the
locked environment:

```bash
make setup
```

This runs `uv sync`, which creates `.venv` and installs the dependencies from
`uv.lock`, including the dev group, and installs the [prek](https://prek.j178.dev/)
Git hook. Prefix commands with `uv run` to execute them in that environment.

### Create a virtualenv without uv

uv is only used to manage dependencies, so a plain virtualenv works too
(requires `pip >= 25.1` for `--group`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --group dev
prek install
```

The Makefile targets wrap `uv run`; without uv, invoke the tools directly from
the activated virtualenv (e.g. `pytest`, `prek run --all-files`).

### Run tests and linters

```bash
make unit    # unit tests
make lint    # run all hooks via prek (ruff, mypy, hadolint, ...)
make test    # lint + unit + integration
```

### Start a webserver with docker

On saving python files, FastAPI will reload automatically.

```bash
make run-docker-debug
```

### Environment variables

```bash
PROXY_CONFIG_PATH=./config.yml
LOG_LEVEL=DEBUG
```

## Security

Please do not report security vulnerabilities through public issues. See
[SECURITY.md](SECURITY.md) for the private reporting channels and what to expect.
