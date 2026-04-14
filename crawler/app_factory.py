from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from crawler.api.routes import router
from crawler.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Web Crawler API", version="2.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=512)

    if settings.cors_origins:
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        if origins:
            # allow_credentials must be False when allow_origins contains "*"
            # (Starlette raises ValueError otherwise)
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
