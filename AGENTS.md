# AGENTS.md

This is a Go 1.27 project. Dependencies live in `go.mod` and are pinned by
`go.sum`; there are no other package manifests. Run everything with the Go
toolchain (or the Makefile).

## Commands

    make build           # build bin/powerdns-api-proxy
    make run             # go run ./cmd/powerdns-api-proxy; needs PROXY_CONFIG_PATH
    make unit            # go test ./... -v
    make test            # lint + unit
    make lint            # golangci-lint, falling back to go vet
    make fmt             # gofmt -w
    go test ./internal/config/ -run TestGetZoneIfAllowed -v   # single test

## Layout

- `cmd/powerdns-api-proxy/` — entrypoint: env parsing, logging, Sentry, graceful shutdown.
- `internal/config/` — YAML config model, validation, token map, zone resolution.
- `internal/perm/` — zone/record/rrset and server-wide permission rules.
- `internal/upstream/` — pooled PowerDNS API client.
- `internal/server/` — router, handlers, error writing, embedded Swagger UI.
- `internal/middleware/` — audit log, access log, trusted proxy headers.
- `internal/logging/` — text/JSON logger and audit log.
- `internal/metrics/`, `internal/utils/`, `internal/httperr/` — supporting packages.

## Gotchas

- Config is read once at startup. `PROXY_CONFIG_PATH` must point at valid YAML;
  there is no hot reload.
- `LOG_LEVEL` defaults to `DEBUG` and `LOG_FILE` defaults to a `log` file; set
  `LOG_FILE=false` for local runs to avoid writing log files.
- Regexes are Go RE2 (no backreferences or lookaround; `\w`/`\d` are ASCII).
  Zone/record regexes are anchored to a full match at load time.
- Path parameters are validated before forwarding, and the server id must be
  `localhost`; anything else returns 404.
- Routing uses chi (Go 1.22-style patterns are not used); the Swagger UI
  assets come from `github.com/swaggo/files/v2` — only `index.html` and
  `openapi.json` are embedded from `internal/server/web`.
- `cryptokeys` and `tsigkeys` payloads are redacted from upstream and audit logs
  by path segment.
- `make lint` needs `golangci-lint` installed; otherwise it falls back to
  `go vet`. Building the Docker image needs a running Docker daemon.

## Conventions

Conventional Commits (`type(scope): description`) are required, feature/config
changes need an approved issue first, and `make test` must pass before a PR.
See CONTRIBUTING.md — it is the source of truth for these rules.
