# Deployment


EZDNSTester is a single-process FastAPI app and can be deployed either directly with Python or as a container.

## Direct Python

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

`requirements.txt` declares:

```
fastapi
uvicorn
dnspython
httpx[http2,socks]
jinja2
python-multipart
```

None of the dependencies are version-pinned — pinning is left to the deployer.

## Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

The image copies the entire repository into `/app`, so `templates/`, `img/`, and the Python modules are all available at runtime.

## docker-compose.yml

```yaml
version: '3.8'

services:
  dns-tester:
    build: .
    ports:
      - "8000:8000"
    restart: unless-stopped
```

One service, one port mapping, automatic restarts unless explicitly stopped. Build and run with:

```bash
docker-compose up --build
```

## Environment Variables

Cache tuning is the only operational configuration surface:

| Variable | Default | Meaning |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | Maximum live cache entries. Set to `0` to disable caching. |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | Upper bound for cached TTL seconds. |

Set them in the Compose file if you need non-default values:

```yaml
services:
  dns-tester:
    build: .
    ports:
      - "8000:8000"
    restart: unless-stopped
    environment:
      EZDNS_API_CACHE_SIZE: "1024"
      EZDNS_API_CACHE_MAX_TTL: "120"
```

## Reverse Proxy for DoH Clients

Standard DoH clients expect HTTPS. Place the app behind a reverse proxy that terminates TLS, for example nginx:

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

`/dns-query` accepts both GET (base64url `dns=` parameter) and POST (`Content-Type: application/dns-message`). See [API Reference](api-reference.md) for full details.

## Health Checks

There is no dedicated health endpoint. Treat `GET /api/help` or `GET /api/servers` as a cheap liveness probe — both return immediately without performing DNS queries.
