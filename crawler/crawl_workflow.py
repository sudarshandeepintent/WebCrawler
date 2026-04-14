from __future__ import annotations

from crawler.html_metadata import parse_page
from crawler.http_fetch import fetch_page
from crawler.schemas import PageMetadata
from crawler.topic_scoring import classify_page

# still got a body worth parsing (forbidden pages sometimes ship html anyway)
_SOFT = {401, 403, 406, 429}


class UpstreamCrawlError(Exception):
    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def crawl_url(url: str, *, timeout: float = 45.0, follow_redirects: bool = True) -> PageMetadata:
    fr = fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)

    if fr.error:
        raise UpstreamCrawlError(fr.error, status_code=502)

    if fr.status_code in _SOFT and fr.html.strip():
        meta = classify_page(parse_page(fr))
        note = f"[http {fr.status_code}] gated response — parsed whatever html came back."
        meta.description = f"{note} {meta.description or ''}".strip()
        return meta

    if fr.status_code in _SOFT:
        raise UpstreamCrawlError(f"http {fr.status_code}, empty body", status_code=fr.status_code)

    if fr.status_code >= 400:
        raise UpstreamCrawlError(f"http {fr.status_code}", status_code=fr.status_code)

    return classify_page(parse_page(fr))
