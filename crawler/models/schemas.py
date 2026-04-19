from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl
    timeout: float = Field(default=45.0, ge=1.0, le=120.0)  
    follow_redirects: bool = True


class LinkInfo(BaseModel):
    href: str
    text: str
    is_external: bool  # True if the link points to a different domain than the crawled page


class ImageInfo(BaseModel):
    src: str
    alt: str


class PageMetadata(BaseModel):
    # core HTTP info
    url: str          # original URL as submitted
    final_url: str    # where we actually landed after redirects
    status_code: int

    # standard HTML meta tags
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None
    charset: Optional[str] = None
    canonical: Optional[str] = None
    robots: Optional[str] = None

    # social / SEO tags
    og: Dict[str, str] = {}
    twitter: Dict[str, str] = {}

    # page structure
    headings: Dict[str, List[str]] = {}
    links: List[LinkInfo] = []
    images: List[ImageInfo] = []

    # body content
    body_text: str = ""
    word_count: int = 0

    # classification results from topics.py
    page_category: str = "unknown"
    topics: List[str] = []
    topic_scores: Dict[str, float] = {}

    # performance / cache fields
    fetch_duration_seconds: Optional[float] = None  # only set on live fetches, None on cache hits
    from_cache: bool = False
    cached_at: Optional[str] = None  # ISO timestamp of when the result was first cached


class BatchCrawlRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., min_length=1, max_length=50)  # 50 is a reasonable limit to avoid abuse
    timeout: float = Field(default=45.0, ge=1.0, le=120.0)
    follow_redirects: bool = True
    concurrency: int = Field(default=5, ge=1, le=20)  # max 20 — higher than this and you start hitting rate limits


class UrlStatus(str, Enum):
    ok = "ok"
    error = "error"
    cached = "cached"


class BatchResultItem(BaseModel):
    url: str
    status: UrlStatus
    data: Optional[PageMetadata] = None  # None when status is "error"
    error: Optional[str] = None          # None when status is "ok" or "cached"


class BatchCrawlResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    cached: int
    duration_seconds: float  # wall-clock time for the entire batch
    results: List[BatchResultItem]


class CacheStatsResponse(BaseModel):
    backend: str            # "memory" or "redis"
    entries: int
    ttl_seconds: int
    max_size: Optional[int] = None  # None for Redis (no hard limit enforced by the app)


class DeepCrawlRequest(BaseModel):
    seed_url: HttpUrl
    max_depth: int = Field(default=2, ge=1, le=5)       # how many link-hops from seed
    max_pages: int = Field(default=20, ge=1, le=100)    # hard stop so it doesn't run forever
    stay_on_domain: bool = True                          # don't follow links to other sites
    concurrency: int = Field(default=3, ge=1, le=10)
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    follow_redirects: bool = True


class CrawledPage(BaseModel):
    url: str
    depth: int               # 0 = seed, 1 = one hop from seed, etc.
    status: str              # "ok", "cached", "error"
    data: Optional[PageMetadata] = None
    error: Optional[str] = None


class DeepCrawlStats(BaseModel):
    pages_crawled: int
    pages_failed: int
    pages_cached: int
    total_links_found: int
    max_depth_reached: int
    duration_seconds: float


class DeepCrawlResponse(BaseModel):
    seed_url: str
    pages: List[CrawledPage]
    stats: DeepCrawlStats
