# EZDNSTester

[English](../README.md) | [简体中文](README_zh-CN.md)

EZDNSTester 是一个基于 FastAPI 的 DNS 对比工具，用来查看不同解析器对同一条查询会返回什么结果。它支持本地系统解析、传统 UDP DNS、DNS over TLS、DNS over HTTPS，同时提供浏览器界面和适合脚本调用的 API。

## 能做什么

- 一次对比多个 DNS 服务器
- 通过 HTTP 或 HTTPS 代理测试 DoH
- 暴露一个兼容 DoH 的转发端点
- 返回 JSON、简洁文本或格式化文本结果
- 可本地运行，也可直接用 Docker

## 快速开始

### 本地运行

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`。

### Docker

```bash
docker-compose up --build
```

## 服务器写法

当接口需要你指定 DNS 服务器时，使用 `type://server`。

| 类型      | 含义                      | 示例                                                                       |
| ------- | ----------------------- | ------------------------------------------------------------------------ |
| `local` | 系统默认解析器                 | `local`、`local://local`                                                  |
| `udp`   | UDP DNS，默认端口 `53`       | `udp://8.8.8.8`、`udp://8.8.8.8:8053`、`udp://[2606:4700:4700::1111]:8053` |
| `dot`   | DNS over TLS，默认端口 `853` | `dot://1.1.1.1`、`dot://dns.example.com:8853`                             |
| `doh`   | DNS over HTTPS          | `doh://https://dns.google/dns-query`                                     |

如果不写前缀，默认按 UDP 处理。

## 常用接口

### `POST /api/test`

这是 Web 界面内部使用的单服务器测试接口。

```bash
curl -X POST "http://localhost:8000/api/test" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "udp",
    "server": "8.8.8.8:8053",
    "domain": "google.com",
    "record_type": "A"
  }'
```

### `GET /api/query`

适合命令行、脚本或批量对比场景。

```bash
curl "http://localhost:8000/api/query?domain=google.com"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8:8053&type=AAAA"
curl "http://localhost:8000/api/query?domain=google.com&server=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"
curl "http://localhost:8000/api/query?domain=google.com&format=simple"
curl "http://localhost:8000/api/query?domain=google.com&format=text"
```

如果你更习惯发 JSON，也可以用 `POST`：

```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "google.com",
    "servers": [
      "udp://8.8.8.8:8053",
      "doh://https://dns.google/dns-query"
    ],
    "record_type": "A",
    "proxy": null
  }'
```

常用参数：

| 参数       | 说明                                                         |
| -------- | ---------------------------------------------------------- |
| `domain` | 要解析的域名                                                     |
| `server` | 一个或多个上游服务器，格式为 `type://server`                             |
| `type`   | 记录类型：`A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS`、`SOA`、`BOTH`、`ALL` |
| `proxy`  | DoH 请求使用的代理地址                                              |
| `format` | 输出格式：`json`、`simple`、`text`                                |

### `GET /dns-query` 和 `POST /dns-query`

EZDNSTester 也可以作为兼容 DoH 的上游使用。实际部署时，通常会放在提供 HTTPS 的反向代理后面，然后把 `/dns-query` 暴露给客户端。

```bash
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8:8053"
```

```bash
curl -X POST "http://localhost:8000/dns-query" \
  -H "Content-Type: application/dns-message" \
  --data-binary @query.bin
```

可选参数：

| 参数         | 说明                              |
| ---------- | ------------------------------- |
| `dns`      | `GET` 请求使用的 Base64url 编码 DNS 消息 |
| `upstream` | 指定上游解析器，支持自定义 UDP 或 DoT 端口      |
| `proxy`    | DoH 上游请求使用的代理地址                 |

### `GET /api/servers`

返回内置的服务器列表，Web 界面和默认的 CLI 查询都会用到它。

### `GET /api/help`

返回一份简短的接口说明和示例，适合程序自己读取。

## 反向代理说明

如果你准备把 `/dns-query` 提供给标准 DoH 客户端使用，记得把应用放在提供 HTTPS 的反向代理后面。

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 项目结构

- `app.py`：FastAPI 入口和 API 路由
- `dns_tester.py`：UDP、DoT、DoH 和本地解析的测试逻辑
- `templates/index.html`：浏览器界面
- `Dockerfile` 与 `docker-compose.yml`：容器相关配置

## 许可证

本项目采用 GNU General Public License v3.0。完整内容见 [LICENSE](../LICENSE)。
