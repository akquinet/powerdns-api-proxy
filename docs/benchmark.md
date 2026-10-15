# Benchmark: Go rewrite vs. Python implementation

This document compares the Go rewrite against the previous Python/FastAPI
implementation under identical conditions. The Go numbers were measured on the
working tree that also contains the chi router and swaggo/files changes.

**TL;DR** — the Go proxy is 8–66× faster in throughput, cuts p99 latency under
load from ~110 ms to ~6 ms on upstream paths, and uses ~4× less memory idle
(13 MB vs 64 MB) and ~3× less under load.

## Environment

| | |
| --- | --- |
| CPU | Intel Core i9-10850K @ 3.60 GHz, 20 threads |
| Memory | 62 GiB |
| Kernel | Linux 6.18.55 |
| Go | go1.27.1 |
| Python | 3.14.7 (uv-managed venv) |
| Load generator | [hey](https://github.com/rakyll/hey) v0.1.5 |
| Upstream | mock PowerDNS API on `127.0.0.1` (Go, sub-millisecond) |
| Implementations | Python `a2e246f` (main before the rewrite) · Go working tree on `21cfcfc` |
| Date | 2026-10-15 |

## Methodology

- Both proxies ran on the same host, one at a time, against the **same mock
  PowerDNS upstream** and the **same configuration** (`config.yml` with the
  `acme`, `monitoring` and `global` environments).
- Single process each: one uvicorn worker for Python, one Go process. No
  containerization, no reverse proxy in front.
- Log level `INFO` for both, so access/audit logging overhead is included
  symmetrically.
- Closed-loop load with `hey`, 10 s per run, at concurrency 1, 8 and 64,
  keep-alive enabled.
- Load generator and both proxies share the host; the measurement includes that
  noise but applies equally to both sides.

### Scenarios

| Name | Request | Path under test |
| --- | --- | --- |
| `index` | `GET /` | static page, no auth, no upstream |
| `allowed` | `GET /info/allowed` | token auth + in-memory config |
| `servers` | `GET /api/v1/servers` | auth + upstream passthrough |
| `zones` | `GET /api/v1/servers/localhost/zones` | auth + upstream + zone filtering |
| `patch` | `PATCH /api/v1/servers/localhost/zones/example.com.` | auth + RRSet permission check + upstream (`204`) |
| `unauth` | `GET /info/allowed` (bad token) | rejection path (`401`) |

## Results

| scenario | c | python req/s | go req/s | speedup | py p95 ms | go p95 ms | py p99 ms | go p99 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| index | 1 | 1770 | 14433 | 8.2× | 0.60 | 0.10 | 0.70 | 0.10 |
| index | 8 | 2339 | 87943 | 37.6× | 3.60 | 0.20 | 3.80 | 0.30 |
| index | 64 | 2312 | 97405 | 42.1× | 31.50 | 2.00 | 49.20 | 2.90 |
| allowed | 1 | 1187 | 12012 | 10.1× | 1.00 | 0.10 | 1.20 | 0.10 |
| allowed | 8 | 1385 | 73335 | 53.0× | 7.20 | 0.20 | 8.20 | 0.30 |
| allowed | 64 | 1307 | 80703 | 61.7× | 55.10 | 2.00 | 67.70 | 2.60 |
| servers | 1 | 678 | 5701 | 8.4× | 1.70 | 0.20 | 2.00 | 0.30 |
| servers | 8 | 836 | 24880 | 29.8× | 11.00 | 0.60 | 12.20 | 0.70 |
| servers | 64 | 796 | 31187 | 39.2× | 87.90 | 4.70 | 103.70 | 6.10 |
| zones | 1 | 632 | 5323 | 8.4× | 1.80 | 0.20 | 2.00 | 0.30 |
| zones | 8 | 659 | 18452 | 28.0× | 15.10 | 0.70 | 16.90 | 0.80 |
| zones | 64 | 702 | 28363 | 40.4× | 97.10 | 4.90 | 109.10 | 6.30 |
| patch | 1 | 585 | 5581 | 9.5× | 2.00 | 0.20 | 2.30 | 0.30 |
| patch | 8 | 610 | 16011 | 26.2× | 14.90 | 0.80 | 16.50 | 1.00 |
| patch | 64 | 586 | 26104 | 44.5× | 128.50 | 4.90 | 143.60 | 6.10 |
| unauth | 1 | 1420 | 13968 | 9.8× | 1.10 | 0.10 | 1.20 | 0.10 |
| unauth | 8 | 1674 | 81810 | 48.9× | 6.10 | 0.20 | 7.20 | 0.30 |
| unauth | 64 | 1536 | 100567 | 65.5× | 51.80 | 2.00 | 89.70 | 2.50 |

All responses carried the expected status (`200` / `204` / `401`); no errors in
any run.

### Memory

| | idle RSS | RSS after the load matrix |
| --- | --- | --- |
| Python | ~64 MB | ~85 MB |
| Go | ~13 MB | ~31 MB |

## Interpretation

- **Throughput** grows 8–10× even at concurrency 1 and 28–66× once the Python
  worker saturates: a single uvicorn worker plateaus around 600–2400 req/s
  depending on the scenario, while the Go process keeps scaling to 26k–100k
  req/s.
- **Tail latency** is where the difference hurts most. At c=64 the Python p99
  reaches ~110–144 ms on upstream paths (queueing behind the single worker);
  Go stays below 6.3 ms.
- The two largest contributors on the Go side are the shared pooled HTTP client
  (the Python implementation opened a new `aiohttp.ClientSession` per upstream
  request) and the absence of interpreter/GC overhead on the hot path.
- Even I/O-free paths (`/`, token rejection) improve ~8–10× at c=1, which is
  the floor imposed by process startup/request dispatch costs.

## Caveats

- The upstream is a local mock with sub-millisecond latency; these numbers
  measure **proxy overhead**, not end-to-end latency against a real PowerDNS
  server. With a remote upstream, the absolute throughput gap narrows and
  latency is dominated by the network — relative proxy overhead stays.
- The client, both proxies and the mock share one host. Go's ceiling for the
  synthetic `index` case (~100k req/s) is likely the load generator itself.
- Python can be scaled with multiple uvicorn workers; that raises throughput at
  a memory cost. It was not benchmarked, and the comparison is single-worker
  against single-process as shipped.
- Results vary run to run; treat the ratios as indicative, not exact.

## Reproducing

The Python baseline can be checked out from git history
(`git worktree add /tmp/py-bench a2e246f`), installed with `uv sync`, and run
against the same config as the Go binary:

```bash
# Python (pre-rewrite)
cd /tmp/py-bench
PROXY_CONFIG_PATH=./config.yml LOG_FILE=false LOG_LEVEL=INFO \
  .venv/bin/python -m powerdns_api_proxy &

# Go
PROXY_CONFIG_PATH=./config.yml LOG_FILE=false LOG_LEVEL=INFO \
  go run ./cmd/powerdns-api-proxy &

# Load
hey -z 10s -c 8 -H "X-API-Key: <token>" \
  http://127.0.0.1:8000/api/v1/servers/localhost/zones
```

Both need a reachable PowerDNS API (`pdns_api_url`); a local mock keeps the
numbers comparable.
