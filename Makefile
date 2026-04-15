.PHONY: run dev test lint format install install-dev docker-build docker-run clean

# ── local dev ──────────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt

run:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

dev: install-dev run

# ── tests ──────────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-fast:
	pytest tests/ -q

test-coverage:
	pytest tests/ --cov=crawler --cov-report=term-missing -q

# ── linting / formatting ───────────────────────────────────────────────────────

lint:
	ruff check crawler/ tests/

format:
	ruff format crawler/ tests/

check: lint test

# ── docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker build -t webcrawler .

docker-run:
	docker run --rm -p 8080:8080 -e PORT=8080 webcrawler

docker-run-redis:
	docker run --rm -p 8080:8080 \
		-e PORT=8080 \
		-e REDIS_URL=redis://host.docker.internal:6379 \
		webcrawler

# ── cloud run ─────────────────────────────────────────────────────────────────

# usage: make gcp-deploy PROJECT_ID=my-project REDIS_URL=rediss://...
PROJECT_ID ?= your-project-id
REGION     ?= us-central1
IMAGE      := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/webcrawler-repo/webcrawler:latest

gcp-build:
	gcloud builds submit --tag $(IMAGE) .

gcp-deploy:
	gcloud run deploy webcrawler \
		--image $(IMAGE) \
		--platform managed \
		--region $(REGION) \
		--allow-unauthenticated \
		--port 8080 \
		--memory 1Gi \
		--cpu 2 \
		--min-instances 0 \
		--max-instances 10 \
		--concurrency 80 \
		--timeout 120 \
		--set-env-vars="REDIS_URL=$(REDIS_URL),CACHE_TTL=3600,CACHE_MAX=500,CORS_ORIGINS=*"

gcp-push: gcp-build gcp-deploy

# ── cleanup ───────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
