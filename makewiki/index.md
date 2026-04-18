# EZDNSTester

EZDNSTester is a small FastAPI application for comparing how different DNS resolvers answer the same query. It supports four transports (local resolver, plain UDP, DNS over TLS, DNS over HTTPS), exposes both a browser UI and a set of HTTP APIs, and includes a built-in ARC result cache so repeat queries can be served without hitting upstream servers.

## Highlights

- Compare several DNS servers in one run
- Test DoH requests through an HTTP, HTTPS, or SOCKS proxy
- Expose a DoH-compatible forwarding endpoint at `/dns-query`
- Return results as JSON, plain text, or a boxed terminal view
- Run locally with Python or as a container via `docker-compose`

## Components

| Component             | Source                             | Role                                                 |
| --------------------- | ---------------------------------- | ---------------------------------------------------- |
| HTTP API layer        | `app.py`                           | FastAPI app, request validation, cache orchestration |
| DNS transport helpers | `dns_tester.py`                    | Per-protocol query implementations                   |
| ARC result cache      | `arc_cache.py`                     | TTL-aware Adaptive Replacement Cache                 |
| Browser UI            | `templates/index.html`             | Served from `/`                                      |
| Container deployment  | `Dockerfile`, `docker-compose.yml` | Packaging                                            |

## Next Steps

- [Getting Started](getting-started.md)
- [Architecture](architecture.md)
- [API Reference](api-reference.md)
- [ARC Cache](arc-cache.md)
- [DNS Transports](dns-transports.md)
- [Deployment](deployment.md)

## License

GNU General Public License v3.0. See `LICENSE`.
