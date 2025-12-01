from fastapi import FastAPI, Request, HTTPException, Query, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import dns_tester
import dns.message
import dns.rdatatype
import base64
import asyncio

app = FastAPI(
    title="EZDNSTester API",
    description="DNS Resolution Tester with DoH server and CLI query support",
    version="1.0.0",
)

app.mount("/img", StaticFiles(directory="img"), name="img")


class TestRequest(BaseModel):
    type: str
    server: str
    domain: str
    proxy: Optional[str] = None
    record_type: Optional[str] = "A"


class QueryRequest(BaseModel):
    domain: str
    servers: Optional[List[str]] = None
    record_type: Optional[str] = "A"
    proxy: Optional[str] = None


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


@app.get("/", response_class=FileResponse)
async def read_root():
    return FileResponse("templates/index.html")


@app.post("/api/test")
async def run_test(test_req: TestRequest):
    server = test_req.server.split("#")[0]
    record_type = test_req.record_type or "A"

    if test_req.type == "local":
        return dns_tester.test_local(test_req.domain, record_type)
    elif test_req.type == "udp":
        return dns_tester.test_udp(server, test_req.domain, record_type)
    elif test_req.type == "dot":
        return dns_tester.test_dot(server, test_req.domain, record_type)
    elif test_req.type == "doh":
        return await dns_tester.test_doh(
            server, test_req.domain, test_req.proxy, record_type
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid test type")


def parse_server_string(server_str: str) -> dict:
    """Parse server string: 'type://server' or plain 'server' (defaults to UDP)."""
    if server_str.startswith("local://") or server_str == "local":
        return {"type": "local", "server": "local"}
    elif server_str.startswith("doh://"):
        return {"type": "doh", "server": server_str[6:]}
    elif server_str.startswith("udp://"):
        return {"type": "udp", "server": server_str[6:]}
    elif server_str.startswith("dot://"):
        return {"type": "dot", "server": server_str[6:]}
    else:
        return {"type": "udp", "server": server_str}


async def forward_dns_query(
    wire_data: bytes, upstream: Optional[str] = None, proxy: Optional[str] = None
) -> bytes:

    try:
        query = dns.message.from_wire(wire_data)
        domain = str(query.question[0].name)
        rdtype = query.question[0].rdtype
        rdtype_str = dns.rdatatype.to_text(rdtype)

        if upstream:
            parsed = parse_server_string(upstream)
            server_type = parsed["type"]
            server = parsed["server"]

            if server_type == "local":
                result = dns_tester.test_local(domain.rstrip("."), rdtype_str)
            elif server_type == "udp":
                result = dns_tester.test_udp(server, domain.rstrip("."), rdtype_str)
            elif server_type == "dot":
                result = dns_tester.test_dot(server, domain.rstrip("."), rdtype_str)
            elif server_type == "doh":
                result = await dns_tester.test_doh(
                    server, domain.rstrip("."), proxy, rdtype_str
                )
            else:
                raise ValueError(f"Unknown server type: {server_type}")
        else:
            result = None
            for s in DEFAULT_SERVERS:
                server_type = s["type"]
                server = s["server"]
                try:
                    if server_type == "local":
                        result = dns_tester.test_local(domain.rstrip("."), rdtype_str)
                    elif server_type == "udp":
                        result = dns_tester.test_udp(
                            server, domain.rstrip("."), rdtype_str
                        )
                    elif server_type == "dot":
                        result = dns_tester.test_dot(
                            server, domain.rstrip("."), rdtype_str
                        )
                    elif server_type == "doh":
                        result = await dns_tester.test_doh(
                            server, domain.rstrip("."), proxy, rdtype_str
                        )

                    if (
                        result
                        and result.get("status") == "success"
                        and result.get("answers")
                    ):
                        break
                except:
                    continue

            if not result:
                result = {"status": "error", "error": "All upstream servers failed"}

        response = dns.message.make_response(query)

        if result.get("status") == "success" and result.get("answers"):
            for ans in result["answers"]:
                if ans.startswith("["):
                    type_end = ans.index("]")
                    ans_type = ans[1:type_end]
                    ans_value = ans[type_end + 2 :]

                    ans_rdtype = dns.rdatatype.from_text(ans_type)
                    rrset = response.find_rrset(
                        response.answer,
                        query.question[0].name,
                        dns.rdataclass.IN,
                        ans_rdtype,
                        create=True,
                    )
                    rd = dns.rdata.from_text(dns.rdataclass.IN, ans_rdtype, ans_value)
                    rrset.add(rd)
        else:
            response.set_rcode(dns.rcode.SERVFAIL)

        return response.to_wire()

    except Exception as e:
        try:
            query = dns.message.from_wire(wire_data)
            response = dns.message.make_response(query)
            response.set_rcode(dns.rcode.SERVFAIL)
            return response.to_wire()
        except:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/dns-query")
async def doh_get(
    dns: str = Query(..., description="Base64url encoded DNS query"),
    upstream: Optional[str] = Query(None, description="Upstream DNS server"),
    proxy: Optional[str] = Query(None, description="Proxy for DoH upstream"),
):
    """DoH GET endpoint (RFC 8484)."""
    try:
        padding = 4 - len(dns) % 4
        if padding != 4:
            dns += "=" * padding
        wire_data = base64.urlsafe_b64decode(dns)

        response_wire = await forward_dns_query(wire_data, upstream, proxy)

        return Response(content=response_wire, media_type="application/dns-message")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid DNS query: {str(e)}")


@app.post("/dns-query")
async def doh_post(
    request: Request,
    upstream: Optional[str] = Query(None, description="Upstream DNS server"),
    proxy: Optional[str] = Query(None, description="Proxy for DoH upstream"),
):
    """DoH POST endpoint (RFC 8484)."""
    content_type = request.headers.get("content-type", "")
    if "application/dns-message" not in content_type:
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/dns-message"
        )

    wire_data = await request.body()
    response_wire = await forward_dns_query(wire_data, upstream, proxy)

    return Response(content=response_wire, media_type="application/dns-message")


@app.get("/api/query")
async def cli_query_get(
    domain: str = Query(..., description="Domain to query"),
    server: Optional[List[str]] = Query(None, description="DNS servers"),
    type: Optional[str] = Query("A", description="Record type"),
    proxy: Optional[str] = Query(None, description="Proxy for DoH requests"),
    format: Optional[str] = Query(
        "json", description="Output format: json, text, simple"
    ),
):
    """CLI-friendly DNS query API (GET)."""
    return await _perform_query(domain, server, type, proxy, format)


@app.post("/api/query")
async def cli_query_post(
    query_req: QueryRequest, format: Optional[str] = Query("json")
):
    """CLI-friendly DNS query API (POST)."""
    return await _perform_query(
        query_req.domain,
        query_req.servers,
        query_req.record_type,
        query_req.proxy,
        format,
    )


async def _perform_query(
    domain: str,
    servers: Optional[List[str]],
    record_type: Optional[str],
    proxy: Optional[str],
    output_format: Optional[str],
):
    """Perform DNS query across multiple servers."""
    if not record_type:
        record_type = "A"
    if not output_format:
        output_format = "json"

    if not servers:
        servers = [f"{s['type']}://{s['server']}" for s in DEFAULT_SERVERS[:5]]

    results = []

    async def query_server(server_str: str):
        parsed = parse_server_string(server_str)
        server_type = parsed["type"]
        server = parsed["server"]

        try:
            if server_type == "local":
                result = dns_tester.test_local(domain, record_type)
            elif server_type == "udp":
                result = dns_tester.test_udp(server, domain, record_type)
            elif server_type == "dot":
                result = dns_tester.test_dot(server, domain, record_type)
            elif server_type == "doh":
                result = await dns_tester.test_doh(server, domain, proxy, record_type)
            else:
                result = {
                    "status": "error",
                    "error": f"Unknown server type: {server_type}",
                }

            return {"server": server_str, "type": server_type, **result}
        except Exception as e:
            return {
                "server": server_str,
                "type": server_type,
                "status": "error",
                "error": str(e),
            }

    tasks = [query_server(s) for s in servers]
    results = await asyncio.gather(*tasks)

    if output_format == "simple":
        lines = [
            f"DNS Query Results for: {domain}",
            f"Record Type: {record_type}",
            "=" * 50,
        ]
        for r in results:
            status_icon = "✓" if r.get("status") == "success" else "✗"
            lines.append(
                f"\n{status_icon} {r.get('server', 'Unknown')} ({r.get('type', '?')})"
            )
            if r.get("status") == "success":
                lines.append(f"  Latency: {r.get('latency_ms', '-')} ms")
                if r.get("answers"):
                    for ans in r["answers"]:
                        lines.append(f"  → {ans}")
                else:
                    lines.append("  → No records found")
            else:
                lines.append(f"  Error: {r.get('error', 'Unknown error')}")
        lines.append("\n" + "=" * 50)
        return PlainTextResponse("\n".join(lines))

    elif output_format == "text":
        lines = []
        lines.append(f"╔{'═' * 60}╗")
        lines.append(f"║ DNS Query Results".ljust(61) + "║")
        lines.append(f"║ Domain: {domain}".ljust(61) + "║")
        lines.append(f"║ Record Type: {record_type}".ljust(61) + "║")
        lines.append(f"╠{'═' * 60}╣")

        for r in results:
            status = "SUCCESS" if r.get("status") == "success" else "FAILED"
            lines.append(f"║ Server: {r.get('server', 'Unknown')[:50]}".ljust(61) + "║")
            lines.append(
                f"║   Type: {r.get('type', '?').upper()}  |  Status: {status}".ljust(61)
                + "║"
            )
            if r.get("status") == "success":
                lines.append(
                    f"║   Latency: {r.get('latency_ms', '-')} ms".ljust(61) + "║"
                )
                if r.get("answers"):
                    for ans in r["answers"]:
                        lines.append(f"║   → {ans[:52]}".ljust(61) + "║")
            else:
                lines.append(
                    f"║   Error: {r.get('error', 'Unknown')[:48]}".ljust(61) + "║"
                )
            lines.append(f"╟{'─' * 60}╢")

        lines[-1] = f"╚{'═' * 60}╝"
        return PlainTextResponse("\n".join(lines))

    else:
        return {"domain": domain, "record_type": record_type, "results": results}


@app.get("/api/servers")
async def list_servers():
    """List all available default DNS servers."""
    return {
        "servers": DEFAULT_SERVERS,
        "format_hint": "Use 'type://server' format when specifying servers, e.g., 'udp://8.8.8.8' or 'doh://https://dns.google/dns-query'",
    }


@app.get("/api/help")
async def api_help():
    """API usage help and examples."""
    return {
        "endpoints": {
            "/dns-query": {
                "description": "DoH Server Mode (RFC 8484) - Can be used as a DoH upstream for clients",
                "methods": ["GET", "POST"],
                "parameters": {
                    "dns": "(GET only) Base64url encoded DNS query",
                    "upstream": "Upstream DNS server to forward queries to",
                    "proxy": "Proxy for DoH upstream requests",
                },
                "examples": [
                    "curl 'http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE'",
                    "curl 'http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8'",
                ],
            },
            "/api/query": {
                "description": "CLI Query Mode - Query multiple DNS servers and get formatted results",
                "methods": ["GET", "POST"],
                "parameters": {
                    "domain": "Domain name to query",
                    "server": "DNS server(s) in format type://server (can specify multiple)",
                    "type": "Record type: A, AAAA, CNAME, MX, TXT, NS, SOA, BOTH, ALL",
                    "proxy": "Proxy for DoH requests",
                    "format": "Output format: json, text, simple",
                },
                "examples": [
                    "curl 'http://localhost:8000/api/query?domain=google.com'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&format=simple'",
                    "curl 'http://localhost:8000/api/query?domain=google.com&type=AAAA&proxy=http://127.0.0.1:7890'",
                ],
            },
            "/api/servers": {
                "description": "List all available default DNS servers",
                "methods": ["GET"],
            },
            "/api/test": {
                "description": "Original single server test endpoint (used by Web UI)",
                "methods": ["POST"],
            },
        },
        "server_format": {
            "description": "Server string format: type://server",
            "types": {
                "udp": "UDP DNS (port 53)",
                "dot": "DNS over TLS (port 853)",
                "doh": "DNS over HTTPS",
            },
            "examples": [
                "udp://8.8.8.8",
                "udp://223.5.5.5",
                "dot://1.1.1.1",
                "doh://https://dns.google/dns-query",
                "doh://https://1.1.1.1/dns-query",
            ],
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
