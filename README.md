# PowerDNS-API-Proxy

## Description

The proxy can be used between a PowerDNS API and a client.

There is the possibility to define multiple tokens. Each token is represented by an `environment`.
A `environment` can get access to one or more zones.
Within a zone, the token can be limited to one or more records.

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

* username: name of the environment
* password: token

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
```

When `LOG_FORMAT=json` is set, all logs (application and uvicorn access logs) will be output in JSON format.

Set `AUDIT_LOGGING=false` to disable automatic audit logging of API requests.

### Audit Logging

All API operations (GET, POST, PUT, PATCH, DELETE) are automatically logged to stderr with structured data via middleware.

This includes both successful operations and forbidden attempts (HTTP 403).

Each audit log entry contains:

* `timestamp`: ISO 8601 timestamp
* `level`: Log level (INFO)
* `event_type`: "audit" for easy filtering
* `audit`: Structured audit data object containing:
  * `environment`: Name of the authenticated environment/token
  * `method`: HTTP method (GET, POST, PUT, PATCH, DELETE)
  * `path`: Resource path that was accessed/modified
  * `status_code`: HTTP response status code
  * `payload`: Request payload (optional, for write operations; omitted for sensitive endpoints like `/cryptokeys` and `/tsigkeys`)
  * `query_params`: Query parameters (optional, for GET requests)

#### Text Format (default)

```
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 PATCH /zones/example.com 204 payload={'rrsets': []}
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 GET /zones 200 query_params={'rrsets': 'true'}
INFO - 2026-03-26 12:03:21,323 - powerdns_api_proxy - proxy.py - audit - 70 - AUDIT: Test1 DELETE /zones/test.com 403
```

#### JSON Format (set LOG_FORMAT=json)

```json
{"timestamp": "2026-03-26T11:39:29", "level": "INFO", "event_type": "audit", "audit": {"environment": "Test1", "method": "PATCH", "path": "/zones/example.com", "status_code": 204, "payload": {"rrsets": [...]}}}
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
```

## Development

### Install requirements

```bash
virtualenv .venv && source .venv/bin/activate
make setup
```

### Run tests

```bash
make unit
make test
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
