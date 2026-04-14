from __future__ import annotations

from crawler.html_metadata import parse_page
from crawler.http_fetch import fetch_page
from crawler.schemas import PageMetadata
from crawler.topic_scoring import classify_page


class UpstreamCrawlError(Exception):
    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def crawl_url(url: str, *, timeout: float = 15.0, follow_redirects: bool = True) -> PageMetadata:
    fr = fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)
    if fr.error:
        raise UpstreamCrawlError(fr.error, status_code=502)
    if fr.status_code >= 400:
        raise UpstreamCrawlError(
            f"Remote server returned HTTP {fr.status_code}",
            status_code=fr.status_code,
        )
    meta = parse_page(fr)
    return classify_page(meta)
