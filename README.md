# PowerDNS-API-Proxy

## Description

The proxy can be used between a PowerDNS API and a client.
It should have 1:1 compatibility with the PowerDNS API.

There is the possibility to define multiple tokens. Each token is represented by an `environment`.
A `environment` can get access to one or more zones.
Within a zone, the token can be limited to one or more records.

## Usage

### Container

Containers are available under [Packages](https://github.com/akquinet/powerdns-api-proxy/pkgs/container/powerdns-api-proxy).

```bash
docker run -v config:/config -e PROXY_CONFIG_PATH=/config/config.yaml -e LOG_LEVEL=WARNING --name powerdns-api-proxy ghcr.io/akquinet/powerdns-api-proxy:latest
```

### Authentication

The token is expected in the header `X-API-Key` as with the PowerDNS API.

If the token is missing a `HTTP 401` is returned.

### RBAC

If a resource is not allowed, then a `HTTP 403` comes back.

An overview of the allowed resources of a token can be seen with a `GET` on `<url>/info/allowed`.

### API Docs

The Swagger documentation can be viewed at `<url>/docs`.

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

For this the `Environment` must have the option `global_read: true`.

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
