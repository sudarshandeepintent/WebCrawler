from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from crawler.config import settings
from crawler.models.schemas import CacheStatsResponse, PageMetadata

logger = logging.getLogger(__name__)


def _url_key(url: str) -> str:
    return settings.cache_prefix + hashlib.sha256(url.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _MemEntry:
    __slots__ = ("data", "expires_at", "cached_at")

    def __init__(self, data: str, ttl: int) -> None:
        self.data = data
        self.cached_at = _now_iso()
        self.expires_at = time.monotonic() + ttl


class MemoryCache:
    def __init__(self, ttl: int | None = None, max_size: int | None = None) -> None:
        self._ttl = ttl if ttl is not None else settings.cache_ttl
        self._max = max_size if max_size is not None else settings.cache_max
        self._store: OrderedDict[str, _MemEntry] = OrderedDict()
        self._lock = threading.Lock()

    def _sweep(self) -> None:
        now = time.monotonic()
        dead = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in dead:
            del self._store[k]

    def _trim(self) -> None:
        while len(self._store) >= self._max:
            self._store.popitem(last=False)

    def get(self, url: str) -> Optional[PageMetadata]:
        key = _url_key(url)
        with self._lock:
            ent = self._store.get(key)
            if ent is None:
                return None
            if ent.expires_at <= time.monotonic():
                del self._store[key]
                return None
            self._store.move_to_end(key)
            meta = PageMetadata.model_validate_json(ent.data)
            meta.from_cache = True
            meta.cached_at = ent.cached_at
            return meta

    def set(self, url: str, meta: PageMetadata) -> None:
        key = _url_key(url)
        with self._lock:
            self._sweep()
            self._trim()
            self._store[key] = _MemEntry(meta.model_dump_json(), self._ttl)
            self._store.move_to_end(key)

    def delete(self, url: str) -> None:
        with self._lock:
            self._store.pop(_url_key(url), None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> CacheStatsResponse:
        with self._lock:
            self._sweep()
            return CacheStatsResponse(
                backend="memory",
                entries=len(self._store),
                ttl_seconds=self._ttl,
                max_size=self._max,
            )


class RedisCache:
    def __init__(self, redis_url: str, ttl: int | None = None) -> None:
        import redis

        self._ttl = ttl if ttl is not None else settings.cache_ttl
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()
        logger.info("redis cache ok %s", redis_url)

    def get(self, url: str) -> Optional[PageMetadata]:
        raw = self._client.get(_url_key(url))
        if raw is None:
            return None
        payload = json.loads(raw)
        meta = PageMetadata.model_validate(payload["meta"])
        meta.from_cache = True
        meta.cached_at = payload.get("cached_at")
        return meta

    def set(self, url: str, meta: PageMetadata) -> None:
        payload = json.dumps({"meta": meta.model_dump(), "cached_at": _now_iso()})
        self._client.setex(_url_key(url), self._ttl, payload)

    def delete(self, url: str) -> None:
        self._client.delete(_url_key(url))

    def clear(self) -> None:
        pat = settings.cache_prefix + "*"
        keys = self._client.keys(pat)
        if keys:
            self._client.delete(*keys)

    def stats(self) -> CacheStatsResponse:
        pat = settings.cache_prefix + "*"
        n = len(self._client.keys(pat))
        return CacheStatsResponse(backend="redis", entries=n, ttl_seconds=self._ttl, max_size=None)


def _make_cache() -> MemoryCache | RedisCache:
    if settings.redis_url:
        try:
            return RedisCache(settings.redis_url)
        except Exception as e:
            logger.warning("redis failed (%s), using memory", e)
    return MemoryCache()


cache: MemoryCache | RedisCache = _make_cache()
