from typing import Optional

import ipaddress
import ssl
import time

import dns.message
import dns.query
import dns.rdatatype
import dns.resolver
import httpx

DEFAULT_RECORD_TYPE = "A"
RECORD_TYPES = {
    "A": [dns.rdatatype.A],
    "AAAA": [dns.rdatatype.AAAA],
    "CNAME": [dns.rdatatype.CNAME],
    "MX": [dns.rdatatype.MX],
    "TXT": [dns.rdatatype.TXT],
    "NS": [dns.rdatatype.NS],
    "SOA": [dns.rdatatype.SOA],
    "BOTH": [dns.rdatatype.A, dns.rdatatype.AAAA],
    "ALL": [
        dns.rdatatype.A,
        dns.rdatatype.AAAA,
        dns.rdatatype.CNAME,
        dns.rdatatype.MX,
        dns.rdatatype.TXT,
        dns.rdatatype.NS,
    ],
}
DOH_HEADERS = {
    "Content-Type": "application/dns-message",
    "Accept": "application/dns-message",
}


def _parse_dns_endpoint(server: str, default_port: int) -> tuple[str, int]:
    server = server.strip()
    if not server:
        raise ValueError("DNS server cannot be empty")

    if server.startswith("["):
        if "]" not in server:
            raise ValueError("Invalid IPv6 server format. Use [IPv6] or [IPv6]:port.")

        host, remainder = server[1:].split("]", 1)
        port = default_port
        if remainder:
            if not remainder.startswith(":"):
                raise ValueError(
                    "Invalid IPv6 server format. Use [IPv6] or [IPv6]:port."
                )

            port_text = remainder[1:]
            if not port_text.isdigit():
                raise ValueError(f"Invalid port in server '{server}'")
            port = int(port_text)
    else:
        colon_count = server.count(":")
        if colon_count == 0:
            host = server
            port = default_port
        elif colon_count == 1:
            host, port_text = server.rsplit(":", 1)
            if not host or not port_text.isdigit():
                raise ValueError(
                    "Invalid server format. Use host, host:port, or [IPv6]:port."
                )
            port = int(port_text)
        else:
            try:
                ipaddress.IPv6Address(server)
                host = server
                port = default_port
            except ValueError as exc:
                raise ValueError(
                    "Invalid server format. Use host, host:port, or [IPv6]:port."
                ) from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"Port must be between 1 and 65535: {port}")

    return host, port


def _normalize_record_type(record_type: Optional[str]) -> str:
    return (record_type or DEFAULT_RECORD_TYPE).upper()


def _resolve_record_types(record_type: Optional[str]) -> list[int]:
    normalized = _normalize_record_type(record_type)
    return RECORD_TYPES.get(normalized, RECORD_TYPES[DEFAULT_RECORD_TYPE])


def _collect_message_records(
    answer_sections, requested_type: int, include_all: bool
) -> list[dict]:
    records = []
    for rrset in answer_sections:
        if rrset.rdtype != requested_type and not include_all:
            continue

        actual_type = dns.rdatatype.to_text(rrset.rdtype)
        ttl = max(0, int(getattr(rrset, "ttl", 0) or 0))
        records.extend(
            {"type": actual_type, "value": str(rr), "ttl": ttl} for rr in rrset
        )
    return records


def _collect_resolver_records(
    response, requested_type: int, include_all: bool
) -> list[dict]:
    if response.rdtype != requested_type and not include_all:
        return []

    actual_type = dns.rdatatype.to_text(response.rdtype)
    ttl = max(0, int(getattr(getattr(response, "rrset", None), "ttl", 0) or 0))
    return [{"type": actual_type, "value": str(rr), "ttl": ttl} for rr in response]


def _records_to_answers(records: list[dict]) -> list[str]:
    return [f"[{record['type']}] {record['value']}" for record in records]


def _derive_min_ttl(records: list[dict]) -> Optional[int]:
    ttl_values = [max(0, int(record.get("ttl", 0) or 0)) for record in records]
    return min(ttl_values) if ttl_values else None


def _success_result(server: str, total_duration: float, records: list[dict]) -> dict:
    result = {
        "status": "success",
        "latency_ms": round(total_duration, 2),
        "answers": _records_to_answers(records),
        "server": server,
        "_records": records,
    }

    min_ttl = _derive_min_ttl(records)
    if min_ttl is not None:
        result["_min_ttl"] = min_ttl

    return result


def _error_result(server: str, exc: Exception) -> dict:
    return {"status": "error", "error": str(exc), "server": server}


def test_udp(
    server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0
):
    """Resolve DNS records over UDP."""
    try:
        records = []
        total_duration = 0.0
        normalized_record_type = _normalize_record_type(record_type)
        include_all = normalized_record_type == "ALL"
        server_host, server_port = _parse_dns_endpoint(server_ip, 53)

        for rdtype in _resolve_record_types(normalized_record_type):
            query = dns.message.make_query(domain, rdtype)
            start_time = time.perf_counter()
            response = dns.query.udp(
                query,
                server_host,
                port=server_port,
                timeout=timeout,
            )
            total_duration += (time.perf_counter() - start_time) * 1000
            records.extend(_collect_message_records(response.answer, rdtype, include_all))

        return _success_result(server_ip, total_duration, records)
    except Exception as exc:
        return _error_result(server_ip, exc)


def test_dot(
    server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0
):
    """Resolve DNS records over DNS over TLS."""
    try:
        records = []
        total_duration = 0.0
        normalized_record_type = _normalize_record_type(record_type)
        include_all = normalized_record_type == "ALL"
        server_host, server_port = _parse_dns_endpoint(server_ip, 853)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        for rdtype in _resolve_record_types(normalized_record_type):
            query = dns.message.make_query(domain, rdtype)
            start_time = time.perf_counter()
            response = dns.query.tls(
                query,
                server_host,
                port=server_port,
                timeout=timeout,
                ssl_context=context,
            )
            total_duration += (time.perf_counter() - start_time) * 1000
            records.extend(_collect_message_records(response.answer, rdtype, include_all))

        return _success_result(server_ip, total_duration, records)
    except Exception as exc:
        return _error_result(server_ip, exc)


async def test_doh(
    url: str,
    domain: str,
    proxy: Optional[str] = None,
    record_type: str = "ALL",
    timeout: float = 5.0,
):
    """Resolve DNS records over DNS over HTTPS."""
    try:
        records = []
        total_duration = 0.0
        normalized_record_type = _normalize_record_type(record_type)
        include_all = normalized_record_type == "ALL"

        client_kwargs = {"verify": False, "timeout": timeout}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for rdtype in _resolve_record_types(normalized_record_type):
                query = dns.message.make_query(domain, rdtype)
                start_time = time.perf_counter()
                response = await client.post(
                    url,
                    content=query.to_wire(),
                    headers=DOH_HEADERS,
                )
                response.raise_for_status()
                total_duration += (time.perf_counter() - start_time) * 1000

                message = dns.message.from_wire(response.content)
                records.extend(
                    _collect_message_records(message.answer, rdtype, include_all)
                )

        return _success_result(url, total_duration, records)
    except Exception as exc:
        return _error_result(url, exc)


def test_local(domain: str, record_type: str = "ALL", timeout: float = 5.0):
    """Resolve DNS records with the system resolver."""
    try:
        records = []
        total_duration = 0.0
        normalized_record_type = _normalize_record_type(record_type)
        include_all = normalized_record_type == "ALL"

        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout

        for rdtype in _resolve_record_types(normalized_record_type):
            try:
                start_time = time.perf_counter()
                response = resolver.resolve(domain, dns.rdatatype.to_text(rdtype))
                total_duration += (time.perf_counter() - start_time) * 1000
                records.extend(_collect_resolver_records(response, rdtype, include_all))
            except dns.resolver.NoAnswer:
                continue
            except dns.resolver.NXDOMAIN:
                continue

        return _success_result("local", total_duration, records)
    except Exception as exc:
        return _error_result("local", exc)
