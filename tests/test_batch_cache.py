"""
Tests for:
  - crawler.cache  (MemoryCache)
  - crawler.batch  (crawl_batch async orchestrator)
  - POST /crawl/batch  API endpoint
  - Cache integration with POST /crawl
"""
from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from crawler.cache import MemoryCache
from crawler.schemas import BatchCrawlRequest, PageMetadata, UrlStatus
from main import app

client = TestClient(app)

# ── Shared HTML fixture ───────────────────────────────────────────────────────

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Test Page</title>
  <meta name="description" content="A test page for unit testing.">
</head>
<body>
  <h1>Hello World</h1>
  <p>This is a sample page used for testing the crawler.</p>
  <a href="https://other.com/link">External</a>
</body>
</html>"""


def _make_metadata(url: str = "https://example.com") -> PageMetadata:
    return PageMetadata(
        url=url,
        final_url=url,
        status_code=200,
        title="Test Page",
        description="A test page for unit testing.",
        body_text="Hello World This is a sample page.",
        word_count=7,
        page_category="blog",
        topics=["technology"],
        topic_scores={"technology": 0.5},
    )


# ═════════════════════════════════════════════════════════════════════════════
# MemoryCache unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestMemoryCache:

    def setup_method(self):
        # Fresh cache for each test
        self.cache = MemoryCache(ttl=60, max_size=5)

    def test_miss_returns_none(self):
        assert self.cache.get("https://example.com") is None

    def test_set_then_get(self):
        meta = _make_metadata()
        self.cache.set("https://example.com", meta)
        result = self.cache.get("https://example.com")
        assert result is not None
        assert result.title == "Test Page"

    def test_from_cache_flag_set(self):
        meta = _make_metadata()
        self.cache.set("https://example.com", meta)
        result = self.cache.get("https://example.com")
        assert result.from_cache is True

    def test_cached_at_set(self):
        meta = _make_metadata()
        self.cache.set("https://example.com", meta)
        result = self.cache.get("https://example.com")
        assert result.cached_at is not None

    def test_delete(self):
        meta = _make_metadata()
        self.cache.set("https://example.com", meta)
        self.cache.delete("https://example.com")
        assert self.cache.get("https://example.com") is None

    def test_clear(self):
        for i in range(3):
            self.cache.set(f"https://example.com/{i}", _make_metadata(f"https://example.com/{i}"))
        self.cache.clear()
        assert self.cache.stats().entries == 0

    def test_ttl_expiry(self):
        short_cache = MemoryCache(ttl=1, max_size=10)
        meta = _make_metadata()
        short_cache.set("https://example.com", meta)
        time.sleep(1.1)
        assert short_cache.get("https://example.com") is None

    def test_lru_eviction(self):
        # Fill to max_size (5), then add one more — oldest should be evicted
        for i in range(5):
            self.cache.set(f"https://example.com/{i}", _make_metadata())
        self.cache.set("https://example.com/new", _make_metadata())
        # Total entries should not exceed max_size
        assert self.cache.stats().entries <= 5

    def test_stats_returns_correct_count(self):
        for i in range(3):
            self.cache.set(f"https://example.com/{i}", _make_metadata())
        stats = self.cache.stats()
        assert stats.entries == 3
        assert stats.backend == "memory"
        assert stats.ttl_seconds == 60

    def test_different_urls_stored_separately(self):
        m1 = _make_metadata("https://a.com")
        m1.title = "Page A"
        m2 = _make_metadata("https://b.com")
        m2.title = "Page B"
        self.cache.set("https://a.com", m1)
        self.cache.set("https://b.com", m2)
        assert self.cache.get("https://a.com").title == "Page A"
        assert self.cache.get("https://b.com").title == "Page B"

    def test_overwrite_same_url(self):
        m1 = _make_metadata()
        m1.title = "Old"
        self.cache.set("https://example.com", m1)
        m2 = _make_metadata()
        m2.title = "New"
        self.cache.set("https://example.com", m2)
        assert self.cache.get("https://example.com").title == "New"


# ═════════════════════════════════════════════════════════════════════════════
# Batch crawl unit tests (async, mocked)
# ═════════════════════════════════════════════════════════════════════════════

class TestBatchCrawl:

    def _mock_async_fetch(self, html=SAMPLE_HTML, status=200):
        from crawler.http_fetch import FetchResult
        result = FetchResult(
            url="https://example.com",
            final_url="https://example.com",
            status_code=status,
            html=html,
            content_type="text/html",
        )
        return AsyncMock(return_value=result)

    def test_batch_success(self):
        urls = ["https://example.com/1", "https://example.com/2"]
        from crawler.http_fetch import FetchResult
        def make_result(url, *args, **kwargs):
            return asyncio.coroutine(lambda: FetchResult(
                url=url, final_url=url, status_code=200,
                html=SAMPLE_HTML, content_type="text/html"
            ))()
        async def fake_fetch(url, **kw):
            return FetchResult(url=url, final_url=url, status_code=200,
                               html=SAMPLE_HTML, content_type="text/html")

        with patch("crawler.services.batch_service.async_fetch_page", side_effect=fake_fetch), \
             patch("crawler.services.batch_service.cache.get", return_value=None), \
             patch("crawler.services.batch_service.cache.set"):
            from crawler.batch import crawl_batch
            result = asyncio.get_event_loop().run_until_complete(
                crawl_batch(urls, concurrency=2)
            )
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.cached == 0

    def test_batch_partial_failure(self):
        from crawler.http_fetch import FetchResult
        async def fake_fetch(url, **kw):
            if "bad" in url:
                return FetchResult(url=url, final_url=url, status_code=0,
                                   html="", content_type="", error="Connection refused")
            return FetchResult(url=url, final_url=url, status_code=200,
                               html=SAMPLE_HTML, content_type="text/html")

        urls = ["https://good.com", "https://bad.com"]
        with patch("crawler.services.batch_service.async_fetch_page", side_effect=fake_fetch), \
             patch("crawler.services.batch_service.cache.get", return_value=None), \
             patch("crawler.services.batch_service.cache.set"):
            from crawler.batch import crawl_batch
            result = asyncio.get_event_loop().run_until_complete(
                crawl_batch(urls, concurrency=2)
            )
        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

    def test_batch_cache_hit(self):
        cached_meta = _make_metadata("https://cached.com")
        cached_meta.from_cache = True

        with patch("crawler.services.batch_service.cache.get", return_value=cached_meta):
            from crawler.batch import crawl_batch
            result = asyncio.get_event_loop().run_until_complete(
                crawl_batch(["https://cached.com"], concurrency=1)
            )
        assert result.cached == 1
        assert result.succeeded == 0
        assert result.results[0].status == UrlStatus.cached

    def test_batch_order_preserved(self):
        """Results must come back in the same order as the input URLs."""
        from crawler.http_fetch import FetchResult
        async def fake_fetch(url, **kw):
            await asyncio.sleep(0.01)     # simulate variable latency
            return FetchResult(url=url, final_url=url, status_code=200,
                               html=SAMPLE_HTML, content_type="text/html")

        urls = [f"https://example.com/{i}" for i in range(5)]
        with patch("crawler.services.batch_service.async_fetch_page", side_effect=fake_fetch), \
             patch("crawler.services.batch_service.cache.get", return_value=None), \
             patch("crawler.services.batch_service.cache.set"):
            from crawler.batch import crawl_batch
            result = asyncio.get_event_loop().run_until_complete(
                crawl_batch(urls, concurrency=5)
            )
        for i, item in enumerate(result.results):
            assert item.url == urls[i], f"Order mismatch at index {i}"

    def test_batch_duration_tracked(self):
        from crawler.http_fetch import FetchResult
        async def fake_fetch(url, **kw):
            return FetchResult(url=url, final_url=url, status_code=200,
                               html=SAMPLE_HTML, content_type="text/html")
        with patch("crawler.services.batch_service.async_fetch_page", side_effect=fake_fetch), \
             patch("crawler.services.batch_service.cache.get", return_value=None), \
             patch("crawler.services.batch_service.cache.set"):
            from crawler.batch import crawl_batch
            result = asyncio.get_event_loop().run_until_complete(
                crawl_batch(["https://example.com"], concurrency=1)
            )
        assert result.duration_seconds >= 0


# ═════════════════════════════════════════════════════════════════════════════
# Batch API endpoint tests
# ═════════════════════════════════════════════════════════════════════════════

class TestBatchAPI:

    def _mock_batch(self, urls, succeeded=True):
        from crawler.schemas import BatchCrawlResponse, BatchResultItem
        items = [
            BatchResultItem(
                url=url,
                status=UrlStatus.ok,
                data=_make_metadata(url),
            )
            for url in urls
        ]
        return BatchCrawlResponse(
            total=len(urls),
            succeeded=len(urls) if succeeded else 0,
            failed=0 if succeeded else len(urls),
            cached=0,
            duration_seconds=0.5,
            results=items,
        )

    def test_batch_endpoint_success(self):
        urls = ["https://example.com/1", "https://example.com/2"]
        mock_response = self._mock_batch(urls)
        with patch(
            "crawler.api.routes.crawl_batch",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            r = client.post("/crawl/batch", json={"urls": urls})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert len(data["results"]) == 2

    def test_batch_response_schema(self):
        urls = ["https://example.com"]
        mock_response = self._mock_batch(urls)
        with patch(
            "crawler.api.routes.crawl_batch",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            data = client.post("/crawl/batch", json={"urls": urls}).json()
        for field in ["total", "succeeded", "failed", "cached", "duration_seconds", "results"]:
            assert field in data, f"Missing field: {field}"
        for field in ["url", "status", "data"]:
            assert field in data["results"][0], f"Missing result field: {field}"

    def test_batch_empty_urls_rejected(self):
        r = client.post("/crawl/batch", json={"urls": []})
        assert r.status_code == 422

    def test_batch_too_many_urls_rejected(self):
        urls = [f"https://example.com/{i}" for i in range(51)]
        r = client.post("/crawl/batch", json={"urls": urls})
        assert r.status_code == 422

    def test_batch_invalid_url_rejected(self):
        r = client.post("/crawl/batch", json={"urls": ["not-a-url"]})
        assert r.status_code == 422

    def test_batch_concurrency_limit_enforced(self):
        r = client.post("/crawl/batch", json={
            "urls": ["https://example.com"],
            "concurrency": 21,      # max is 20
        })
        assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Cache API endpoint tests
# ═════════════════════════════════════════════════════════════════════════════

class TestCacheAPI:

    def test_cache_stats_endpoint(self):
        r = client.get("/cache/stats")
        assert r.status_code == 200
        data = r.json()
        assert "backend" in data
        assert "entries" in data
        assert "ttl_seconds" in data

    def test_cache_clear_endpoint(self):
        r = client.delete("/cache")
        assert r.status_code == 200
        assert "cleared" in r.json()["detail"].lower()

    def test_cache_evict_endpoint(self):
        r = client.delete("/cache/url", params={"url": "https://example.com"})
        assert r.status_code == 200
        assert "example.com" in r.json()["detail"]

    def test_health_includes_cache_backend(self):
        data = client.get("/health").json()
        assert "cache_backend" in data
        assert data["cache_backend"] in ("memory", "redis")

    def test_single_crawl_populates_cache(self):
        """After a successful /crawl, a second call should be served from cache."""
        from crawler.http_fetch import FetchResult
        fetch_result = FetchResult(
            url="https://example.com/cache-test",
            final_url="https://example.com/cache-test",
            status_code=200,
            html=SAMPLE_HTML,
            content_type="text/html",
        )
        # Clear any existing cache entry
        client.delete("/cache/url", params={"url": "https://example.com/cache-test"})

        with patch("crawler.services.crawl_service.fetch_page", return_value=fetch_result):
            r1 = client.post("/crawl", json={"url": "https://example.com/cache-test"})
        assert r1.status_code == 200
        assert r1.json()["from_cache"] is False

        # Second call — no mock needed, should be served from cache
        r2 = client.post("/crawl", json={"url": "https://example.com/cache-test"})
        assert r2.status_code == 200
        assert r2.json()["from_cache"] is True

    def test_single_crawl_bypass_cache(self):
        """use_cache=false must skip the cache."""
        from crawler.http_fetch import FetchResult
        fetch_result = FetchResult(
            url="https://example.com/no-cache",
            final_url="https://example.com/no-cache",
            status_code=200,
            html=SAMPLE_HTML,
            content_type="text/html",
        )
        with patch("crawler.services.crawl_service.fetch_page", return_value=fetch_result):
            r = client.post("/crawl?use_cache=false",
                            json={"url": "https://example.com/no-cache"})
        assert r.status_code == 200
        assert r.json()["from_cache"] is False


# ═════════════════════════════════════════════════════════════════════════════
# Live integration tests (opt-in)
# ═════════════════════════════════════════════════════════════════════════════

INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Set RUN_INTEGRATION=1 to run live network tests",
)


@INTEGRATION
def test_live_batch_three_urls():
    r = client.post("/crawl/batch", json={
        "urls": [
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "https://news.ycombinator.com",
            "https://www.rei.com/blog/camp/how-to-introduce-your-indoorsy-friend-to-the-outdoors/",
        ],
        "concurrency": 3,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["succeeded"] >= 2
    for item in data["results"]:
        assert item["status"] in ("ok", "cached", "error")


@INTEGRATION
def test_live_batch_cache_hit():
    """Second batch call on same URLs should return cached results."""
    urls = ["https://en.wikipedia.org/wiki/Python_(programming_language)"]
    client.post("/crawl/batch", json={"urls": urls})   # warm up cache
    r2 = client.post("/crawl/batch", json={"urls": urls})
    assert r2.status_code == 200
    assert r2.json()["cached"] == 1
