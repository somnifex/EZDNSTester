# DNS Resolution Tester

A web-based tool to test DNS resolution across different protocols (UDP 53, DoH, DoT) and servers.

## Features

- **Multi-Protocol Support**: Test DNS resolution using UDP, DNS over HTTPS (DoH), and DNS over TLS (DoT).
- **Multi-Server Testing**: Run concurrent tests against multiple DNS servers.
- **Proxy Support**: Optional HTTP/HTTPS proxy support for DoH requests.
- **Web Interface**: Clean and responsive UI built with Vue.js and Tailwind CSS.
- **Docker Ready**: Easily deployable using Docker and Docker Compose.

## Prerequisites

- Python 3.9+
- Docker (optional)

## Installation & Usage

### Local Development

1.  **Clone the repository**
2.  **Install dependencies** (using `uv` or `pip`):
    ```bash
    uv venv
    uv pip install -r requirements.txt
    ```
3.  **Run the application**:
    ```bash
    uv run uvicorn app:app --host 0.0.0.0 --port 8000
    ```
4.  Open [http://localhost:8000](http://localhost:8000) in your browser.

### Docker Deployment

1.  **Build and run using Docker Compose**:
    ```bash
    docker-compose up --build
    ```
2.  Open [http://localhost:8000](http://localhost:8000) in your browser.

## Project Structure

- `app.py`: FastAPI backend application.
- `dns_tester.py`: Core DNS testing logic.
- `templates/index.html`: Frontend Web UI.
- `Dockerfile` & `docker-compose.yml`: Docker configuration.

## License

MIT
