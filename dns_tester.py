import dns.message
import dns.query
import dns.rdatatype
import dns.resolver
import httpx
import time
import ssl

def test_udp(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0):
    """Test DNS resolution via UDP."""
    try:
        answers = []
        total_duration = 0
        
        type_map = {
            "A": [dns.rdatatype.A],
            "AAAA": [dns.rdatatype.AAAA],
            "CNAME": [dns.rdatatype.CNAME],
            "MX": [dns.rdatatype.MX],
            "TXT": [dns.rdatatype.TXT],
            "NS": [dns.rdatatype.NS],
            "SOA": [dns.rdatatype.SOA],
            "BOTH": [dns.rdatatype.A, dns.rdatatype.AAAA],
            "ALL": [dns.rdatatype.A, dns.rdatatype.AAAA, dns.rdatatype.CNAME, dns.rdatatype.MX, dns.rdatatype.TXT, dns.rdatatype.NS],
        }
        
        rdtypes = type_map.get(record_type, [dns.rdatatype.A])
        
        for rdtype in rdtypes:
            start_time = time.time()
            query = dns.message.make_query(domain, rdtype)
            response = dns.query.udp(query, server_ip, timeout=timeout)
            duration = (time.time() - start_time) * 1000
            total_duration += duration
            
            for rrset in response.answer:
                actual_type = dns.rdatatype.to_text(rrset.rdtype)
                if rrset.rdtype == rdtype or record_type == "ALL":
                    for rr in rrset:
                        answers.append(f"[{actual_type}] {str(rr)}")
                
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

def test_dot(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0):
    """Test DNS resolution via DoT (DNS over TLS)."""
    try:
        answers = []
        total_duration = 0
        
        type_map = {
            "A": [dns.rdatatype.A],
            "AAAA": [dns.rdatatype.AAAA],
            "CNAME": [dns.rdatatype.CNAME],
            "MX": [dns.rdatatype.MX],
            "TXT": [dns.rdatatype.TXT],
            "NS": [dns.rdatatype.NS],
            "SOA": [dns.rdatatype.SOA],
            "BOTH": [dns.rdatatype.A, dns.rdatatype.AAAA],
            "ALL": [dns.rdatatype.A, dns.rdatatype.AAAA, dns.rdatatype.CNAME, dns.rdatatype.MX, dns.rdatatype.TXT, dns.rdatatype.NS],
        }
        
        rdtypes = type_map.get(record_type, [dns.rdatatype.A])
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        for rdtype in rdtypes:
            start_time = time.time()
            query = dns.message.make_query(domain, rdtype)
            response = dns.query.tls(query, server_ip, timeout=timeout, ssl_context=context)
            duration = (time.time() - start_time) * 1000
            total_duration += duration
            
            for rrset in response.answer:
                actual_type = dns.rdatatype.to_text(rrset.rdtype)
                if rrset.rdtype == rdtype or record_type == "ALL":
                    for rr in rrset:
                        answers.append(f"[{actual_type}] {str(rr)}")
                
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

async def test_doh(url: str, domain: str, proxy: str | None = None, record_type: str = "ALL", timeout: float = 5.0):
    """Test DNS resolution via DoH (DNS over HTTPS)."""
    try:
        answers = []
        total_duration = 0
        
        type_map = {
            "A": [dns.rdatatype.A],
            "AAAA": [dns.rdatatype.AAAA],
            "CNAME": [dns.rdatatype.CNAME],
            "MX": [dns.rdatatype.MX],
            "TXT": [dns.rdatatype.TXT],
            "NS": [dns.rdatatype.NS],
            "SOA": [dns.rdatatype.SOA],
            "BOTH": [dns.rdatatype.A, dns.rdatatype.AAAA],
            "ALL": [dns.rdatatype.A, dns.rdatatype.AAAA, dns.rdatatype.CNAME, dns.rdatatype.MX, dns.rdatatype.TXT, dns.rdatatype.NS],
        }
        
        rdtypes = type_map.get(record_type, [dns.rdatatype.A])
        
        headers = {
            "Content-Type": "application/dns-message",
            "Accept": "application/dns-message"
        }
        
        client_kwargs = {"verify": False, "timeout": timeout}
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for rdtype in rdtypes:
                start_time = time.time()
                
                query = dns.message.make_query(domain, rdtype)
                wire_data = query.to_wire()
                
                resp = await client.post(url, content=wire_data, headers=headers)
                resp.raise_for_status()
                
                response = dns.message.from_wire(resp.content)
                duration = (time.time() - start_time) * 1000
                total_duration += duration
                
                for rrset in response.answer:
                    actual_type = dns.rdatatype.to_text(rrset.rdtype)
                    if rrset.rdtype == rdtype or record_type == "ALL":
                        for rr in rrset:
                            answers.append(f"[{actual_type}] {str(rr)}")
                
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

def test_local(domain: str, record_type: str = "ALL", timeout: float = 5.0):
    """Test DNS resolution via system default resolver."""
    try:
        answers = []
        total_duration = 0
        
        type_map = {
            "A": [dns.rdatatype.A],
            "AAAA": [dns.rdatatype.AAAA],
            "CNAME": [dns.rdatatype.CNAME],
            "MX": [dns.rdatatype.MX],
            "TXT": [dns.rdatatype.TXT],
            "NS": [dns.rdatatype.NS],
            "SOA": [dns.rdatatype.SOA],
            "BOTH": [dns.rdatatype.A, dns.rdatatype.AAAA],
            "ALL": [dns.rdatatype.A, dns.rdatatype.AAAA, dns.rdatatype.CNAME, dns.rdatatype.MX, dns.rdatatype.TXT, dns.rdatatype.NS],
        }
        
        rdtypes = type_map.get(record_type, [dns.rdatatype.A])
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        
        for rdtype in rdtypes:
            try:
                start_time = time.time()
                response = resolver.resolve(domain, dns.rdatatype.to_text(rdtype))
                duration = (time.time() - start_time) * 1000
                total_duration += duration
                
                actual_type = dns.rdatatype.to_text(response.rdtype)
                if response.rdtype == rdtype or record_type == "ALL":
                    for rr in response:
                        answers.append(f"[{actual_type}] {str(rr)}")
            except dns.resolver.NoAnswer:
                continue
            except dns.resolver.NXDOMAIN:
                continue
                
        return {
            "status": "success",
            "latency_ms": round(total_duration, 2),
            "answers": answers,
            "server": "local"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "server": "local"
        }
