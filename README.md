# EZDNSTester


[English](README.md) | [简体中文](docs/README_zh-CN.md)

EZDNSTester is a small FastAPI app for checking how different DNS resolvers answer the same query. It supports local resolution, plain UDP DNS, DNS over TLS, and DNS over HTTPS, with both a browser UI and API endpoints for scripts or terminal use.

## What It Does

- Compare several DNS servers in one run
- Test DoH requests through an HTTP or HTTPS proxy
- Expose a DoH-compatible forwarding endpoint
- Return JSON, simple text, or formatted text for CLI use
- Run locally with Python or inside Docker

## Quick Start

### Local

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

### Docker

```bash
docker-compose up --build
```

## ARC Cache

The API layer now includes an ARC (Adaptive Replacement Cache) for upstream DNS results.

- Cache is disabled by default for all API requests
- Successful API queries can be reused from cache when the same upstream, domain, record type, and proxy are requested again
- Cache lifetime is bounded by the upstream DNS TTL and `EZDNS_API_CACHE_MAX_TTL`
- Enable it per request with `cache=true`
- Each request can further reduce the TTL with `cache_max_ttl`

Environment variables:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `EZDNS_API_CACHE_SIZE` | `512` | Maximum number of live cached query entries. Set to `0` to disable ARC caching. |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | Global upper bound, in seconds, for cached DNS results. |

## Server Strings

When an endpoint expects a DNS server, use `type://server`.

| Type    | Meaning                          | Examples                                                                   |
| ------- | -------------------------------- | -------------------------------------------------------------------------- |
| `local` | System resolver                  | `local`, `local://local`                                                   |
| `udp`   | UDP DNS, default port `53`       | `udp://8.8.8.8`, `udp://8.8.8.8:8053`, `udp://[2606:4700:4700::1111]:8053` |
| `dot`   | DNS over TLS, default port `853` | `dot://1.1.1.1`, `dot://dns.example.com:8853`                              |
| `doh`   | DNS over HTTPS                   | `doh://https://dns.google/dns-query`                                       |

If the prefix is omitted, the server is treated as UDP.

## Common Endpoints

### `POST /api/test`

Single-server query used by the web UI.

```bash
curl -X POST "http://localhost:8000/api/test" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "udp",
    "server": "8.8.8.8:8053",
    "domain": "google.com",
    "record_type": "A",
    "cache": true,
    "cache_max_ttl": 120
  }'
```

### `GET /api/query`

Useful for shell scripts and side-by-side checks.

```bash
curl "http://localhost:8000/api/query?domain=google.com"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8:8053&type=AAAA"
curl "http://localhost:8000/api/query?domain=google.com&server=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
curl "http://localhost:8000/api/query?domain=google.com&format=text"
curl "http://localhost:8000/api/query?domain=google.com&cache=true"
curl "http://localhost:8000/api/query?domain=google.com&cache=true&cache_max_ttl=60"
```

POST works the same way if you prefer sending JSON:

```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "google.com",
    "servers": [
      "udp://8.8.8.8:8053",
      "doh://https://dns.google/dns-query"
    ],
    "record_type": "A",
    "proxy": null,
    "cache": true,
    "cache_max_ttl": 120
  }'
```

Supported query parameters:

| Parameter | Meaning                                                                    |
| --------- | -------------------------------------------------------------------------- |
| `domain`  | Domain name to resolve                                                     |
| `server`  | One or more upstream servers in `type://server` format                     |
| `type`    | Record type: `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA`, `BOTH`, `ALL` |
| `proxy`   | Proxy URL for DoH requests                                                 |
| `format`  | Output format: `json`, `simple`, `text`                                    |
| `cache`   | Enable the ARC cache for this request. Disabled by default.                |
| `cache_max_ttl` | Per-request upper bound for cache TTL in seconds                    |

### `GET /dns-query` and `POST /dns-query`

EZDNSTester can also behave like a DoH-compatible upstream. In practice you will usually place it behind a reverse proxy that terminates TLS, then point clients at `/dns-query`.

```bash
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8:8053"
curl "http://localhost:8000/dns-query?dns=...&cache=true&cache_max_ttl=60"
```

```bash
curl -X POST "http://localhost:8000/dns-query" \
  -H "Content-Type: application/dns-message" \
  --data-binary @query.bin
```

Optional query parameters:

| Parameter  | Meaning                                              |
| ---------- | ---------------------------------------------------- |
| `dns`      | Base64url-encoded DNS message for `GET` requests     |
| `upstream` | Upstream resolver, including custom UDP or DoT ports |
| `proxy`    | Proxy URL for DoH upstream requests                  |
| `cache`    | Enable the ARC cache for this request. Disabled by default. |
| `cache_max_ttl` | Per-request upper bound for cache TTL in seconds |

### `GET /api/servers`

Returns the built-in server presets used by the UI and default CLI queries.

### `GET /api/cache`

Returns the ARC cache configuration and current live statistics.

### `GET /api/help`

Returns a compact machine-readable summary of the main endpoints and examples.

`/dns-query` responses also include cache headers:

- `X-Cache`: `HIT`, `MISS`, `BYPASS`, or `ERROR`
- `X-Cache-TTL`: effective TTL window used for the response
- `X-Cache-Expires-In`: remaining seconds before the cached entry is considered stale for that request

## Reverse Proxy Note

If you want to use `/dns-query` from standard DoH clients, put the app behind a reverse proxy that serves HTTPS.

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## Project Layout

- `app.py`: FastAPI entrypoint and API routes
- `arc_cache.py`: ARC cache implementation with TTL-aware entries
- `dns_tester.py`: DNS lookup helpers for UDP, DoT, DoH, and the local resolver
- `templates/index.html`: Browser UI
- `Dockerfile` and `docker-compose.yml`: Container setup

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for the full text.
