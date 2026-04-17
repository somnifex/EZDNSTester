# 快速开始


EZDNSTester 是一个运行在 `8000` 端口的 FastAPI 单进程服务。可以在本地直接运行，也可以通过容器运行。

## 本地运行

项目使用 [uv](https://docs.astral.sh/uv/) 管理环境，使用原生 `pip` 同样可以。

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

然后打开 <http://localhost:8000>。

## 使用 Docker 运行

```bash
docker-compose up --build
```

Compose 文件会构建仓库自带的 Dockerfile（`python:3.10-slim`），安装同一份 `requirements.txt`，并将容器的 `8000` 端口映射到主机。

## 依赖

`requirements.txt` 仅以名称声明直接依赖：

- `fastapi`
- `uvicorn`
- `dnspython`
- `httpx[http2,socks]`
- `jinja2`
- `python-multipart`

## 第一次查询

服务启动后，可用 CLI 风格端点快速验证：

```bash
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
```

访问 `/` 可以打开浏览器 UI —— 应用挂载了 `templates/index.html` 和 `/img` 静态目录。

## 可选配置

ARC 缓存通过环境变量进行调优。默认值已足够稳妥，通常无需修改。

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | 活跃缓存条目数上限，设为 `0` 可完全禁用缓存。 |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | 缓存 DNS 结果的 TTL 秒数上限。 |

详见 [ARC 缓存](arc-cache.md)。
