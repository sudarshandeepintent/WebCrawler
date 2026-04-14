from __future__ import annotations

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
