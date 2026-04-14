FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4 \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crawler ./crawler
COPY main.py .
COPY static ./static

RUN chown -R app:app /app
USER app

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers '--forwarded-allow-ips=*'"]
