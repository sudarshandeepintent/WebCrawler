from __future__ import annotations

import asyncio
import time
from typing import List, Set, Tuple
from urllib.parse import urlparse, urlunparse

from crawler.adapters.http_async import async_fetch_page
from crawler.classification.topics import classify_page
from crawler.infrastructure.cache import cache
from crawler.models.schemas import CrawledPage, DeepCrawlResponse, DeepCrawlStats, PageMetadata
from crawler.parsing.extract import parse_page

_SOFT = {401, 403, 406, 429}


def _normalize(url: str) -> str:
    # strip the fragment (#section) since it points to the same page, just a different scroll position.
    # also strip trailing slashes from the path so /about and /about/ don't get crawled twice.
    p = urlparse(url)
    clean_path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme, p.netloc, clean_path, p.params, p.query, ""))


def _same_domain(url: str, host: str) -> bool:
    # allow www.example.com and example.com to be treated as the same domain.
    # without this, a seed of example.com would skip all links to www.example.com.
    parsed = urlparse(url).netloc
    return parsed == host or parsed == "www." + host or host == "www." + parsed


async def _fetch_one(
    url: str,
    depth: int,
    sem: asyncio.Semaphore,
    timeout: float,
    follow_redirects: bool,
) -> Tuple[CrawledPage, list]:
    # hit cache before acquiring the semaphore — cached pages are free,
    # no point counting them against the concurrency limit.
    hit = cache.get(url)
    if hit is not None:
        return CrawledPage(url=url, depth=depth, status="cached", data=hit), hit.links

    async with sem:
        fr = await async_fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)

    if fr.error:
        return CrawledPage(url=url, depth=depth, status="error", error=fr.error), []

    # gated but has HTML — parse what we can, still follow its links
    if fr.status_code in _SOFT and fr.html.strip():
        meta = classify_page(parse_page(fr))
        cache.set(url, meta)
        return CrawledPage(url=url, depth=depth, status="ok", data=meta), meta.links

    if fr.status_code >= 400:
        return CrawledPage(url=url, depth=depth, status="error", error=f"http {fr.status_code}"), []

    meta = classify_page(parse_page(fr))
    cache.set(url, meta)
    return CrawledPage(url=url, depth=depth, status="ok", data=meta), meta.links


async def deep_crawl(
    seed_url: str,
    *,
    max_depth: int = 2,
    max_pages: int = 20,
    stay_on_domain: bool = True,
    concurrency: int = 3,
    timeout: float = 30.0,
    follow_redirects: bool = True,
) -> DeepCrawlResponse:
    t0 = time.perf_counter()
    seed_host = urlparse(seed_url).netloc

    visited: Set[str] = set()
    results: List[CrawledPage] = []
    total_links_found = 0
    max_depth_reached = 0

    # BFS — process one depth level at a time.
    # this guarantees we always crawl shallower pages before deeper ones,
    # and makes the depth number on each result accurate.
    current_level: List[Tuple[str, int]] = [(_normalize(seed_url), 0)]
    sem = asyncio.Semaphore(concurrency)

    while current_level and len(visited) < max_pages:
        # pick URLs from this level that we haven't visited yet,
        # respecting the max_pages cap
        to_fetch: List[Tuple[str, int]] = []
        for url, depth in current_level:
            norm = _normalize(url)
            if norm not in visited and len(visited) + len(to_fetch) < max_pages:
                visited.add(norm)
                to_fetch.append((norm, depth))

        if not to_fetch:
            break

        # fetch everything at this depth level concurrently
        tasks = [
            _fetch_one(url, depth, sem, timeout, follow_redirects)
            for url, depth in to_fetch
        ]
        batch = await asyncio.gather(*tasks, return_exceptions=True)

        next_level: List[Tuple[str, int]] = []
        for (url, depth), result in zip(to_fetch, batch):
            if isinstance(result, Exception):
                results.append(CrawledPage(url=url, depth=depth, status="error", error=str(result)))
                continue

            page_result, links = result
            results.append(page_result)

            if page_result.status in ("ok", "cached"):
                max_depth_reached = max(max_depth_reached, depth)
                total_links_found += len(links)

                # only queue the next level if we haven't hit max_depth yet
                if depth < max_depth:
                    for link in links:
                        norm_href = _normalize(link.href)
                        if norm_href in visited:
                            continue
                        # domain check — skip external links if stay_on_domain is set
                        if stay_on_domain and not _same_domain(norm_href, seed_host):
                            continue
                        next_level.append((norm_href, depth + 1))

        current_level = next_level

    ok     = sum(1 for r in results if r.status == "ok")
    cached = sum(1 for r in results if r.status == "cached")
    failed = sum(1 for r in results if r.status == "error")

    return DeepCrawlResponse(
        seed_url=seed_url,
        pages=results,
        stats=DeepCrawlStats(
            pages_crawled=ok + cached,
            pages_failed=failed,
            pages_cached=cached,
            total_links_found=total_links_found,
            max_depth_reached=max_depth_reached,
            duration_seconds=round(time.perf_counter() - t0, 3),
        ),
    )
