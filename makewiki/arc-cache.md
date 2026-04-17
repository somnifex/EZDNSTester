# ARC Cache


EZDNSTester ships with an in-process Adaptive Replacement Cache tuned for DNS results. The implementation lives in `arc_cache.py` as `AdaptiveReplacementTTLCache`, and `app.py` exposes it through the module-level singleton `API_RESULT_CACHE`.

## Design

The cache keeps four OrderedDicts:

| List | Meaning | Holds |
| --- | --- | --- |
| `T1` | Recently referenced once | Live entries with TTL |
| `T2` | Referenced at least twice | Live entries with TTL |
| `B1` | Ghosts evicted from T1 | Keys only |
| `B2` | Ghosts evicted from T2 | Keys only |

A floating-point `target_t1` sets the desired T1 size:

- A B1 hit increases `target_t1` by `max(1, |B2| / max(1, |B1|))` — lean toward recency.
- A B2 hit decreases `target_t1` by `max(1, |B1| / max(1, |B2|))` — lean toward frequency.
- `target_t1` is clamped to `[0, capacity]`.

## TTL Handling

Each entry is a `_CacheItem(value, expires_at)` where `expires_at = time.monotonic() + ttl_seconds`. Every public method (`get`, `put`, `stats`) first calls `_prune_expired`, which walks both `T1` and `T2` and deletes items whose `expires_at` is in the past.

Any of the following skip the cache entirely:

- `capacity == 0`
- `ttl_seconds <= 0`

## Thread Safety

All mutations acquire a `threading.RLock`, so the cache is safe to share between the async FastAPI request handlers and any background tasks.

## Usage From `app.py`

`API_RESULT_CACHE = AdaptiveReplacementTTLCache(API_CACHE_SIZE)` is created once at import. The cache key is `(server_type, server, domain, record_type, proxy)`, with string fields normalized (strip/lower/domain-rstrip).

On a cache miss that produces a cacheable result (`status == "success"`, non-empty `_records`, `min_ttl > 0`), `_dispatch_test` stores a deep copy along with a `_cached_at` timestamp and calls `API_RESULT_CACHE.put(key, entry, min(min_ttl, EZDNS_API_CACHE_MAX_TTL))`.

On a subsequent request with `cache=true`, the entry is returned if:

- it still exists in T1/T2 after pruning
- its age (`now - _cached_at`) is smaller than the per-request window, where the window is `min(min_ttl, _effective_cache_ttl(cache_max_ttl))`

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `EZDNS_API_CACHE_SIZE` | `512` | Maximum live entries. `0` disables the cache. |
| `EZDNS_API_CACHE_MAX_TTL` | `300` | Global upper bound for cached TTL seconds. |

Per-request controls:

| Field | Effect |
| --- | --- |
| `cache=true` | Opt in for this request |
| `cache_max_ttl=N` | Cap this request's effective TTL at `min(N, EZDNS_API_CACHE_MAX_TTL)` |

Both are supported on `/api/test`, `/api/query`, and `/dns-query`.

## Response Annotations

When caching is in play, responses include additional fields:

- `cached` — whether this specific response came from the cache
- `cache_ttl` — the effective TTL window used
- `cache_max_ttl` — resolved value of `EZDNS_API_CACHE_MAX_TTL` (optionally narrowed by the request)
- `cache_expires_in` — remaining seconds before the cached entry is considered stale for this request

For `/dns-query`, the same information is surfaced as HTTP headers `X-Cache`, `X-Cache-TTL`, and `X-Cache-Expires-In`.

## Inspecting Live State

`GET /api/cache` returns both the configuration and the output of `AdaptiveReplacementTTLCache.stats()`:

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

`live_entries = recent_entries + frequent_entries` (after pruning). `target_recent_size` is the current `target_t1`, rounded to 2 decimals.
