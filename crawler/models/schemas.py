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
    is_external: bool


class ImageInfo(BaseModel):
    src: str
    alt: str


class PageMetadata(BaseModel):
    url: str
    final_url: str
    status_code: int

    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None
    charset: Optional[str] = None
    canonical: Optional[str] = None
    robots: Optional[str] = None

    og: Dict[str, str] = {}
    twitter: Dict[str, str] = {}

    headings: Dict[str, List[str]] = {}
    links: List[LinkInfo] = []
    images: List[ImageInfo] = []

    body_text: str = ""
    word_count: int = 0

    page_category: str = "unknown"
    topics: List[str] = []
    topic_scores: Dict[str, float] = {}

    from_cache: bool = False
    cached_at: Optional[str] = None


class BatchCrawlRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., min_length=1, max_length=50)
    timeout: float = Field(default=45.0, ge=1.0, le=120.0)
    follow_redirects: bool = True
    concurrency: int = Field(default=5, ge=1, le=20)


class UrlStatus(str, Enum):
    ok = "ok"
    error = "error"
    cached = "cached"


class BatchResultItem(BaseModel):
    url: str
    status: UrlStatus
    data: Optional[PageMetadata] = None
    error: Optional[str] = None


class BatchCrawlResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    cached: int
    duration_seconds: float
    results: List[BatchResultItem]


class CacheStatsResponse(BaseModel):
    backend: str
    entries: int
    ttl_seconds: int
    max_size: Optional[int] = None
