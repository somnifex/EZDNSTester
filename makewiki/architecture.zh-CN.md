# 架构


EZDNSTester 的结构故意保持简单：单个 FastAPI 进程将工作委托给一个传输层与一个内存缓存。

## 分层

```
HTTP 客户端
     │
     ▼
┌───────────────────────────┐
│ HTTP API 层 (app.py)      │
│  - 请求/响应模型          │
│  - parse_server_string    │
│  - _dispatch_test         │
│  - /dns-query 转发        │
└─────────────┬─────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ dns_tester.py│   │ arc_cache.py │
│ 本地/UDP/    │   │ 带 TTL 的    │
│ DoT/DoH      │   │ ARC          │
└──────────────┘   └──────────────┘
```

## HTTP API 层 —— `app.py`

FastAPI 应用以 `title="EZDNSTester API"`、`version="1.1.0"` 构造。静态图片挂载在 `/img`，根路径返回 `templates/index.html`。

关键内部组件：

- `TestRequest` / `QueryRequest`：Pydantic 请求模型
- `DEFAULT_SERVERS`：十二个默认解析器预设，调用方未指定时使用
- `parse_server_string`：把 `type://server` 字符串解析为 `{type, server}`
- `_dispatch_test`：解析单次查询的唯一入口，先查 ARC 缓存，再分派到 `dns_tester.test_local/udp/dot/test_doh`
- `_query_default_servers`：顺序遍历 `DEFAULT_SERVERS`，直到某个返回 `status == "success"` 且含答案
- `forward_dns_query`：为 `/dns-query` 做 wire 格式翻译
- `_perform_query`：通过 `asyncio.gather` 扇出执行 `/api/query`

## DNS 传输助手 —— `dns_tester.py`

四个入口共用同一结果结构：

| 函数 | 传输方式 | 使用库 |
| --- | --- | --- |
| `test_local` | 系统解析器 | `dns.resolver.Resolver` |
| `test_udp` | UDP DNS，默认端口 53 | `dns.query.udp` |
| `test_dot` | DNS over TLS，默认端口 853 | `dns.query.tls`（关闭证书校验） |
| `test_doh` | DNS over HTTPS（异步） | `httpx.AsyncClient`（`verify=False`，可选代理） |

`_parse_dns_endpoint` 统一处理 `host`、`host:port` 与 `[IPv6]:port` 三种写法，并强制 `1 ≤ port ≤ 65535`。

`RECORD_TYPES` 把常用名称（`A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS`、`SOA`、`BOTH`、`ALL`）映射到 `dns.rdatatype` 列表，每次调用会为每个 rdtype 发起一次查询并累加延迟。

## ARC 结果缓存 —— `arc_cache.py`

`AdaptiveReplacementTTLCache` 是带 TTL 的线程安全自适应替换缓存：

- `T1`/`T2`：近期与高频活跃条目，存放 `_CacheItem(value, expires_at)`
- `B1`/`B2`：仅保留键的影子列表
- `target_t1`：T1 与 T2 的动态分界线，B1 命中时增大，B2 命中时减小
- `capacity == 0` 会完全禁用缓存

每次 `get`、`put`、`stats` 都会用 `time.monotonic()` 清理过期条目。

## 请求生命周期

带 `cache=true` 进入 `_dispatch_test` 的请求流程：

1. 构造缓存键 `(server_type, server, domain, record_type, proxy)`。
2. 若 `API_RESULT_CACHE.get(key)` 命中且条目年龄小于本次请求窗口，则返回深拷贝并附加 `cached=true` 与 `X-Cache=HIT`。
3. 否则调用 `dns_tester`，在结果成功且 `min_ttl > 0` 时调用 `API_RESULT_CACHE.put(key, value, min(min_ttl, EZDNS_API_CACHE_MAX_TTL))`。
4. 给返回值添加 `cache_ttl`、`cache_max_ttl`、`cache_expires_in` 字段。

## 部署形态

Dockerfile 以 `python:3.10-slim` 为基础镜像，启动命令为 `uvicorn app:app --host 0.0.0.0 --port 8000`。Compose 文件只定义单个 `dns-tester` 服务，`restart: unless-stopped`，端口映射 `8000:8000`。详见 [部署](deployment.md)。
