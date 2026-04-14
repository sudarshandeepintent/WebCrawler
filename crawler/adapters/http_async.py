from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from crawler.domain.fetch_result import BACKOFF, FetchResult, HDRS, referer_for

# same curl-cffi trick as the sync adapter — needed for WAF-protected sites.
# async version uses curl_cffi's AsyncSession instead of requests.get
try:
    from curl_cffi.requests import AsyncSession as _CffiSession  # type: ignore[import]
    _have_cffi = True
except ImportError:
    _have_cffi = False


async def _curl(url: str, timeout: float, follow: bool) -> FetchResult:
    h = {**HDRS, "Referer": referer_for(url)}
    try:
        async with _CffiSession(impersonate="chrome124") as session:
            resp = await session.get(
                url,
                headers=h,
                timeout=timeout,
                allow_redirects=follow,
            )
        return FetchResult(
            url=url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            html=resp.text,
            content_type=resp.headers.get("content-type", ""),
        )
    except Exception as e:
        return FetchResult(url, url, 0, "", "", error=f"cffi async: {e}")


async def _httpx(url: str, timeout: float, follow: bool) -> FetchResult:
    h = {**HDRS, "Referer": referer_for(url)}
    t = httpx.Timeout(connect=min(20.0, timeout), read=timeout, write=min(20.0, timeout), pool=10.0)
    last: Optional[FetchResult] = None
    delays = (0.0,) + BACKOFF

    for i, wait in enumerate(delays):
        if wait:
            await asyncio.sleep(wait)  # non-blocking sleep — other tasks keep running
        try:
            async with httpx.AsyncClient(headers=h, timeout=t, follow_redirects=follow) as client:
                resp = await client.get(url)
            fr = FetchResult(
                url=url,
                final_url=str(resp.url),
                status_code=resp.status_code,
                html=resp.text,
                content_type=resp.headers.get("content-type", ""),
            )
            if resp.status_code in (429, 503) and i < len(BACKOFF):
                last = fr
                continue
            return fr
        except httpx.TimeoutException as e:
            return FetchResult(url, url, 0, "", "", error=f"timeout: {e}")
        except httpx.RequestError as e:
            return FetchResult(url, url, 0, "", "", error=f"request error: {e}")
    assert last is not None
    return last


async def async_fetch_page(
    url: str,
    timeout: float = 45.0,
    follow_redirects: bool = True,
) -> FetchResult:
    # prefer curl-cffi, fall back to httpx if it's not installed
    if _have_cffi:
        return await _curl(url, timeout, follow_redirects)
    return await _httpx(url, timeout, follow_redirects)
