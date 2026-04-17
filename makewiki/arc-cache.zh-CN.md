# ARC 缓存


EZDNSTester 内置了一个进程内的自适应替换缓存，专为 DNS 结果调优。实现位于 `arc_cache.py` 的 `AdaptiveReplacementTTLCache`，`app.py` 通过模块级单例 `API_RESULT_CACHE` 使用。

## 设计

缓存使用四个 OrderedDict：

| 列表 | 含义 | 存储 |
| --- | --- | --- |
| `T1` | 近期访问一次 | 带 TTL 的活跃条目 |
| `T2` | 至少访问两次 | 带 TTL 的活跃条目 |
| `B1` | 从 T1 淘汰的影子 | 仅键 |
| `B2` | 从 T2 淘汰的影子 | 仅键 |

浮点数 `target_t1` 表示期望的 T1 大小：

- B1 命中：`target_t1 += max(1, |B2| / max(1, |B1|))`，偏向“最近使用”。
- B2 命中：`target_t1 -= max(1, |B1| / max(1, |B2|))`，偏向“最常使用”。
- `target_t1` 被限制在 `[0, capacity]`。

## TTL 处理

每个条目是 `_CacheItem(value, expires_at)`，其中 `expires_at = time.monotonic() + ttl_seconds`。`get`、`put`、`stats` 都会先调用 `_prune_expired`，遍历 `T1` 与 `T2`，删除 `expires_at` 已过的条目。

以下情况会完全跳过缓存：

- `capacity == 0`
- `ttl_seconds <= 0`

## 线程安全

所有改动都在 `threading.RLock` 下进行，可安全地在 FastAPI 异步请求处理器与任何后台任务之间共享。

## 在 `app.py` 中的使用

`API_RESULT_CACHE = AdaptiveReplacementTTLCache(API_CACHE_SIZE)` 在模块导入时创建一次。缓存键为 `(server_type, server, domain, record_type, proxy)`，其中字符串字段都经过规范化（strip/lower/domain 去尾点）。

当缓存未命中且结果可缓存（`status == "success"`、`_records` 非空、`min_ttl > 0`）时，`_dispatch_test` 会深拷贝结果、写入 `_cached_at` 时间戳，并调用 `API_RESULT_CACHE.put(key, entry, min(min_ttl, EZDNS_API_CACHE_MAX_TTL))`。

后续带 `cache=true` 的请求，若满足以下条件则复用该条目：

- 经过清理后仍存在于 T1/T2
- 年龄（`now - _cached_at`）小于本次请求窗口，窗口为 `min(min_ttl, _effective_cache_ttl(cache_max_ttl))`

## 配置

| 环境变量 | 默认 | 作用 |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | 活跃条目数上限。`0` 完全禁用缓存。 |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | 全局 TTL 秒数上限。 |

每次请求可控的字段：

| 字段 | 作用 |
| --- | --- |
| `cache=true` | 本次请求启用缓存 |
| `cache_max_ttl=N` | 把本次请求的 TTL 限制在 `min(N, EZDNS_API_CACHE_MAX_TTL)` |

`/api/test`、`/api/query`、`/dns-query` 均支持这两项。

## 响应附加信息

启用缓存后，响应体会额外包含：

- `cached`：本次响应是否命中缓存
- `cache_ttl`：本次响应使用的 TTL 窗口
- `cache_max_ttl`：`EZDNS_API_CACHE_MAX_TTL` 的有效取值（可被请求值收窄）
- `cache_expires_in`：本次请求视角下缓存还剩多少秒

对于 `/dns-query`，同样信息以响应头 `X-Cache`、`X-Cache-TTL`、`X-Cache-Expires-In` 暴露。

## 查看运行状态

`GET /api/cache` 同时返回配置与 `AdaptiveReplacementTTLCache.stats()` 结果：

```json
{
  "enabled": true,
  "policy": "ARC",
  "default_request_cache": false,
  "config": { "capacity": 512, "max_ttl": 300, "env": { "size": "EZDNS_API_CACHE_SIZE", "max_ttl": "EZDNS_API_CACHE_MAX_TTL" } },
  "stats": {
    "capacity": 512,
    "live_entries": 0,
    "recent_entries": 0,
    "frequent_entries": 0,
    "recent_ghosts": 0,
    "frequent_ghosts": 0,
    "target_recent_size": 0.0
  }
}
```

`live_entries = recent_entries + frequent_entries`（清理后的值）。`target_recent_size` 是当前的 `target_t1`，保留两位小数。
