# Getting Started


EZDNSTester runs as a single FastAPI process on port `8000`. You can run it locally or inside a container.

## Run Locally

The project uses [uv](https://docs.astral.sh/uv/) for environment management but plain `pip` works too.

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open <http://localhost:8000>.

## Run With Docker

```bash
docker-compose up --build
```

The Compose file builds the bundled Dockerfile (`python:3.10-slim`), installs the same `requirements.txt`, and maps container port `8000` to the host.

## Requirements

Direct Python dependencies, pinned by name only in `requirements.txt`:

- `fastapi`
- `uvicorn`
- `dnspython`
- `httpx[http2,socks]` — HTTP/2 and SOCKS proxy support for DoH
- `jinja2`
- `python-multipart`

## First Query

Once the server is running, try the CLI-friendly endpoint:

```bash
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
```

For the browser UI, visit `/` — the app mounts `templates/index.html` and the `/img` static directory.

## Optional Configuration

Tuning the ARC result cache is done via environment variables. Both default to safe values and do not need to be set for normal use.

| Variable | Default | Meaning |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | Maximum number of live cached query entries. `0` disables caching. |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | Upper bound, in seconds, for cached DNS results. |

See [ARC Cache](arc-cache.md) for details.
