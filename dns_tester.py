import dns.message
import dns.query
import dns.rdatatype
import httpx
import time
import socket
import ssl

def test_udp(server_ip: str, domain: str, record_type: str = "A", timeout: float = 5.0):
    try:
        answers = []
        total_duration = 0
        
        rdtypes = []
        if record_type == "A":
            rdtypes = [dns.rdatatype.A]
        elif record_type == "AAAA":
            rdtypes = [dns.rdatatype.AAAA]
        elif record_type == "BOTH":
            rdtypes = [dns.rdatatype.A, dns.rdatatype.AAAA]
        else:
            rdtypes = [dns.rdatatype.A]
        
        for rdtype in rdtypes:
            start_time = time.time()
            query = dns.message.make_query(domain, rdtype)
            response = dns.query.udp(query, server_ip, timeout=timeout)
            duration = (time.time() - start_time) * 1000
            total_duration += duration
            
            type_label = "A" if rdtype == dns.rdatatype.A else "AAAA"
            for rrset in response.answer:
                for rr in rrset:
                    answers.append(f"[{type_label}] {str(rr)}")
                
        return {
            "status": "success",
            "latency_ms": round(total_duration, 2),
            "answers": answers,
            "server": server_ip
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "server": server_ip
        }

def test_dot(server_ip: str, domain: str, record_type: str = "A", timeout: float = 5.0):
    """
    Test DNS resolution via DoT (DNS over TLS).
    record_type: "A" for IPv4, "AAAA" for IPv6, "BOTH" for both
    """
    try:
        answers = []
        total_duration = 0
        
        rdtypes = []
        if record_type == "A":
            rdtypes = [dns.rdatatype.A]
        elif record_type == "AAAA":
            rdtypes = [dns.rdatatype.AAAA]
        elif record_type == "BOTH":
            rdtypes = [dns.rdatatype.A, dns.rdatatype.AAAA]
        else:
            rdtypes = [dns.rdatatype.A]
        
        # Create a simplified SSL context that doesn't verify certificates strictly
        # This allows testing servers with self-signed or invalid certificates
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        for rdtype in rdtypes:
            start_time = time.time()
            query = dns.message.make_query(domain, rdtype)
            response = dns.query.tls(query, server_ip, timeout=timeout, ssl_context=context)
            duration = (time.time() - start_time) * 1000
            total_duration += duration
            
            type_label = "A" if rdtype == dns.rdatatype.A else "AAAA"
            for rrset in response.answer:
                for rr in rrset:
                    answers.append(f"[{type_label}] {str(rr)}")
                
        return {
            "status": "success",
            "latency_ms": round(total_duration, 2),
            "answers": answers,
            "server": server_ip
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "server": server_ip
        }

async def test_doh(url: str, domain: str, proxy: str = None, record_type: str = "A", timeout: float = 5.0):
    """
    Test DNS resolution via DoH (DNS over HTTPS).
    record_type: "A" for IPv4, "AAAA" for IPv6, "BOTH" for both
    """
    try:
        answers = []
        total_duration = 0
        
        rdtypes = []
        if record_type == "A":
            rdtypes = [dns.rdatatype.A]
        elif record_type == "AAAA":
            rdtypes = [dns.rdatatype.AAAA]
        elif record_type == "BOTH":
            rdtypes = [dns.rdatatype.A, dns.rdatatype.AAAA]
        else:
            rdtypes = [dns.rdatatype.A]
        
        headers = {
            "Content-Type": "application/dns-message",
            "Accept": "application/dns-message"
        }
        
        # Handle proxy
        client_kwargs = {"verify": False, "timeout": timeout}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for rdtype in rdtypes:
                start_time = time.time()
                
                # Construct DoH query using RFC 8484 (application/dns-message)
                query = dns.message.make_query(domain, rdtype)
                wire_data = query.to_wire()
                
                # Using POST for DNS wire format
                resp = await client.post(url, content=wire_data, headers=headers)
                resp.raise_for_status()
                
                response = dns.message.from_wire(resp.content)
                duration = (time.time() - start_time) * 1000
                total_duration += duration
                
                type_label = "A" if rdtype == dns.rdatatype.A else "AAAA"
                for rrset in response.answer:
                    for rr in rrset:
                        answers.append(f"[{type_label}] {str(rr)}")
                
        return {
            "status": "success",
            "latency_ms": round(total_duration, 2),
            "answers": answers,
            "server": url
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "server": url
        }
