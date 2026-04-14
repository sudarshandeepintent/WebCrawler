from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

# Full Chrome 124 header set — I copied this from a real browser devtools session.
# The Sec-Fetch-* and Sec-CH-UA headers are what most WAFs actually check,
# not just the User-Agent string. Without these, sites like REI or Amazon
# return 403 immediately even if the UA looks fine.
HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"macOS"',
}

# two retry delays for 429/503 responses — 1.5s then 4s.
# didn't want to go overboard with retries, just enough to handle brief rate limits.
BACKOFF = (1.5, 4.0)


def referer_for(url: str) -> str:
    # set Referer to the site's own homepage rather than leaving it blank.
    # some sites (REI especially) reject requests with no Referer header.
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


@dataclass
class FetchResult:
    # simple container that travels through fetch → parse → classify.
    # error is set instead of raising so batch jobs can handle failures
    # per-URL without crashing the whole batch.
    url: str
    final_url: str       # may differ from url after redirects
    status_code: int
    html: str
    content_type: str
    error: Optional[str] = None
