from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None  # type: ignore[assignment]

# chrome-ish; helps on sites that only sniff headers
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

BACKOFF = (1.5, 4.0)


def _referer(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    html: str
    content_type: str
    error: Optional[str] = None


def _cffi_get(url: str, timeout: float, follow: bool) -> FetchResult:
    h = {**HDRS, "Referer": _referer(url)}
    try:
        r = cffi_requests.get(
            url,
            headers=h,
            impersonate="chrome124",
            timeout=timeout,
            allow_redirects=follow,
        )
        return FetchResult(
            url=url,
            final_url=str(r.url),
            status_code=r.status_code,
            html=r.text,
            content_type=r.headers.get("content-type", ""),
        )
    except Exception as e:
        return FetchResult(url, url, 0, "", "", error=f"cffi error: {e}")


def _httpx_get(url: str, timeout: float, follow: bool) -> FetchResult:
    h = {**HDRS, "Referer": _referer(url)}
    t = httpx.Timeout(connect=min(20.0, timeout), read=timeout, write=min(20.0, timeout), pool=10.0)
    last: Optional[FetchResult] = None
    delays = (0.0,) + BACKOFF
    for i, wait in enumerate(delays):
        if wait:
            time.sleep(wait)
        try:
            with httpx.Client(headers=h, timeout=t, follow_redirects=follow, http2=False) as client:
                resp = client.get(url)
            ct = resp.headers.get("content-type", "")
            fr = FetchResult(
                url=url,
                final_url=str(resp.url),
                status_code=resp.status_code,
                html=resp.text,
                content_type=ct,
            )
            if resp.status_code in (429, 503) and i < len(BACKOFF):
                last = fr
                continue
            return fr
        except httpx.ReadTimeout:
            return FetchResult(
                url,
                url,
                0,
                "",
                "",
                error=f"timed out reading body ({timeout:g}s). bump timeout in json, max 120",
            )
        except httpx.ConnectTimeout as e:
            return FetchResult(url, url, 0, "", "", error=f"connect timeout: {e}")
        except httpx.TimeoutException as e:
            return FetchResult(url, url, 0, "", "", error=f"timeout: {e}")
        except httpx.RequestError as e:
            return FetchResult(url, url, 0, "", "", error=f"request error: {e}")
    assert last is not None
    return last


def fetch_page(url: str, timeout: float = 45.0, follow_redirects: bool = True) -> FetchResult:
    if cffi_requests is not None:
        return _cffi_get(url, timeout, follow_redirects)
    return _httpx_get(url, timeout, follow_redirects)
