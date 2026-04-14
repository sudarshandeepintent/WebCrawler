from __future__ import annotations

import time
from typing import Optional, Protocol, runtime_checkable

import httpx

from crawler.domain.fetch_result import BACKOFF, FetchResult, HDRS, referer_for

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None  # type: ignore[assignment]


@runtime_checkable
class SyncFetchStrategy(Protocol):
    def pull(self, url: str, timeout: float, follow: bool) -> FetchResult: ...


class _CurlSync:
    def pull(self, url: str, timeout: float, follow: bool) -> FetchResult:
        h = {**HDRS, "Referer": referer_for(url)}
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


class _HttpxSync:
    def pull(self, url: str, timeout: float, follow: bool) -> FetchResult:
        h = {**HDRS, "Referer": referer_for(url)}
        t = httpx.Timeout(
            connect=min(20.0, timeout),
            read=timeout,
            write=min(20.0, timeout),
            pool=10.0,
        )
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
                    error=f"read timed out ({timeout:g}s), try higher timeout in json (max 120)",
                )
            except httpx.ConnectTimeout as e:
                return FetchResult(url, url, 0, "", "", error=f"connect timeout: {e}")
            except httpx.TimeoutException as e:
                return FetchResult(url, url, 0, "", "", error=f"timeout: {e}")
            except httpx.RequestError as e:
                return FetchResult(url, url, 0, "", "", error=f"request error: {e}")
        assert last is not None
        return last


def _strategy() -> SyncFetchStrategy:
    if cffi_requests is not None:
        return _CurlSync()
    return _HttpxSync()


_impl = _strategy()


def fetch_page(url: str, timeout: float = 45.0, follow_redirects: bool = True) -> FetchResult:
    return _impl.pull(url, timeout, follow_redirects)
