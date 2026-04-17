# 部署


EZDNSTester 是单进程 FastAPI 应用，可直接以 Python 运行，也可容器化部署。

## 直接用 Python

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

`requirements.txt` 声明了：

```
fastapi
uvicorn
dnspython
httpx[http2,socks]
jinja2
python-multipart
```

所有依赖均未锁定版本，版本固定由部署方决定。

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

镜像会把整个仓库复制到 `/app`，因此 `templates/`、`img/` 和 Python 模块在运行时均可用。

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

单服务、单端口映射、除非被显式停止否则自动重启。构建并运行：

```bash
docker-compose up --build
```

## 环境变量

唯一的运维可调参数是缓存：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | 活跃缓存条目数上限。设为 `0` 可完全禁用缓存。 |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | 缓存 TTL 秒数上限。 |

如需非默认值，可在 Compose 文件中配置：

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

## 面向 DoH 客户端的反向代理

标准 DoH 客户端期望 HTTPS。可在应用前放置一个卸载 TLS 的反向代理，例如 nginx：

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

`/dns-query` 同时接受 GET（`dns=` 为 base64url）与 POST（`Content-Type: application/dns-message`）。详见 [API 参考](api-reference.md)。

## 健康检查

项目没有专门的健康检查端点。`GET /api/help` 或 `GET /api/servers` 可作为轻量的存活探针，两者都能立即返回，不会发起 DNS 查询。
