# API Reference


All endpoints live in `app.py`. Unless noted, responses are JSON.

## `GET /`

Serves the browser UI from `templates/index.html`.

## `POST /api/test`

Single-server test used by the web UI.

Request body (`TestRequest`):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `type` | string | — | `local`, `udp`, `dot`, or `doh` |
| `server` | string | — | Host, URL, or `local` |
| `domain` | string | — | Domain to query |
| `proxy` | string? | `null` | Proxy URL for DoH upstream |
| `record_type` | string? | `A` | `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA`, `BOTH`, `ALL` |
| `cache` | bool | `false` | Enable the ARC cache for this request |
| `cache_max_ttl` | int? (>=1) | `null` | Per-request upper bound for cache TTL (s) |

Trailing `# comment` segments in `server` are stripped. Invalid input raises `HTTP 400` with the underlying `ValueError` message (for example `Server cannot be empty` or `Invalid test type: {t}`).

```bash
curl -X POST "http://localhost:8000/api/test" \
  -H "Content-Type: application/json" \
  -d '{"type":"udp","server":"8.8.8.8:8053","domain":"google.com","record_type":"A","cache":true,"cache_max_ttl":120}'
```

## `GET /api/query` and `POST /api/query`

Fan-out query across one or more servers.

Query / body parameters:

| Parameter | Type | Notes |
| --- | --- | --- |
| `domain` | string | Required |
| `server` (GET) / `servers` (POST) | list[string] | Repeat or pass an array. Defaults to the first five presets in `DEFAULT_SERVERS`. |
| `type` (alias for `record_type`) | string | Default `A` |
| `proxy` | string? | Proxy URL for DoH |
| `format` | string | `json` (default), `simple`, `text` |
| `cache` | bool | Default `false` |
| `cache_max_ttl` | int? (>=1) | Optional TTL cap |

JSON response shape:

```json
{
  "domain": "google.com",
  "record_type": "A",
  "results": [
    { "server": "...", "type": "udp", "status": "success", "latency_ms": 12.34, "answers": ["[A] 142.250.0.0"], "cached": false }
  ]
}
```

`format=simple` returns a compact plain-text report; `format=text` returns a boxed ASCII layout for terminals.

```bash
curl "http://localhost:8000/api/query?domain=google.com"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
curl "http://localhost:8000/api/query?domain=google.com&cache=true&cache_max_ttl=60"
```

## `GET /dns-query` and `POST /dns-query`

DoH-compatible forwarding endpoint (RFC 8484).

| Parameter | Applies to | Notes |
| --- | --- | --- |
| `dns` | GET | Base64url-encoded DNS wire message |
| `upstream` | GET, POST | `type://server`; UDP/DoT accept `host:port` |
| `proxy` | GET, POST | Proxy for DoH upstream |
| `cache` | GET, POST | Enable the ARC cache for this request |
| `cache_max_ttl` | GET, POST | Per-request TTL cap |

`POST` requires `Content-Type: application/dns-message` (otherwise `HTTP 415`). When no `upstream` is specified, the endpoint falls back to `_query_default_servers`, which iterates the twelve presets until one returns a successful answer; if none does, it responds with a SERVFAIL DNS message.

Response headers:

| Header | Meaning |
| --- | --- |
| `X-Cache` | `HIT`, `MISS`, `BYPASS`, or `ERROR` |
| `X-Cache-TTL` | Effective TTL window for the response |
| `X-Cache-Expires-In` | Remaining seconds before the cached entry is considered stale |

```bash
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8:8053"
curl -X POST "http://localhost:8000/dns-query" -H "Content-Type: application/dns-message" --data-binary @query.bin
```

## `GET /api/servers`

Returns the built-in server presets:

```json
{
  "servers": [{ "name": "Local", "server": "local", "type": "local" }, "..."],
  "format_hint": "Use 'type://server' when specifying servers. UDP and DoT also accept host:port, ..."
}
```

## `GET /api/cache`

Returns ARC cache configuration and live statistics:

```json
{
  "enabled": true,
  "policy": "ARC",
  "default_request_cache": false,
  "config": {
    "capacity": 512,
    "max_ttl": 300,
    "env": { "size": "EZDNS_API_CACHE_SIZE", "max_ttl": "EZDNS_API_CACHE_MAX_TTL" }
  },
  "stats": {
    "capacity": 512,
    "live_entries": 0,
    "recent_entries": 0,
    "frequent_entries": 0,
    "recent_ghosts": 0,
    "frequent_ghosts": 0,
    "target_recent_size": 0.0
  }
}
```

## `GET /api/help`

Compact machine-readable summary of every endpoint above, including cache semantics and server-string examples.

## Server String Format

All endpoints that accept a `server` (or `upstream`) string use the form `type://server`:

| Type | Default port | Example |
| --- | --- | --- |
| `local` | — | `local`, `local://local` |
| `udp` | 53 | `udp://8.8.8.8`, `udp://8.8.8.8:8053`, `udp://[2606:4700:4700::1111]:8053` |
| `dot` | 853 | `dot://1.1.1.1`, `dot://dns.example.com:8853` |
| `doh` | — | `doh://https://dns.google/dns-query` |

If the prefix is omitted the server is treated as UDP.

## Error Messages

Errors that bubble out as `HTTP 400` or appear in response bodies:

- `Server cannot be empty`
- `Invalid test type: {server_type}`
- `DNS server cannot be empty`
- `Invalid IPv6 server format. Use [IPv6] or [IPv6]:port.`
- `Invalid port in server '{server}'`
- `Invalid server format. Use host, host:port, or [IPv6]:port.`
- `Port must be between 1 and 65535: {port}`
- `All upstream servers failed` (from `_query_default_servers`)
- `Invalid DNS query: {exc}` (DoH GET decoding)
