# Architecture


EZDNSTester is intentionally small: a single FastAPI process that delegates work to a transport layer and an in-memory cache.

## Layers

```
HTTP clients
     │
     ▼
┌───────────────────────────┐
│ HTTP API layer (app.py)   │
│  - request/response types │
│  - parse_server_string    │
│  - _dispatch_test         │
│  - /dns-query forwarding  │
└─────────────┬─────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ dns_tester.py│   │ arc_cache.py │
│ (local/UDP/  │   │ (ARC with    │
│  DoT/DoH)    │   │  TTL)        │
└──────────────┘   └──────────────┘
```

## HTTP API Layer — `app.py`

The FastAPI app is constructed with `title="EZDNSTester API"` and `version="1.1.0"`. Static images are mounted at `/img`; the root path serves `templates/index.html`.

Key internals:

- `TestRequest` / `QueryRequest` — Pydantic request bodies
- `DEFAULT_SERVERS` — twelve preset resolvers used when the caller does not supply one
- `parse_server_string` — converts `type://server` strings into `{type, server}` dicts
- `_dispatch_test` — the single entry point to resolve one query; consults the ARC cache, then calls one of `dns_tester.test_local/udp/dot/test_doh`
- `_query_default_servers` — iterates `DEFAULT_SERVERS` until one returns `status == "success"` with non-empty answers
- `forward_dns_query` — wire-format DoH translation for `/dns-query`
- `_perform_query` — fan-out for `/api/query` via `asyncio.gather`

## DNS Transport Helpers — `dns_tester.py`

Four entry points share the same result shape:

| Function | Transport | Library |
| --- | --- | --- |
| `test_local` | System resolver | `dns.resolver.Resolver` |
| `test_udp` | UDP DNS, default port 53 | `dns.query.udp` |
| `test_dot` | DNS over TLS, default port 853 | `dns.query.tls` (SSL check disabled) |
| `test_doh` | DNS over HTTPS (async) | `httpx.AsyncClient` (`verify=False`, optional proxy) |

The helper `_parse_dns_endpoint` normalizes `host`, `host:port`, and `[IPv6]:port` forms and enforces `1 ≤ port ≤ 65535`.

`RECORD_TYPES` maps friendly names (`A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA`, `BOTH`, `ALL`) to lists of `dns.rdatatype` values. Each call runs one query per mapped rdtype and sums latencies.

## ARC Result Cache — `arc_cache.py`

`AdaptiveReplacementTTLCache` is a thread-safe Adaptive Replacement Cache extended with per-entry TTLs:

- `T1` / `T2` — recent and frequent live entries, each holding `_CacheItem(value, expires_at)`
- `B1` / `B2` — recent and frequent ghost entries (keys only)
- `target_t1` — dynamic split point between T1 and T2; increases on B1 hits, decreases on B2 hits
- `capacity == 0` disables the cache entirely

Expired entries are pruned on every `get`, `put`, and `stats` call using `time.monotonic()`.

## Request Lifecycle

A request that reaches `_dispatch_test` with `cache=true` follows this path:

1. Build a cache key `(server_type, server, domain, record_type, proxy)`.
2. If `API_RESULT_CACHE.get(key)` returns a live entry and the cache age is smaller than the per-request window, return a deep copy annotated with `cached=true` and `X-Cache=HIT`.
3. Otherwise, dispatch to `dns_tester` and, on a successful result with `min_ttl > 0`, call `API_RESULT_CACHE.put(key, value, min(min_ttl, EZDNS_API_CACHE_MAX_TTL))`.
4. Annotate the response with `cache_ttl`, `cache_max_ttl`, and `cache_expires_in`.

## Deployment Shape

The Dockerfile uses `python:3.10-slim` and launches `uvicorn app:app --host 0.0.0.0 --port 8000`. The Compose file runs a single `dns-tester` service with `restart: unless-stopped` and port mapping `8000:8000`. See [Deployment](deployment.md).
