from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WebCrawler/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    html: str
    content_type: str
    error: Optional[str] = None


def fetch_page(url: str, timeout: float = 15.0, follow_redirects: bool = True) -> FetchResult:
    try:
        with httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as client:
            resp = client.get(url)
            ct = resp.headers.get("content-type", "")
            return FetchResult(
                url=url,
                final_url=str(resp.url),
                status_code=resp.status_code,
                html=resp.text,
                content_type=ct,
            )
    except httpx.TimeoutException as e:
        return FetchResult(url, url, 0, "", "", error=f"Timeout: {e}")
    except httpx.RequestError as e:
        return FetchResult(url, url, 0, "", "", error=f"Request error: {e}")
