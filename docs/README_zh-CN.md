# EZDNSTester

[English](../README.md) | [简体中文](README_zh-CN.md)

一款基于 Web 的 DNS 解析测试工具，支持多种协议（UDP 53、DoH、DoT）和服务器测试，并提供完整的 DoH 服务器模式和命令行查询 API。

## 功能特性

- **多协议支持**：支持 UDP、DNS over HTTPS (DoH) 和 DNS over TLS (DoT) 协议测试
- **多服务器测试**：同时对多个 DNS 服务器进行并发测试
- **代理支持**：DoH 请求支持 HTTP/HTTPS 代理
- **Web 界面**：基于 Vue.js 和 Tailwind CSS 构建的简洁响应式界面
- **DoH 服务器模式**：可作为符合 RFC 8484 标准的 DoH 服务器，支持配置上游服务器
- **命令行查询 API**：通过 API 查询多个 DNS 服务器，支持格式化输出，便于命令行使用
- **Docker 部署**：支持 Docker 和 Docker Compose 快速部署

## 环境要求

- Python 3.9+
- Docker（可选）

## 安装与使用

### 本地开发

1. **克隆仓库**
2. **安装依赖**（使用 `uv` 或 `pip`）：
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```
3. **运行应用**：
   ```bash
   uv run uvicorn app:app --host 0.0.0.0 --port 8000
   ```
4. 在浏览器中打开 [http://localhost:8000](http://localhost:8000)

### Docker 部署

1. **使用 Docker Compose 构建并运行**：
   ```bash
   docker-compose up --build
   ```
2. 在浏览器中打开 [http://localhost:8000](http://localhost:8000)

## API 接口文档

### 1. DoH 服务器模式 (`/dns-query`)

EZDNSTester 可以作为符合 RFC 8484 标准的 DoH (DNS over HTTPS) 服务器。您可以将其作为客户端的上游 DoH 服务器使用（需要反向代理提供 TLS 支持）。

#### GET 方法

```bash
# 基本 DoH 查询（Base64url 编码的 DNS 消息）
curl "http://localhost:8000/dns-query?dns=AAABAAABAAAAAAAAB2V4YW1wbGUDY29tAAABAAE"

# 使用自定义上游服务器
curl "http://localhost:8000/dns-query?dns=...&upstream=udp://8.8.8.8"

# 使用 DoH 上游和代理
curl "http://localhost:8000/dns-query?dns=...&upstream=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"
```

#### POST 方法

```bash
curl -X POST "http://localhost:8000/dns-query" \
     -H "Content-Type: application/dns-message" \
     --data-binary @query.bin
```

#### 参数说明

| 参数       | 说明                                    |
| ---------- | --------------------------------------- |
| `dns`      | （仅 GET）Base64url 编码的 DNS 查询     |
| `upstream` | 上游 DNS 服务器（格式：`type://server`）|
| `proxy`    | DoH 上游请求的代理服务器                |

### 2. 命令行查询 API (`/api/query`)

查询多个 DNS 服务器并获取格式化结果，非常适合命令行使用。

#### GET 方法

```bash
# 使用默认服务器查询
curl "http://localhost:8000/api/query?domain=google.com"

# 查询指定服务器
curl "http://localhost:8000/api/query?domain=google.com&server=udp://8.8.8.8&server=doh://https://dns.google/dns-query"

# 查询指定记录类型
curl "http://localhost:8000/api/query?domain=google.com&type=AAAA"

# DoH 查询使用代理
curl "http://localhost:8000/api/query?domain=google.com&server=doh://https://dns.google/dns-query&proxy=http://127.0.0.1:7890"

# 简单文本输出（适合命令行）
curl "http://localhost:8000/api/query?domain=google.com&format=simple"

# 格式化文本输出
curl "http://localhost:8000/api/query?domain=google.com&format=text"
```

#### POST 方法

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

#### 参数说明

| 参数       | 说明                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------- |
| `domain`   | 要查询的域名（必填）                                                                     |
| `server`   | DNS 服务器，格式为 `type://server`（可指定多个）                                        |
| `type`     | 记录类型：`A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS`、`SOA`、`BOTH`、`ALL`                  |
| `proxy`    | DoH 请求的代理服务器                                                                     |
| `format`   | 输出格式：`json`（默认）、`text`、`simple`                                               |

#### 输出格式

**JSON（默认）**

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

**Simple（命令行友好）**

```
DNS Query Results for: google.com
Record Type: A
==================================================

✓ udp://8.8.8.8 (udp)
  Latency: 45.23 ms
  → [A] 142.250.190.78

==================================================
```

### 3. 获取默认服务器列表 (`/api/servers`)

```bash
curl "http://localhost:8000/api/servers"
```

### 4. API 帮助 (`/api/help`)

```bash
curl "http://localhost:8000/api/help"
```

## 服务器地址格式

指定 DNS 服务器时，请使用 `type://server` 格式：

| 类型    | 说明                  | 示例                                   |
| ------- | --------------------- | -------------------------------------- |
| `udp`   | UDP DNS（端口 53）    | `udp://8.8.8.8`                        |
| `dot`   | DNS over TLS（端口 853）| `dot://1.1.1.1`                      |
| `doh`   | DNS over HTTPS        | `doh://https://dns.google/dns-query`   |

如果未指定类型前缀，默认使用 `udp`。

## 作为 DoH 服务器使用

将 EZDNSTester 作为 DoH 服务器供客户端使用：

1. 部署在提供 TLS 的反向代理（nginx、Caddy）后面
2. 配置反向代理转发 `/dns-query` 请求
3. 在 DNS 客户端中使用该 URL 作为 DoH 上游

nginx 配置示例：

```nginx
location /dns-query {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 项目结构

- `app.py`：FastAPI 后端应用，包含 DoH 服务器和命令行 API
- `dns_tester.py`：核心 DNS 测试逻辑
- `templates/index.html`：前端 Web 界面
- `Dockerfile` & `docker-compose.yml`：Docker 配置文件

## 开源协议

MIT
