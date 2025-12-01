# DNS Resolution Tester



A web-based tool to test DNS resolution across different protocols (UDP 53, DoH, DoT) and servers, with full API support for DoH server mode and CLI queries.

## Features

- **Multi-Protocol Support**: Test DNS resolution using UDP, DNS over HTTPS (DoH), and DNS over TLS (DoT).
- **Multi-Server Testing**: Run concurrent tests against multiple DNS servers.
- **Proxy Support**: Optional HTTP/HTTPS proxy support for DoH requests.
- **Web Interface**: Clean and responsive UI built with Vue.js and Tailwind CSS.
- **DoH Server Mode**: Act as a DoH server (RFC 8484 compliant) with configurable upstream.
- **CLI Query API**: Query multiple DNS servers via API with formatted output for command line use.
- **Docker Ready**: Easily deployable using Docker and Docker Compose.

## Prerequisites

- Python 3.9+
- Docker (optional)

## Installation & Usage

### Local Development

1. **Clone the repository**
2. **Install dependencies** (using `uv` or `pip`):
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```
3. **Run the application**:
   ```bash
   uv run uvicorn app:app --host 0.0.0.0 --port 8000
   ```
4. Open [http://localhost:8000](http://localhost:8000) in your browser.

### Docker Deployment

1. **Build and run using Docker Compose**:
   ```bash
   docker-compose up --build
   ```
2. Open [http://localhost:8000](http://localhost:8000) in your browser.

## API Reference

### 1. DoH Server Mode (`/dns-query`)

EZDNSTester can act as a DoH (DNS over HTTPS) server compliant with RFC 8484. You can use it as an upstream DoH server for clients (requires reverse proxy for TLS).

#### GET Method

```bash
# Basic DoH query (Base64url encoded DNS message)
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"

# With custom upstream server
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8"

# With DoH upstream and proxy
curl "http://localhost:8000/dns-query?dns=...&upstream=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"
```

#### POST Method

```bash
curl -X POST "http://localhost:8000/dns-query" \
     -H "Content-Type: application/dns-message" \
     --data-binary @query.bin
```

#### Parameters

| Parameter    | Description                                    |
| ------------ | ---------------------------------------------- |
| `dns`      | (GET only) Base64url encoded DNS query         |
| `upstream` | Upstream DNS server (format:`type://server`) |
| `proxy`    | Proxy for DoH upstream requests                |

### 2. CLI Query API (`/api/query`)

Query multiple DNS servers and get formatted results, perfect for command line use.

#### GET Method

```bash
# Query with default servers
curl "http://localhost:8000/api/query?domain=google.com"

# Query specific servers
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"

# Query with record type
curl "http://localhost:8000/api/query?domain=google.com&type=AAAA"

# Query with proxy for DoH
curl "http://localhost:8000/api/query?domain=google.com&server=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"

# Simple text output (great for CLI)
curl "http://localhost:8000/api/query?domain=google.com&format=simple"

# Formatted text output
curl "http://localhost:8000/api/query?domain=google.com&format=text"
```

#### POST Method

```bash
curl -X POST "http://localhost:8000/api/query" \
     -H "Content-Type: application/json" \
     -d '{
       "domain": "google.com",
       "servers": ["udp://8.8.8.8", "doh://https://dns.google/dns-query"],
       "record_type": "A",
       "proxy": null
     }'
```

#### Parameters

| Parameter  | Description                                                                                 |
| ---------- | ------------------------------------------------------------------------------------------- |
| `domain` | Domain name to query (required)                                                             |
| `server` | DNS server(s) in format `type://server` (can specify multiple)                            |
| `type`   | Record type:`A`, `AAAA`, `CNAME`, `MX`, `TXT`, `NS`, `SOA`, `BOTH`, `ALL` |
| `proxy`  | Proxy for DoH requests                                                                      |
| `format` | Output format:`json` (default), `text`, `simple`                                      |

#### Output Formats

**JSON (default)**

```json
{
  "domain": "google.com",
  "record_type": "A",
  "results": [
    {
      "server": "udp://8.8.8.8",
      "type": "udp",
      "status": "success",
      "latency_ms": 45.23,
      "answers": ["[A] 142.250.190.78"]
    }
  ]
}
```

**Simple (for CLI)**

```
DNS Query Results for: google.com
Record Type: A
==================================================

✓ udp://8.8.8.8 (udp)
  Latency: 45.23 ms
  → [A] 142.250.190.78

==================================================
```

### 3. List Default Servers (`/api/servers`)

```bash
curl "http://localhost:8000/api/servers"
```

### 4. API Help (`/api/help`)

```bash
curl "http://localhost:8000/api/help"
```

## Server String Format

When specifying DNS servers, use the format `type://server`:

| Type    | Description             | Example                                |
| ------- | ----------------------- | -------------------------------------- |
| `udp` | UDP DNS (port 53)       | `udp://8.8.8.8`                      |
| `dot` | DNS over TLS (port 853) | `dot://1.1.1.1`                      |
| `doh` | DNS over HTTPS          | `doh://https://dns.google/dns-query` |

If no type prefix is provided, `udp` is assumed.

## Using as DoH Server

To use EZDNSTester as a DoH server for clients:

1. Deploy behind a reverse proxy (nginx, Caddy) that provides TLS
2. Configure the reverse proxy to forward `/dns-query` requests
3. Use the URL as DoH upstream in your DNS client

Example nginx configuration:

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## Project Structure

- `app.py`: FastAPI backend application with DoH server and CLI API.
- `dns_tester.py`: Core DNS testing logic.
- `templates/index.html`: Frontend Web UI.
- `Dockerfile` & `docker-compose.yml`: Docker configuration.

## License

MIT
