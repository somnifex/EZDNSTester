# DNS 传输


`dns_tester.py` 提供四个入口，分别对应支持的传输方式。四个函数共用同一组成功/错误结构，供 `app.py` 统一调用。

## 统一结果结构

成功：

```python
{
  "status": "success",
  "latency_ms": 12.34,        # 按 rdtype 累计的延迟，保留 2 位小数
  "answers": ["[A] 1.2.3.4"], # 可读格式
  "server": <原样回显>,
  "_records": [ {"type": "A", "value": "1.2.3.4", "ttl": 60}, ... ],
  "_min_ttl": 60              # 可选
}
```

错误：

```python
{"status": "error", "error": str(exc), "server": <原样回显>}
```

前缀为 `_` 的字段属于内部，`app._public_result` 会在返回给 HTTP 客户端前去除。

## 记录类型

`RECORD_TYPES` 将常用名称映射到 rdtype 列表：

| 名称 | 展开为 |
| --- | --- |
| `A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS`、`SOA` | 单个 rdtype |
| `BOTH` | `A`、`AAAA` |
| `ALL` | `A`、`AAAA`、`CNAME`、`MX`、`TXT`、`NS` |

未知名称退回 `A`。每次调用会对每个 rdtype 独立发起查询并累加延迟。

## 本地解析 —— `test_local`

```python
test_local(domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

使用 `dns.resolver.Resolver()`，设 `resolver.timeout = resolver.lifetime = timeout`。单个 rdtype 抛出 `NoAnswer` 或 `NXDOMAIN` 会被静默跳过，其他异常变为错误结果。

## UDP —— `test_udp`

```python
test_udp(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

通过 `_parse_dns_endpoint(..., default_port=53)` 解析 `server_ip`，随后调用 `dns.query.udp(query, host, port=port, timeout=timeout)`。

## DNS over TLS —— `test_dot`

```python
test_dot(server_ip: str, domain: str, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

构造一个关闭证书校验（`check_hostname = False`、`verify_mode = CERT_NONE`）的 SSL 上下文，然后调用 `dns.query.tls(query, host, port=port, timeout=timeout, ssl_context=context)`。默认端口 `853`。

## DNS over HTTPS —— `test_doh`

```python
async test_doh(url: str, domain: str, proxy: Optional[str] = None, record_type: str = "ALL", timeout: float = 5.0) -> dict
```

打开 `httpx.AsyncClient(verify=False, timeout=timeout)`（提供 `proxy` 时附带 `proxy=`）。对每个 rdtype 将 DNS 查询序列化为 wire 格式后 POST 到 `url`，请求头：

```
Content-Type: application/dns-message
Accept: application/dns-message
```

`response.raise_for_status()` 会把 HTTP 错误转化为传输层的错误结果。

## 端点解析 —— `_parse_dns_endpoint`

`_parse_dns_endpoint(server: str, default_port: int) -> tuple[str, int]` 接受：

- `host`：使用默认端口
- `host:port`
- `[IPv6]` 或 `[IPv6]:port`
- 含多个冒号的纯 IPv6 字面量（通过 `ipaddress.IPv6Address` 校验）

出错时给出明确文案：

- `DNS server cannot be empty`
- `Invalid IPv6 server format. Use [IPv6] or [IPv6]:port.`
- `Invalid port in server '{server}'`
- `Invalid server format. Use host, host:port, or [IPv6]:port.`
- `Port must be between 1 and 65535: {port}`

## 安全提示

`test_dot` 与 `test_doh` 均关闭 TLS 证书校验。这是刻意为之 —— 此工具用于对任意 DNS 服务器（包括自签名证书）进行行为诊断。请勿将这些辅助函数原样用于通用的安全 DNS 客户端。
