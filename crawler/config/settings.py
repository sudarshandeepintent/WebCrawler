from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    redis_url: str | None
    cache_ttl: int
    cache_max: int
    cache_prefix: str
    static_dir: Path
    cors_origins: str


def _load() -> Settings:
    root = Path(__file__).resolve().parents[2]
    return Settings(
        redis_url=os.getenv("REDIS_URL"),
        cache_ttl=int(os.getenv("CACHE_TTL", "3600")),
        cache_max=int(os.getenv("CACHE_MAX", "500")),
        cache_prefix=os.getenv("CACHE_PREFIX", "webcrawler:"),
        static_dir=root / "static",
        cors_origins=os.getenv("CORS_ORIGINS", "").strip(),
    )


settings = _load()
