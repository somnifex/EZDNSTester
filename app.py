import asyncio
import base64
import copy
import os
import time
from typing import List, Optional

import dns.message
import dns.rcode
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns_tester
from arc_cache import AdaptiveReplacementTTLCache
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DEFAULT_RECORD_TYPE = "A"
DEFAULT_OUTPUT_FORMAT = "json"
DEFAULT_API_CACHE_SIZE = 512
DEFAULT_API_CACHE_MAX_TTL = 300


def _read_int_env(name: str, default: int, minimum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return max(minimum, int(value))
    except ValueError:
        return default


API_CACHE_SIZE = _read_int_env(
    "EZDNS_API_CACHE_SIZE", DEFAULT_API_CACHE_SIZE, minimum=0
)
API_CACHE_MAX_TTL = _read_int_env(
    "EZDNS_API_CACHE_MAX_TTL", DEFAULT_API_CACHE_MAX_TTL, minimum=1
)
API_RESULT_CACHE = AdaptiveReplacementTTLCache(API_CACHE_SIZE)

app = FastAPI(
    title="EZDNSTester API",
    description="DNS testing API with DoH forwarding and CLI query endpoints.",
    version="1.1.0",
)

app.mount("/img", StaticFiles(directory="img"), name="img")


class TestRequest(BaseModel):
    type: str
    server: str
    domain: str
    proxy: Optional[str] = None
    record_type: Optional[str] = DEFAULT_RECORD_TYPE
    cache: bool = False
    cache_max_ttl: Optional[int] = Field(default=None, ge=1)


class QueryRequest(BaseModel):
    domain: str
    servers: Optional[List[str]] = None
    record_type: Optional[str] = DEFAULT_RECORD_TYPE
    proxy: Optional[str] = None
    cache: bool = False
    cache_max_ttl: Optional[int] = Field(default=None, ge=1)


DEFAULT_SERVERS = [
    {"name": "Local", "server": "local", "type": "local"},
    {"name": "Tencent-DoH", "server": "https://doh.pub/dns-query", "type": "doh"},
    {"name": "360-DoH", "server": "https://doh.360.cn", "type": "doh"},
    {"name": "Aliyun-DoH", "server": "https://dns.alidns.com/dns-query", "type": "doh"},
    {"name": "Google-DoH", "server": "https://dns.google/dns-query", "type": "doh"},
    {"name": "Cloudflare-DoH", "server": "https://1.1.1.1/dns-query", "type": "doh"},
    {"name": "Tencent-UDP", "server": "119.29.29.29", "type": "udp"},
    {"name": "Aliyun-UDP", "server": "223.5.5.5", "type": "udp"},
    {"name": "114DNS-UDP", "server": "114.114.114.114", "type": "udp"},
    {"name": "CNNICSDNS-UDP", "server": "1.2.4.8", "type": "udp"},
    {"name": "Google-UDP", "server": "8.8.8.8", "type": "udp"},
    {"name": "Cloudflare-UDP", "server": "1.1.1.1", "type": "udp"},
]


def _normalize_record_type(record_type: Optional[str]) -> str:
    return (record_type or DEFAULT_RECORD_TYPE).upper()


def _normalize_output_format(output_format: Optional[str]) -> str:
    return (output_format or DEFAULT_OUTPUT_FORMAT).lower()


def _strip_server_comment(server: str) -> str:
    return server.partition("#")[0].strip()


def parse_server_string(server_str: str) -> dict:
    server_str = server_str.strip()
    if not server_str:
        raise ValueError("Server cannot be empty")

    if server_str.startswith("local://") or server_str == "local":
        return {"type": "local", "server": "local"}
    if server_str.startswith("doh://"):
        return {"type": "doh", "server": server_str[6:]}
    if server_str.startswith("udp://"):
        return {"type": "udp", "server": server_str[6:]}
    if server_str.startswith("dot://"):
        return {"type": "dot", "server": server_str[6:]}
    return {"type": "udp", "server": server_str}


def _normalize_domain(domain: str) -> str:
    return domain.rstrip(".").lower()


def _cache_enabled() -> bool:
    return API_RESULT_CACHE.capacity > 0


def _effective_cache_ttl(requested_cache_max_ttl: Optional[int]) -> Optional[int]:
    if not _cache_enabled():
        return None

    if requested_cache_max_ttl is None:
        return API_CACHE_MAX_TTL

    return max(1, min(requested_cache_max_ttl, API_CACHE_MAX_TTL))


def _build_cache_key(
    server_type: str,
    server: str,
    domain: str,
    record_type: str,
    proxy: Optional[str],
):
    return (
        server_type.strip().lower(),
        server.strip(),
        _normalize_domain(domain),
        record_type.upper(),
        (proxy or "").strip(),
    )


def _result_min_ttl(result: dict) -> Optional[int]:
    min_ttl = result.get("_min_ttl")
    if isinstance(min_ttl, int):
        return min_ttl

    records = result.get("_records") or []
    ttl_values = [max(0, int(record.get("ttl", 0) or 0)) for record in records]
    return min(ttl_values) if ttl_values else None


def _cache_lifetime(result: dict) -> Optional[int]:
    min_ttl = _result_min_ttl(result)
    if min_ttl is None:
        return None

    return min(min_ttl, API_CACHE_MAX_TTL)


def _request_cache_window(
    result: dict,
    use_cache: bool,
    cache_max_ttl: Optional[int],
) -> Optional[int]:
    if not use_cache:
        return None

    request_cap = _effective_cache_ttl(cache_max_ttl)
    min_ttl = _result_min_ttl(result)
    if request_cap is None or min_ttl is None:
        return None

    return min(min_ttl, request_cap)


def _cache_age_seconds(result: dict) -> int:
    cached_at = result.get("_cached_at")
    if not cached_at:
        return 0

    return max(0, int(time.time() - float(cached_at)))


def _can_use_cached_result(result: dict, cache_max_ttl: Optional[int]) -> bool:
    request_window = _request_cache_window(result, True, cache_max_ttl)
    if request_window is None:
        return False

    return _cache_age_seconds(result) < request_window


def _result_is_cacheable(result: dict) -> bool:
    min_ttl = _result_min_ttl(result)
    return (
        result.get("status") == "success"
        and bool(result.get("_records"))
        and min_ttl is not None
        and min_ttl > 0
    )


def _annotate_result(
    result: dict,
    *,
    cached: bool,
    use_cache: bool,
    cache_max_ttl: Optional[int],
) -> dict:
    result["cached"] = cached

    request_window = _request_cache_window(result, use_cache, cache_max_ttl)
    if request_window is not None:
        age_seconds = _cache_age_seconds(result) if cached else 0
        result["cache_ttl"] = request_window
        result["cache_max_ttl"] = _effective_cache_ttl(cache_max_ttl)
        result["cache_expires_in"] = max(0, request_window - age_seconds)

    return result


def _public_result(result: dict) -> dict:
    return {key: value for key, value in result.items() if not key.startswith("_")}


async def _dispatch_test_uncached(
    server_type: str,
    server: str,
    domain: str,
    record_type: str,
    proxy: Optional[str] = None,
) -> dict:
    if server_type == "local":
        return dns_tester.test_local(domain, record_type)
    if server_type == "udp":
        return dns_tester.test_udp(server, domain, record_type)
    if server_type == "dot":
        return dns_tester.test_dot(server, domain, record_type)
    if server_type == "doh":
        return await dns_tester.test_doh(server, domain, proxy, record_type)
    raise ValueError(f"Invalid test type: {server_type}")


async def _dispatch_test(
    server_type: str,
    server: str,
    domain: str,
    record_type: str,
    proxy: Optional[str] = None,
    use_cache: bool = False,
    cache_max_ttl: Optional[int] = None,
) -> dict:
    cache_allowed = bool(use_cache) and _cache_enabled()
    cache_key = _build_cache_key(server_type, server, domain, record_type, proxy)

    if cache_allowed:
        cached_result = API_RESULT_CACHE.get(cache_key)
        if cached_result is not None and _can_use_cached_result(
            cached_result, cache_max_ttl
        ):
            return _annotate_result(
                copy.deepcopy(cached_result),
                cached=True,
                use_cache=True,
                cache_max_ttl=cache_max_ttl,
            )

    result = await _dispatch_test_uncached(server_type, server, domain, record_type, proxy)

    if cache_allowed and _result_is_cacheable(result):
        cache_entry = copy.deepcopy(result)
        cache_entry["_cached_at"] = time.time()
        cache_lifetime = _cache_lifetime(cache_entry)
        if cache_lifetime is not None:
            API_RESULT_CACHE.put(cache_key, cache_entry, cache_lifetime)

    return _annotate_result(
        result,
        cached=False,
        use_cache=cache_allowed,
        cache_max_ttl=cache_max_ttl,
    )


async def _query_default_servers(
    domain: str,
    record_type: str,
    proxy: Optional[str] = None,
    use_cache: bool = False,
    cache_max_ttl: Optional[int] = None,
) -> dict:
    for server_config in DEFAULT_SERVERS:
        try:
            result = await _dispatch_test(
                server_config["type"],
                server_config["server"],
                domain,
                record_type,
                proxy,
                use_cache,
                cache_max_ttl,
            )
        except Exception:
            continue

        if result.get("status") == "success" and result.get("answers"):
            return result

    return {"status": "error", "error": "All upstream servers failed"}


def _decode_base64url_query(encoded_query: str) -> bytes:
    padding = (-len(encoded_query)) % 4
    return base64.urlsafe_b64decode(f"{encoded_query}{'=' * padding}")


def _append_records_to_response(
    response: dns.message.Message,
    question,
    records: list[dict],
    cache_max_ttl: Optional[int] = None,
    age_seconds: int = 0,
) -> None:
    for record in records:
        answer_type = record.get("type")
        answer_value = record.get("value")
        if not answer_type or not answer_value:
            continue

        ttl = max(0, int(record.get("ttl", 0) or 0))
        if cache_max_ttl is not None:
            ttl = min(ttl, cache_max_ttl)
        ttl = max(0, ttl - age_seconds)

        answer_rdtype = dns.rdatatype.from_text(answer_type)
        rrset = response.find_rrset(
            response.answer,
            question.name,
            dns.rdataclass.IN,
            answer_rdtype,
            create=True,
        )
        rrset.ttl = ttl if rrset.ttl == 0 else min(rrset.ttl, ttl)
        rrset.add(
            dns.rdata.from_text(dns.rdataclass.IN, answer_rdtype, answer_value)
        )


def _format_simple_results(domain: str, record_type: str, results: list[dict]):
    lines = [
        f"DNS Query Results for: {domain}",
        f"Record Type: {record_type}",
        "=" * 50,
    ]

    for result in results:
        status_icon = "✓" if result.get("status") == "success" else "✗"
        lines.append("")
        lines.append(
            f"{status_icon} {result.get('server', 'Unknown')} ({result.get('type', '?')})"
        )
        if result.get("status") == "success":
            lines.append(f"  Latency: {result.get('latency_ms', '-')} ms")
            if result.get("answers"):
                lines.extend(f"  → {answer}" for answer in result["answers"])
            else:
                lines.append("  → No records found")
        else:
            lines.append(f"  Error: {result.get('error', 'Unknown error')}")

    lines.extend(["", "=" * 50])
    return PlainTextResponse("\n".join(lines))


def _format_text_results(domain: str, record_type: str, results: list[dict]):
    lines = [
        f"╔{'═' * 60}╗",
        f"║ DNS Query Results".ljust(61) + "║",
        f"║ Domain: {domain}".ljust(61) + "║",
        f"║ Record Type: {record_type}".ljust(61) + "║",
        f"╠{'═' * 60}╣",
    ]

    for result in results:
        status = "SUCCESS" if result.get("status") == "success" else "FAILED"
        lines.append(f"║ Server: {result.get('server', 'Unknown')[:50]}".ljust(61) + "║")
        lines.append(
            f"║   Type: {result.get('type', '?').upper()}  |  Status: {status}".ljust(
                61
            )
            + "║"
        )
        if result.get("status") == "success":
            lines.append(
                f"║   Latency: {result.get('latency_ms', '-')} ms".ljust(61) + "║"
            )
            if result.get("answers"):
                for answer in result["answers"]:
                    lines.append(f"║   → {answer[:52]}".ljust(61) + "║")
        else:
            lines.append(
                f"║   Error: {result.get('error', 'Unknown')[:48]}".ljust(61) + "║"
            )
        lines.append(f"╟{'─' * 60}╢")

    lines[-1] = f"╚{'═' * 60}╝"
    return PlainTextResponse("\n".join(lines))


@app.get("/", response_class=FileResponse)
async def read_root():
    return FileResponse("templates/index.html")


@app.post("/api/test")
async def run_test(test_req: TestRequest):
    server = _strip_server_comment(test_req.server)
    record_type = _normalize_record_type(test_req.record_type)
    server_type = test_req.type.strip().lower()

    try:
        return _public_result(
            await _dispatch_test(
                server_type,
                server,
                test_req.domain,
                record_type,
                test_req.proxy,
                test_req.cache,
                test_req.cache_max_ttl,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def forward_dns_query(
    wire_data: bytes,
    upstream: Optional[str] = None,
    proxy: Optional[str] = None,
    use_cache: bool = False,
    cache_max_ttl: Optional[int] = None,
) -> tuple[bytes, dict]:
    try:
        query = dns.message.from_wire(wire_data)
        question = query.question[0]
        domain = str(question.name).rstrip(".")
        record_type = dns.rdatatype.to_text(question.rdtype)

        if upstream:
            parsed_server = parse_server_string(upstream)
            result = await _dispatch_test(
                parsed_server["type"],
                parsed_server["server"],
                domain,
                record_type,
                proxy,
                use_cache,
                cache_max_ttl,
            )
        else:
            result = await _query_default_servers(
                domain,
                record_type,
                proxy,
                use_cache,
                cache_max_ttl,
            )

        response = dns.message.make_response(query)
        if result.get("status") == "success" and result.get("_records"):
            request_cache_max_ttl = _effective_cache_ttl(cache_max_ttl) if use_cache else None
            _append_records_to_response(
                response,
                question,
                result["_records"],
                cache_max_ttl=request_cache_max_ttl,
                age_seconds=_cache_age_seconds(result) if result.get("cached") else 0,
            )
        else:
            response.set_rcode(dns.rcode.SERVFAIL)

        response_headers = {"X-Cache": "BYPASS"}
        if use_cache and _cache_enabled():
            response_headers["X-Cache"] = "HIT" if result.get("cached") else "MISS"
            if result.get("cache_expires_in") is not None:
                response_headers["X-Cache-Expires-In"] = str(
                    result["cache_expires_in"]
                )
            if result.get("cache_ttl") is not None:
                response_headers["X-Cache-TTL"] = str(result["cache_ttl"])

        return response.to_wire(), response_headers
    except Exception as exc:
        try:
            query = dns.message.from_wire(wire_data)
            response = dns.message.make_response(query)
            response.set_rcode(dns.rcode.SERVFAIL)
            return response.to_wire(), {"X-Cache": "ERROR"}
        except Exception as fallback_exc:
            raise HTTPException(status_code=500, detail=str(exc)) from fallback_exc


@app.get("/dns-query")
async def doh_get(
    dns: str = Query(..., description="Base64url encoded DNS query"),
    upstream: Optional[str] = Query(None, description="Upstream DNS server"),
    proxy: Optional[str] = Query(None, description="Proxy for DoH upstream"),
    cache: bool = Query(False, description="Enable the ARC result cache for this request"),
    cache_max_ttl: Optional[int] = Query(
        None,
        ge=1,
        description="Per-request upper bound for cached TTL in seconds",
    ),
):
    """DoH GET endpoint (RFC 8484)."""
    try:
        wire_data = _decode_base64url_query(dns)
        response_wire, response_headers = await forward_dns_query(
            wire_data,
            upstream,
            proxy,
            cache,
            cache_max_ttl,
        )
        return Response(
            content=response_wire,
            media_type="application/dns-message",
            headers=response_headers,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid DNS query: {exc}") from exc


@app.post("/dns-query")
async def doh_post(
    request: Request,
    upstream: Optional[str] = Query(None, description="Upstream DNS server"),
    proxy: Optional[str] = Query(None, description="Proxy for DoH upstream"),
    cache: bool = Query(False, description="Enable the ARC result cache for this request"),
    cache_max_ttl: Optional[int] = Query(
        None,
        ge=1,
        description="Per-request upper bound for cached TTL in seconds",
    ),
):
    """DoH POST endpoint (RFC 8484)."""
    content_type = request.headers.get("content-type", "")
    if "application/dns-message" not in content_type:
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/dns-message"
        )

    wire_data = await request.body()
    response_wire, response_headers = await forward_dns_query(
        wire_data,
        upstream,
        proxy,
        cache,
        cache_max_ttl,
    )
    return Response(
        content=response_wire,
        media_type="application/dns-message",
        headers=response_headers,
    )


@app.get("/api/query")
async def cli_query_get(
    domain: str = Query(..., description="Domain to query"),
    server: Optional[List[str]] = Query(None, description="DNS servers"),
    record_type: Optional[str] = Query(
        DEFAULT_RECORD_TYPE,
        alias="type",
        description="Record type",
    ),
    proxy: Optional[str] = Query(None, description="Proxy for DoH requests"),
    output_format: Optional[str] = Query(
        DEFAULT_OUTPUT_FORMAT,
        alias="format",
        description="Output format: json, text, simple",
    ),
    cache: bool = Query(False, description="Enable the ARC result cache for this request"),
    cache_max_ttl: Optional[int] = Query(
        None,
        ge=1,
        description="Per-request upper bound for cached TTL in seconds",
    ),
):
    """CLI-friendly DNS query API (GET)."""
    return await _perform_query(
        domain,
        server,
        record_type,
        proxy,
        output_format,
        cache,
        cache_max_ttl,
    )


@app.post("/api/query")
async def cli_query_post(
    query_req: QueryRequest,
    output_format: Optional[str] = Query(DEFAULT_OUTPUT_FORMAT, alias="format"),
):
    """CLI-friendly DNS query API (POST)."""
    return await _perform_query(
        query_req.domain,
        query_req.servers,
        query_req.record_type,
        query_req.proxy,
        output_format,
        query_req.cache,
        query_req.cache_max_ttl,
    )


async def _perform_query(
    domain: str,
    servers: Optional[List[str]],
    record_type: Optional[str],
    proxy: Optional[str],
    output_format: Optional[str],
    use_cache: bool,
    cache_max_ttl: Optional[int],
):
    record_type = _normalize_record_type(record_type)
    output_format = _normalize_output_format(output_format)

    if not servers:
        servers = [f"{server['type']}://{server['server']}" for server in DEFAULT_SERVERS[:5]]

    async def query_server(server_str: str) -> dict:
        try:
            parsed_server = parse_server_string(server_str)
            result = await _dispatch_test(
                parsed_server["type"],
                parsed_server["server"],
                domain,
                record_type,
                proxy,
                use_cache,
                cache_max_ttl,
            )
            return {
                "server": server_str,
                "type": parsed_server["type"],
                **result,
            }
        except Exception as exc:
            server_type = "unknown"
            try:
                server_type = parse_server_string(server_str)["type"]
            except Exception:
                pass
            return {
                "server": server_str,
                "type": server_type,
                "status": "error",
                "error": str(exc),
            }

    results = await asyncio.gather(*(query_server(server_str) for server_str in servers))

    if output_format == "simple":
        return _format_simple_results(domain, record_type, results)
    if output_format == "text":
        return _format_text_results(domain, record_type, results)
    return {
        "domain": domain,
        "record_type": record_type,
        "results": [_public_result(result) for result in results],
    }


@app.get("/api/servers")
async def list_servers():
    """List the built-in DNS servers."""
    return {
        "servers": DEFAULT_SERVERS,
        "format_hint": "Use 'type://server' when specifying servers. UDP and DoT also accept host:port, e.g. 'udp://8.8.8.8:8053', 'dot://dns.example.com:8853', or 'udp://[2606:4700:4700::1111]:8053'.",
    }


@app.get("/api/cache")
async def cache_status():
    """Show ARC cache configuration and live stats."""
    return {
        "enabled": _cache_enabled(),
        "policy": "ARC",
        "default_request_cache": False,
        "config": {
            "capacity": API_CACHE_SIZE,
            "max_ttl": API_CACHE_MAX_TTL,
            "env": {
                "size": "EZDNS_API_CACHE_SIZE",
                "max_ttl": "EZDNS_API_CACHE_MAX_TTL",
            },
        },
        "stats": API_RESULT_CACHE.stats(),
    }


@app.get("/api/help")
async def api_help():
    """Show endpoint usage and examples."""
    return {
        "endpoints": {
            "/dns-query": {
                "description": "DoH-compatible forwarding endpoint",
                "methods": ["GET", "POST"],
                "parameters": {
                    "dns": "(GET only) Base64url encoded DNS query",
                    "upstream": "Upstream DNS server to forward queries to. UDP/DoT accept host:port.",
                    "proxy": "Proxy for DoH upstream requests",
                    "cache": "Enable the ARC cache for this request. Disabled by default.",
                    "cache_max_ttl": "Per-request upper bound for cache TTL in seconds",
                },
                "examples": [
                    "curl 'http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE'",
                    "curl 'http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8'",
                    "curl 'http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8:8053'",
                    "curl 'http://localhost:8000/dns-query?dns=...&cache=true&cache_max_ttl=60'",
                ],
            },
            "/api/query": {
                "description": "Query one or more DNS servers",
                "methods": ["GET", "POST"],
                "parameters": {
                    "domain": "Domain name to query",
                    "server": "DNS server(s) in format type://server (can specify multiple). UDP/DoT accept host:port.",
                    "type": "Record type: A, AAAA, CNAME, MX, TXT, NS, SOA, BOTH, ALL",
                    "proxy": "Proxy for DoH requests",
                    "format": "Output format: json, text, simple",
                    "cache": "Enable the ARC cache for this request. Disabled by default.",
                    "cache_max_ttl": "Per-request upper bound for cache TTL in seconds",
                },
                "examples": [
                    "curl 'http://localhost:8000/api/query?domain=google.com'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8:8053'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&format=simple'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&type=AAAA&proxy=http://127.0.0.1:7890'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&cache=true'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&cache=true&cache_max_ttl=120'",
                ],
            },
            "/api/servers": {
                "description": "List the built-in server presets",
                "methods": ["GET"],
            },
            "/api/cache": {
                "description": "Show ARC cache configuration and live stats",
                "methods": ["GET"],
            },
            "/api/test": {
                "description": "Single-server test endpoint used by the web UI",
                "methods": ["POST"],
                "body_fields": {
                    "cache": "Enable the ARC cache for this request. Disabled by default.",
                    "cache_max_ttl": "Per-request upper bound for cache TTL in seconds",
                },
            },
        },
        "cache": {
            "policy": "ARC",
            "default_request_cache": False,
            "default_capacity": API_CACHE_SIZE,
            "default_max_ttl": API_CACHE_MAX_TTL,
            "request_controls": ["cache", "cache_max_ttl"],
            "response_headers": [
                "X-Cache",
                "X-Cache-TTL",
                "X-Cache-Expires-In",
            ],
            "environment_variables": {
                "size": "EZDNS_API_CACHE_SIZE",
                "max_ttl": "EZDNS_API_CACHE_MAX_TTL",
            },
        },
        "server_format": {
            "description": "Server string format: type://server",
            "types": {
                "udp": "UDP DNS (default port 53, custom host:port supported)",
                "dot": "DNS over TLS (default port 853, custom host:port supported)",
                "doh": "DNS over HTTPS",
            },
            "examples": [
                "udp://8.8.8.8",
                "udp://8.8.8.8:8053",
                "udp://223.5.5.5",
                "dot://1.1.1.1",
                "dot://dns.example.com:8853",
                "doh://https://dns.google/dns-query",
                "doh://https://1.1.1.1/dns-query",
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
