from __future__ import annotations

import asyncio
import time
from typing import List

from crawler.adapters.http_async import async_fetch_page
from crawler.classification.topics import classify_page
from crawler.infrastructure.cache import cache
from crawler.models.schemas import BatchCrawlResponse, BatchResultItem, PageMetadata, UrlStatus
from crawler.parsing.extract import parse_page

_SOFT = {401, 403, 406, 429}


async def _one(
    url: str,
    timeout: float,
    follow_redirects: bool,
    semaphore: asyncio.Semaphore,
) -> BatchResultItem:
    hit = cache.get(url)
    if hit is not None:
        return BatchResultItem(url=url, status=UrlStatus.cached, data=hit)

    async with semaphore:
        fr = await async_fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)

    if fr.error:
        return BatchResultItem(url=url, status=UrlStatus.error, error=fr.error)

    if fr.status_code in _SOFT and fr.html.strip():
        meta = classify_page(parse_page(fr))
        note = f"[http {fr.status_code}] gated — parsed what we got."
        meta.description = f"{note} {meta.description or ''}".strip()
        cache.set(url, meta)
        return BatchResultItem(url=url, status=UrlStatus.ok, data=meta)

    if fr.status_code in _SOFT or fr.status_code >= 400:
        return BatchResultItem(url=url, status=UrlStatus.error, error=f"http {fr.status_code}")

    meta: PageMetadata = classify_page(parse_page(fr))
    cache.set(url, meta)
    return BatchResultItem(url=url, status=UrlStatus.ok, data=meta)


async def crawl_batch(
    urls: List[str],
    *,
    timeout: float = 45.0,
    follow_redirects: bool = True,
    concurrency: int = 5,
) -> BatchCrawlResponse:
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(concurrency)
    tasks = [_one(u, timeout, follow_redirects, sem) for u in urls]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    out: List[BatchResultItem] = []
    for u, item in zip(urls, raw):
        if isinstance(item, Exception):
            out.append(BatchResultItem(url=u, status=UrlStatus.error, error=str(item)))
        else:
            out.append(item)

    ok = sum(1 for r in out if r.status == UrlStatus.ok)
    mem = sum(1 for r in out if r.status == UrlStatus.cached)
    bad = sum(1 for r in out if r.status == UrlStatus.error)

    return BatchCrawlResponse(
        total=len(out),
        succeeded=ok,
        failed=bad,
        cached=mem,
        duration_seconds=round(time.perf_counter() - t0, 3),
        results=out,
    )
