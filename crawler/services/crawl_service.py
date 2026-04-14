from __future__ import annotations

import time

from crawler.adapters import http_sync
from crawler.classification.topics import classify_page
from crawler.domain.errors import UpstreamCrawlError
from crawler.models.schemas import PageMetadata
from crawler.parsing.extract import parse_page

fetch_page = http_sync.fetch_page

_SOFT = {401, 403, 406, 429}


def crawl_url(url: str, *, timeout: float = 45.0, follow_redirects: bool = True) -> PageMetadata:
    t0 = time.perf_counter()
    fr = fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)
    duration = round(time.perf_counter() - t0, 3)

    if fr.error:
        raise UpstreamCrawlError(fr.error, status_code=502)

    if fr.status_code in _SOFT and fr.html.strip():
        meta = classify_page(parse_page(fr))
        note = f"[http {fr.status_code}] gated — parsed what we got."
        meta.description = f"{note} {meta.description or ''}".strip()
        meta.fetch_duration_seconds = duration
        return meta

    if fr.status_code in _SOFT:
        raise UpstreamCrawlError(f"http {fr.status_code}, empty body", status_code=fr.status_code)

    if fr.status_code >= 400:
        raise UpstreamCrawlError(f"http {fr.status_code}", status_code=fr.status_code)

    meta = classify_page(parse_page(fr))
    meta.fetch_duration_seconds = duration
    return meta
