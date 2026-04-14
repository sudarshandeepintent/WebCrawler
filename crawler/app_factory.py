from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from crawler.api.routes import router
from crawler.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Web Crawler API", version="2.0.0")

    # gzip responses over 512 bytes — helps a lot for large JSON with many links/images
    app.add_middleware(GZipMiddleware, minimum_size=512)

    if settings.cors_origins:
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        if origins:
            # Starlette raises ValueError if you combine allow_origins=["*"] with
            # allow_credentials=True — it's actually invalid per the CORS spec.
            # so I only set credentials=True when specific origins are listed.
            wildcard = origins == ["*"]
            app.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=not wildcard,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["*"],
            )

    app.include_router(router)
    return app
