# EZDNSTester


EZDNSTester 是一个小型 FastAPI 应用，用于比较不同 DNS 解析器对同一查询的回答。它支持本地解析、明文 UDP DNS、DNS over TLS 以及 DNS over HTTPS 四种传输方式，同时提供浏览器界面与 HTTP API，并内置一个 ARC 结果缓存，可在不访问上游服务器的情况下服务重复查询。

## 功能亮点

- 一次运行对比多个 DNS 服务器
- 通过 HTTP、HTTPS 或 SOCKS 代理进行 DoH 请求
- 在 `/dns-query` 暴露兼容 DoH 的转发端点
- 结果支持 JSON、纯文本、带框终端视图
- 可直接用 Python 运行，也可通过 `docker-compose` 容器化部署

## 组成部分

| 组件 | 源文件 | 角色 |
| --- | --- | --- |
| HTTP API 层 | `app.py` | FastAPI 应用、请求校验、缓存编排 |
| DNS 传输助手 | `dns_tester.py` | 各协议的查询实现 |
| ARC 结果缓存 | `arc_cache.py` | 带 TTL 的自适应替换缓存 |
| 浏览器界面 | `templates/index.html` | 挂载在 `/` |
| 容器部署 | `Dockerfile`、`docker-compose.yml` | 打包 |

## 继续阅读

- [快速开始](getting-started.md)
- [架构](architecture.md)
- [API 参考](api-reference.md)
- [ARC 缓存](arc-cache.md)
- [DNS 传输](dns-transports.md)
- [部署](deployment.md)

## 许可

GNU General Public License v3.0，详见 `LICENSE`。
