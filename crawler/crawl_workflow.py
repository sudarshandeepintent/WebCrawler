from __future__ import annotations

from crawler.html_metadata import parse_page
from crawler.http_fetch import fetch_page
from crawler.schemas import PageMetadata
from crawler.topic_scoring import classify_page

# HTTP status codes where the server DID return HTML (even if access-restricted).
# We attempt to parse whatever body was returned instead of raising a hard error.
_SOFT_BLOCK_CODES = {403, 401, 406, 429}


class UpstreamCrawlError(Exception):
    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def crawl_url(url: str, *, timeout: float = 15.0, follow_redirects: bool = True) -> PageMetadata:
    fr = fetch_page(url, timeout=timeout, follow_redirects=follow_redirects)

    # Hard network/timeout failures — nothing to parse
    if fr.error:
        raise UpstreamCrawlError(fr.error, status_code=502)

    # Soft block: server responded but restricted access.
    # Parse whatever HTML was returned (error page, meta tags, og: tags often
    # still present) and attach a warning in the description field.
    if fr.status_code in _SOFT_BLOCK_CODES:
        if fr.html.strip():
            meta = parse_page(fr)
            meta = classify_page(meta)
            warning = (
                f"[HTTP {fr.status_code}] The server restricted access. "
                "Metadata below was extracted from the error/redirect page."
            )
            meta.description = warning + (
                f" Original description: {meta.description}" if meta.description else ""
            )
            return meta
        # Empty body — raise a clear error
        raise UpstreamCrawlError(
            f"Remote server returned HTTP {fr.status_code} with no content",
            status_code=fr.status_code,
        )

    # Other 4xx / 5xx with no useful body
    if fr.status_code >= 400:
        raise UpstreamCrawlError(
            f"Remote server returned HTTP {fr.status_code}",
            status_code=fr.status_code,
        )

    meta = parse_page(fr)
    return classify_page(meta)
