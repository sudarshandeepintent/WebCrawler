from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from crawler.crawl_workflow import UpstreamCrawlError, crawl_url
from crawler.schemas import CrawlRequest, PageMetadata

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Web Crawler API", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=512)

_cors = os.getenv("CORS_ORIGINS", "").strip()
if _cors:
    origins = [o.strip() for o in _cors.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )


@app.get("/")
def index():
    path = STATIC_DIR / "index.html"
    if not path.is_file():
        return JSONResponse({"detail": "UI missing on server"}, status_code=503)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.post("/crawl", response_model=PageMetadata)
def crawl(request: CrawlRequest) -> PageMetadata:
    url = str(request.url)
    try:
        return crawl_url(
            url,
            timeout=request.timeout,
            follow_redirects=request.follow_redirects,
        )
    except UpstreamCrawlError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})
