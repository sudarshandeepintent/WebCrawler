# Web Crawler API

Small FastAPI app: one POST grabs a URL, pulls HTML, rips out metadata, then guesses topics/category from word hits.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate   # win: .venv\Scripts\activate
pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

Open **http://127.0.0.1:8000/** for a small UI, or use curl:

```bash
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

API docs: http://127.0.0.1:8000/docs

### Dev (tests)

```bash
pip install -r requirements-dev.txt
pytest
```

## Docker

```bash
docker build -t webcrawler .
docker run --rm -p 8080:8080 -e PORT=8080 webcrawler
# then http://127.0.0.1:8080/
```

## Google Cloud Run

### Prerequisites

1. A **Google Cloud project** with **billing** enabled.
2. [**Google Cloud SDK**](https://cloud.google.com/sdk/docs/install) (`gcloud`) on your machine.
3. From the **repo root** (where `Dockerfile` and `main.py` live).

### One-time setup

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# APIs needed for "deploy from source" (build + run)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### Deploy (builds the Docker image in Cloud Build, then deploys)

```bash
gcloud run deploy webcrawler \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10
```

The first run can take several minutes. When it finishes, the command prints the **service URL** (open it in a browser for the UI, or use `/docs`, `/crawl`).

**Flags in short**

| Flag | Why |
|------|-----|
| `--source .` | Build this directory’s `Dockerfile` in Google Cloud Build; no local Docker required. |
| `--region` | Pick a [region](https://cloud.google.com/run/docs/locations) close to you. |
| `--allow-unauthenticated` | Anyone can call the URL (good for demos). Omit for private services and use IAM. |
| `--timeout` | Max seconds for one request (Cloud Run HTTP max 3600). Set **≥** slow crawls; app caps JSON `timeout` at **120**s. |

**Optional env on deploy**

```bash
gcloud run services update webcrawler --region us-central1 \
  --set-env-vars "CORS_ORIGINS=https://your-frontend.example"
```

Leave `CORS_ORIGINS` unset if the browser only talks to the same Cloud Run URL as the UI.

**Env vars (optional)**

| Variable | Meaning |
|----------|---------|
| `CORS_ORIGINS` | Comma-separated list of allowed browser origins if you call the API from another site. Leave unset when the UI is served from the same Cloud Run URL. |

**Production notes**

- Image runs as non-root user `app`, listens on `$PORT` (Cloud Run sets this).
- Uvicorn uses `--proxy-headers` so HTTPS URLs behind Google’s load balancer stay correct.
- Crawl `timeout` in JSON is capped between **1** and **120** seconds (`crawler/schemas.py`).
