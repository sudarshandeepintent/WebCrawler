from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

# curl-cffi is optional but strongly preferred: it impersonates a real browser's
# TLS fingerprint (JA3/JA3S/ALPN), bypassing WAF bot-detection used by sites
# like REI, Cloudflare-protected pages, Akamai-protected pages, etc.
try:
    from curl_cffi import requests as _cffi_requests  # type: ignore[import]
    _CFFI_AVAILABLE = True
except ImportError:          # pragma: no cover
    _CFFI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Full Chrome 124 browser header set.
# Even without TLS-fingerprint spoofing these headers help on lighter WAFs:
#   - User-Agent   must NOT say "Bot", "Crawler", "Spider", "compatible"
#   - Accept       must match exactly what Chrome sends
#   - Sec-Fetch-*  only real browsers send these; their absence triggers blocks
# ---------------------------------------------------------------------------
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;"
        "q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"macOS"',
    "DNT": "1",
}


_RETRY_DELAYS = [1.5, 4.0]


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    html: str
    content_type: str
    error: Optional[str] = None


def _referer(url: str) -> str:
    """Return the site homepage as a realistic Referer header value."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


# ---------------------------------------------------------------------------
# Primary fetcher: curl-cffi with Chrome TLS impersonation
# ---------------------------------------------------------------------------
def _fetch_cffi(url: str, timeout: float, follow_redirects: bool) -> FetchResult:
    headers = {**_BROWSER_HEADERS, "Referer": _referer(url)}
    try:
        resp = _cffi_requests.get(
            url,
            headers=headers,
            impersonate="chrome124",   # spoofs TLS JA3 + HTTP/2 fingerprint
            timeout=timeout,
            allow_redirects=follow_redirects,
        )
        return FetchResult(
            url=url,
            final_url=resp.url,
            status_code=resp.status_code,
            html=resp.text,
            content_type=resp.headers.get("content-type", ""),
        )
    except Exception as e:          # curl_cffi raises its own exception types
        return FetchResult(url, url, 0, "", "", error=f"cffi error: {e}")


# ---------------------------------------------------------------------------
# Fallback fetcher: httpx (no TLS spoofing, but works for most open sites)
# ---------------------------------------------------------------------------
def _fetch_httpx(url: str, timeout: float, follow_redirects: bool) -> FetchResult:
    headers = {**_BROWSER_HEADERS, "Referer": _referer(url)}
    last_result: Optional[FetchResult] = None
    for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            with httpx.Client(
                headers=headers,
                timeout=timeout,
                follow_redirects=follow_redirects,
                http2=False,
            ) as client:
                resp = client.get(url)
                ct = resp.headers.get("content-type", "")
                result = FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    status_code=resp.status_code,
                    html=resp.text,
                    content_type=ct,
                )
                if resp.status_code in (429, 503) and attempt < len(_RETRY_DELAYS):
                    last_result = result
                    continue
                return result
        except httpx.TimeoutException as e:
            return FetchResult(url, url, 0, "", "", error=f"Timeout: {e}")
        except httpx.RequestError as e:
            return FetchResult(url, url, 0, "", "", error=f"Request error: {e}")
    assert last_result is not None
    return last_result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_page(url: str, timeout: float = 15.0, follow_redirects: bool = True) -> FetchResult:
    """
    Fetch *url* with a real Chrome browser fingerprint.

    Strategy
    --------
    1. If **curl-cffi** is installed (preferred), use it with ``impersonate='chrome124'``
       so the TLS handshake is indistinguishable from a real Chrome browser.
       This bypasses Akamai, Cloudflare, and similar WAF bot-detection.
    2. Fall back to **httpx** with full Chrome headers for sites that only do
       header-level checks (no TLS fingerprinting).
    3. On 429 / 503 responses, retry automatically with back-off.
    """
    if _CFFI_AVAILABLE:
        return _fetch_cffi(url, timeout, follow_redirects)
    return _fetch_httpx(url, timeout, follow_redirects)
