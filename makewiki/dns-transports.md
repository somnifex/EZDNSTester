# DNS Transports


`dns_tester.py` contains four entry points — one per supported transport. All four share the same success / error result shape so callers in `app.py` can treat them uniformly.

## Common Result Shape

Success:

```python
{
  "status": "success",
  "latency_ms": 12.34,        # sum of per-rdtype latencies, 2dp
  "answers": ["[A] 1.2.3.4"], # formatted for humans
  "server": <echo of caller input>,
  "_records": [ {"type": "A", "value": "1.2.3.4", "ttl": 60}, ... ],
  "_min_ttl": 60              # optional
}
```

Error:

```python
{"status": "error", "error": str(exc), "server": <echo>}
```

Fields prefixed with `_` are internal and stripped by `app._public_result` before returning to HTTP clients.

## Record Types

`RECORD_TYPES` maps friendly names to rdtype lists:

| Name | Expands to |
| --- | --- |
| `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA` | single-rdtype |
| `BOTH` | `A`, `AAAA` |
| `ALL` | `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS` |

Unknown names fall back to `A`. Each call issues one DNS query per rdtype and accumulates the wall-clock latency.

## Local Resolver — `test_local`

```python
test_local(domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

Uses `dns.resolver.Resolver()` with `resolver.timeout = resolver.lifetime = timeout`. Per-rdtype `NoAnswer` and `NXDOMAIN` are silently skipped; any other exception becomes an error result.

## UDP — `test_udp`

```python
test_udp(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

Parses `server_ip` with `_parse_dns_endpoint(..., default_port=53)` and issues queries via `dns.query.udp(query, host, port=port, timeout=timeout)`.

## DNS over TLS — `test_dot`

```python
test_dot(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

Builds an SSL context with `check_hostname = False` and `verify_mode = CERT_NONE`, then calls `dns.query.tls(query, host, port=port, timeout=timeout, ssl_context=context)`. Default port is `853`.

## DNS over HTTPS — `test_doh`

```python
async test_doh(url: str, domain: str, proxy: Optional[str] = None, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

Opens an `httpx.AsyncClient(verify=False, timeout=timeout)` (plus `proxy=` when supplied). For each rdtype it serializes a DNS query to wire form and POSTs it to `url` with headers:

```
Content-Type: application/dns-message
Accept: application/dns-message
```

`response.raise_for_status()` propagates HTTP errors into the transport's error result.

## Endpoint Parsing — `_parse_dns_endpoint`

`_parse_dns_endpoint(server: str, default_port: int) -> tuple[str, int]` accepts:

- `host` — use default port
- `host:port`
- `[IPv6]` or `[IPv6]:port`
- Bare IPv6 literal with multiple colons (validated via `ipaddress.IPv6Address`)

Rejects cases with helpful error messages:

- `DNS server cannot be empty`
- `Invalid IPv6 server format. Use [IPv6] or [IPv6]:port.`
- `Invalid port in server '{server}'`
- `Invalid server format. Use host, host:port, or [IPv6]:port.`
- `Port must be between 1 and 65535: {port}`

## Security Notes

Both `test_dot` and `test_doh` disable TLS certificate verification. This is deliberate — the tool is intended for diagnosing DNS behaviour against arbitrary servers, including ones with self-signed certificates. Do not reuse these helpers as-is for general-purpose secure DNS clients.
