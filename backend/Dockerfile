# syntax=docker/dockerfile:1

# ---- base: system libraries and locked Python dependencies (no application code) ----
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# WeasyPrint (PDF of the signal card) needs pango; fonts must contain Cyrillic.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 \
        fonts-dejavu-core fonts-liberation shared-mime-info \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

# ---- browser: Chromium for Playwright captures and Tesseract for OCR (before the code, so code changes keep
# these layers) ----
FROM base AS browser
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*
# One Tesseract thread per task: the worker already runs several tasks at once.
ENV OMP_THREAD_LIMIT=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-kaz \
    && rm -rf /var/lib/apt/lists/*

# ---- api (also used by beat) ----
FROM base AS api
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- worker ----
FROM browser AS worker
COPY --chown=app:app . .
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO"]
