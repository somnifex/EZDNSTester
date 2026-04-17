# API 参考


所有端点均定义在 `app.py`。未特别说明时响应为 JSON。

## `GET /`

返回浏览器 UI（`templates/index.html`）。

## `POST /api/test`

Web UI 使用的单服务器测试端点。

请求体 (`TestRequest`)：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `type` | string | — | `local`、`udp`、`dot` 或 `doh` |
| `server` | string | — | 主机、URL 或 `local` |
| `domain` | string | — | 待查询域名 |
| `proxy` | string? | `null` | DoH 上游的代理 URL |
| `record_type` | string? | `A` | `A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS`、`SOA`、`BOTH`、`ALL` |
| `cache` | bool | `false` | 本次请求是否启用 ARC 缓存 |
| `cache_max_ttl` | int? (>=1) | `null` | 本次请求的缓存 TTL 上限（秒） |

`server` 中尾部的 `# comment` 会被去除。非法输入会以底层 `ValueError` 消息抛出 `HTTP 400`（例如 `Server cannot be empty`、`Invalid test type: {t}`）。

```bash
curl -X POST "http://localhost:8000/api/test" \
  -H "Content-Type: application/json" \
  -d '{"type":"udp","server":"8.8.8.8:8053","domain":"google.com","record_type":"A","cache":true,"cache_max_ttl":120}'
```

## `GET /api/query` 与 `POST /api/query`

对一台或多台服务器进行扇出查询。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `domain` | string | 必填 |
| `server`（GET）/ `servers`（POST） | list[string] | 可重复或数组；缺省时取 `DEFAULT_SERVERS` 前五个预设 |
| `type`（`record_type` 别名） | string | 默认 `A` |
| `proxy` | string? | DoH 代理 URL |
| `format` | string | `json`（默认）、`simple`、`text` |
| `cache` | bool | 默认 `false` |
| `cache_max_ttl` | int? (>=1) | 可选 TTL 上限 |

JSON 响应结构：

```json
{
  "domain": "google.com",
  "record_type": "A",
  "results": [
    { "server": "...", "type": "udp", "status": "success", "latency_ms": 12.34, "answers": ["[A] 142.250.0.0"], "cached": false }
  ]
}
```

`format=simple` 返回紧凑纯文本；`format=text` 返回带框的 ASCII 报告。

```bash
curl "http://localhost:8000/api/query?domain=google.com"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
curl "http://localhost:8000/api/query?domain=google.com&cache=true&cache_max_ttl=60"
```

## `GET /dns-query` 与 `POST /dns-query`

兼容 DoH 的转发端点（RFC 8484）。

| 参数 | 适用方法 | 说明 |
| --- | --- | --- |
| `dns` | GET | base64url 编码的 DNS wire 消息 |
| `upstream` | GET、POST | `type://server`；UDP/DoT 支持 `host:port` |
| `proxy` | GET、POST | DoH 上游代理 |
| `cache` | GET、POST | 启用 ARC 缓存 |
| `cache_max_ttl` | GET、POST | 本次请求 TTL 上限 |

`POST` 要求 `Content-Type: application/dns-message`（否则 `HTTP 415`）。未指定 `upstream` 时会退回到 `_query_default_servers`，按顺序试探 12 个预设；都失败则返回 SERVFAIL。

响应头：

| 头 | 含义 |
| --- | --- |
| `X-Cache` | `HIT`、`MISS`、`BYPASS` 或 `ERROR` |
| `X-Cache-TTL` | 本次响应使用的 TTL 窗口 |
| `X-Cache-Expires-In` | 距离缓存过期的剩余秒数 |

```bash
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8:8053"
curl -X POST "http://localhost:8000/dns-query" -H "Content-Type: application/dns-message" --data-binary @query.bin
```

## `GET /api/servers`

返回内置预设：

```json
{
  "servers": [{ "name": "Local", "server": "local", "type": "local" }, "..."],
  "format_hint": "Use 'type://server' when specifying servers. UDP and DoT also accept host:port, ..."
}
```

## `GET /api/cache`

返回 ARC 缓存的配置与实时统计：

```json
{
  "enabled": true,
  "policy": "ARC",
  "default_request_cache": false,
  "config": {
    "capacity": 512,
    "max_ttl": 300,
    "env": { "size": "EZDNS_API_CACHE_SIZE", "max_ttl": "EZDNS_API_CACHE_MAX_TTL" }
  },
  "stats": { "capacity": 512, "live_entries": 0, "recent_entries": 0, "frequent_entries": 0, "recent_ghosts": 0, "frequent_ghosts": 0, "target_recent_size": 0.0 }
}
```

## `GET /api/help`

以机器可读格式返回上述全部端点的紧凑摘要，包含缓存语义与服务器字符串示例。

## 服务器字符串格式

所有接受 `server`（或 `upstream`）的端点使用 `type://server` 形式：

| 类型 | 默认端口 | 示例 |
| --- | --- | --- |
| `local` | — | `local`、`local://local` |
| `udp` | 53 | `udp://8.8.8.8`、`udp://8.8.8.8:8053`、`udp://[2606:4700:4700::1111]:8053` |
| `dot` | 853 | `dot://1.1.1.1`、`dot://dns.example.com:8853` |
| `doh` | — | `doh://https://dns.google/dns-query` |

若省略前缀则按 UDP 处理。

## 错误消息

以 `HTTP 400` 或响应体形式返回的错误文案：

- `Server cannot be empty`
- `Invalid test type: {server_type}`
- `DNS server cannot be empty`
- `Invalid IPv6 server format. Use [IPv6] or [IPv6]:port.`
- `Invalid port in server '{server}'`
- `Invalid server format. Use host, host:port, or [IPv6]:port.`
- `Port must be between 1 and 65535: {port}`
- `All upstream servers failed`（来自 `_query_default_servers`）
- `Invalid DNS query: {exc}`（DoH GET 解码失败）
