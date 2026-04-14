from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from crawler.config import settings
from crawler.domain.errors import UpstreamCrawlError
from crawler.infrastructure.cache import cache
from crawler.models.schemas import (
    BatchCrawlRequest,
    BatchCrawlResponse,
    CacheStatsResponse,
    CrawlRequest,
    PageMetadata,
)
from crawler.services.batch_service import crawl_batch
from crawler.services.crawl_service import crawl_url

router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    p = settings.static_dir / "index.html"
    if not p.is_file():
        return JSONResponse({"detail": "no ui"}, status_code=503)
    return FileResponse(p, media_type="text/html; charset=utf-8")


@router.post("/crawl", response_model=PageMetadata, tags=["crawl"])
def crawl_one(
    request: CrawlRequest,
    use_cache: bool = Query(default=True),
) -> PageMetadata:
    url = str(request.url)

    # check cache first — skip entirely if use_cache=false (useful for testing
    # or when you know the page has changed since the last crawl)
    if use_cache:
        c = cache.get(url)
        if c is not None:
            return c

    try:
        out = crawl_url(url, timeout=request.timeout, follow_redirects=request.follow_redirects)
    except UpstreamCrawlError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    cache.set(url, out)
    return out


@router.post("/crawl/batch", response_model=BatchCrawlResponse, tags=["crawl"])
async def crawl_many(request: BatchCrawlRequest) -> BatchCrawlResponse:
    # pydantic already validated: 1–50 URLs, concurrency 1–20, valid URLs.
    # just pass through to the service layer.
    urls = [str(u) for u in request.urls]
    return await crawl_batch(
        urls,
        timeout=request.timeout,
        follow_redirects=request.follow_redirects,
        concurrency=request.concurrency,
    )


@router.get("/cache/stats", response_model=CacheStatsResponse, tags=["cache"])
def cache_stats():
    return cache.stats()


@router.delete("/cache", tags=["cache"])
def cache_clear():
    cache.clear()
    return JSONResponse({"detail": "cleared"})


@router.delete("/cache/url", tags=["cache"])
def cache_evict(url: str = Query(...)):
    cache.delete(url)
    return JSONResponse({"detail": f"gone: {url}"})


@router.get("/health", tags=["ops"])
def health():
    # quick liveness check — also reports which cache backend is active
    # so I can confirm Redis is connected after a deploy
    return JSONResponse({"status": "ok", "cache_backend": cache.stats().backend})
