# WebCrawler

A web crawling and scraping API I built with FastAPI. Point it at any URL and it fetches the page, pulls out all the useful metadata (title, description, Open Graph, Twitter Card, headings, links, images), runs topic classification across 16 categories, and gives you everything back as clean JSON.

It supports three modes — single URL scrape, async batch crawl for a list of known URLs, and a true BFS deep crawler that follows links automatically across a site. There's a built-in dashboard UI, a Redis-backed cache, and it's deployed on Google Cloud Run.

---

## Features

- **Single URL scrape** — title, description, OG tags, Twitter Card, headings, links, images, word count, fetch duration, topic scores
- **Batch crawl** — up to 50 URLs submitted at once, fetched concurrently using asyncio + semaphore
- **Deep crawl** — BFS crawler that starts at a seed URL and follows links level by level; configurable max depth, max pages, and domain scoping
- **Topic classification** — 16 topics (technology, outdoors, finance, e-commerce, news, sports, etc.) scored with TF-weighted keyword matching and exclusivity weighting
- **Smart caching** — in-process LRU cache by default, Redis when `REDIS_URL` is set; cache hits skip the network entirely
- **WAF bypass** — `curl-cffi` with Chrome 124 TLS fingerprint impersonation gets through Akamai/Cloudflare bot detection
- **Dashboard UI** — dark-mode single-page app with tabs, expandable results, and a built-in user guide — available at `/`
- **OpenAPI docs** — auto-generated at `/docs`

---

## Quick Start (local)

### 1. Clone and set up

```bash
git clone https://github.com/your-username/WebCrawler.git
cd WebCrawler

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Run

```bash
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** for the UI, or **http://localhost:8000/docs** for the API explorer.

### 3. Try it with curl

```bash
# Single URL
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://news.ycombinator.com"}'

# Batch crawl
curl -X POST http://localhost:8000/crawl/batch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://news.ycombinator.com",
      "https://en.wikipedia.org/wiki/Python_(programming_language)"
    ],
    "concurrency": 2
  }'

# Deep crawl — follows links automatically from the seed URL
curl -X POST http://localhost:8000/crawl/deep \
  -H "Content-Type: application/json" \
  -d '{
    "seed_url": "https://en.wikipedia.org/wiki/Web_crawler",
    "max_depth": 2,
    "max_pages": 15,
    "stay_on_domain": true
  }'
```

---

## Environment Variables

All optional — the app works out of the box without any of them.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | *(not set)* | Redis connection string, e.g. `rediss://default:pass@host:6379`. If unset, falls back to in-memory LRU cache. |
| `CACHE_TTL` | `3600` | Seconds before a cached entry expires. |
| `CACHE_MAX` | `500` | Max entries in the in-memory cache before LRU eviction kicks in. |
| `CACHE_PREFIX` | `webcrawler:` | Key prefix used in Redis. |
| `CORS_ORIGINS` | *(not set)* | Comma-separated list of allowed browser origins. Set to `*` to allow all. |
| `PORT` | `8000` | Port the server listens on (Cloud Run sets this automatically). |

Create a `.env` file in the project root to set these locally:

```env
REDIS_URL=redis://localhost:6379
CACHE_TTL=3600
CORS_ORIGINS=*
```

---

## API Reference

### `POST /crawl`

Crawl a single URL.

**Query params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `use_cache` | bool | `true` | Return cached result if available. |

**Request body**

```json
{
  "url": "https://example.com",
  "timeout": 45,
  "follow_redirects": true
}
```

**Response** — `PageMetadata`

```json
{
  "url": "https://example.com",
  "final_url": "https://example.com",
  "status_code": 200,
  "title": "Example Domain",
  "description": "...",
  "author": null,
  "language": "en",
  "charset": "utf-8",
  "canonical": "https://example.com",
  "robots": "index, follow",
  "og": {},
  "twitter": {},
  "headings": { "h1": ["Example Domain"] },
  "links": [{ "href": "https://...", "text": "...", "is_external": true }],
  "images": [{ "src": "https://...", "alt": "..." }],
  "body_text": "...",
  "word_count": 312,
  "page_category": "technology",
  "topics": ["technology", "education"],
  "topic_scores": { "technology": 0.74, "education": 0.21 },
  "fetch_duration_seconds": 1.247,
  "from_cache": false,
  "cached_at": null
}
```

---

### `POST /crawl/batch`

Crawl up to 50 URLs concurrently.

**Request body**

```json
{
  "urls": ["https://example.com", "https://news.ycombinator.com"],
  "concurrency": 5,
  "timeout": 45,
  "follow_redirects": true
}
```

Limits: `urls` 1–50, `concurrency` 1–20.

**Response** — `BatchCrawlResponse`

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "cached": 0,
  "duration_seconds": 3.187,
  "results": [
    {
      "url": "https://example.com",
      "status": "ok",
      "data": { ... },
      "error": null
    }
  ]
}
```

`status` is one of `ok`, `cached`, `error`.

---

### `POST /crawl/deep`

BFS deep crawler — starts at `seed_url`, follows internal links level by level until it hits `max_depth` or `max_pages`.

**Request body**

```json
{
  "seed_url": "https://example.com/blog",
  "max_depth": 2,
  "max_pages": 20,
  "stay_on_domain": true,
  "concurrency": 3,
  "timeout": 30,
  "follow_redirects": true
}
```

Limits: `max_depth` 1–5, `max_pages` 1–100, `concurrency` 1–10.

**Response** — `DeepCrawlResponse`

```json
{
  "seed_url": "https://example.com/blog",
  "pages": [
    {
      "url": "https://example.com/blog",
      "depth": 0,
      "status": "ok",
      "data": { ... },
      "error": null
    },
    {
      "url": "https://example.com/blog/post-1",
      "depth": 1,
      "status": "ok",
      "data": { ... },
      "error": null
    }
  ],
  "stats": {
    "pages_crawled": 12,
    "pages_failed": 1,
    "pages_cached": 3,
    "total_links_found": 148,
    "max_depth_reached": 2,
    "duration_seconds": 18.4
  }
}
```

`status` per page is one of `ok`, `cached`, `error`.

---

### Cache endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/cache/stats` | Returns backend, entry count, TTL, max size. |
| `DELETE` | `/cache` | Clears the entire cache. |
| `DELETE` | `/cache/url?url=<url>` | Evicts a single URL from the cache. |

### Ops

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status":"ok","cache_backend":"memory"}` or `"redis"`. |
| `GET` | `/docs` | Swagger UI — interactive API explorer. |

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

To also run live network tests (makes real HTTP requests):

```bash
RUN_INTEGRATION=1 pytest tests/test_batch_cache.py -v
```

Test coverage includes:
- `MemoryCache` — miss, set/get, TTL expiry, LRU eviction, stats
- `crawl_batch` — success, partial failure, cache hit, order preservation
- Batch API — schema validation, empty/oversized input rejection, concurrency limit
- Cache API — stats, clear, evict, health endpoint, cache population, bypass

---

## Docker

```bash
# Build
docker build -t webcrawler .

# Run (maps container port 8080 to localhost 8080)
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  webcrawler
```

With Redis:

```bash
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  webcrawler
```

Open **http://localhost:8080**.

---

## Google Cloud Run Deployment

### One-time setup

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

# Create an Artifact Registry repo for the image
gcloud artifacts repositories create webcrawler-repo \
  --repository-format=docker \
  --location=us-central1
```

### Build and deploy

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/webcrawler-repo/webcrawler:latest

# Build the Docker image in Cloud Build
gcloud builds submit --tag $IMAGE .

# Deploy to Cloud Run
gcloud run deploy webcrawler \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 2 \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 80 \
  --timeout 120 \
  --set-env-vars="CACHE_TTL=3600,CACHE_MAX=500,CORS_ORIGINS=*"
```

To add Redis (recommended for production — use [Upstash](https://upstash.com) for a free serverless Redis):

```bash
--set-env-vars="REDIS_URL=rediss://default:PASSWORD@host:6379,CACHE_TTL=3600,CORS_ORIGINS=*"
```

After deploy, the command prints your service URL. Open it in a browser for the dashboard.

---

## Project Structure

```
WebCrawler/
├── main.py                          # App entry point
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── static/
│   └── index.html                   # Dashboard UI (single file, no build step)
├── crawler/
│   ├── app_factory.py               # FastAPI app creation + middleware
│   ├── api/
│   │   └── routes.py                # All API route handlers
│   ├── config/
│   │   └── settings.py              # Environment variable loading
│   ├── domain/
│   │   ├── fetch_result.py          # FetchResult dataclass, shared HTTP headers
│   │   └── errors.py                # UpstreamCrawlError
│   ├── adapters/
│   │   ├── http_sync.py             # Sync fetch: curl-cffi → httpx fallback
│   │   └── http_async.py            # Async fetch for batch crawling
│   ├── parsing/
│   │   └── extract.py               # HTML → PageMetadata (BeautifulSoup)
│   ├── classification/
│   │   └── topics.py                # TF-based topic scoring + category detection
│   ├── services/
│   │   ├── crawl_service.py         # Single URL: fetch → parse → classify → cache
│   │   ├── batch_service.py         # Batch: asyncio.gather + semaphore
│   │   └── deep_crawl_service.py    # BFS crawler: frontier queue + visited set + domain scoping
│   ├── infrastructure/
│   │   └── cache.py                 # MemoryCache (LRU + TTL) and RedisCache
│   └── models/
│       └── schemas.py               # Pydantic request/response models
└── tests/
    ├── test_crawl_api.py
    └── test_batch_cache.py
```

---

## Tech Stack

| Layer | Library |
|-------|---------|
| Web framework | FastAPI + Uvicorn |
| HTTP (sync) | curl-cffi (Chrome TLS impersonation), httpx fallback |
| HTTP (async) | httpx async client |
| HTML parsing | BeautifulSoup4 + lxml |
| Data validation | Pydantic v2 |
| Cache (memory) | Python `OrderedDict` (LRU + TTL) |
| Cache (remote) | Redis via `redis-py` |
| Tests | pytest |
| Deployment | Docker + Google Cloud Run |

Some ScreenShots ->
<img width="1666" height="794" alt="Screenshot 2026-04-15 at 4 03 03 PM" src="https://github.com/user-attachments/assets/34782fd5-c7b4-4216-aa91-cb8b8e4f8153" />

