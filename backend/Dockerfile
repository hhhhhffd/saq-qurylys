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
# The Telegram session of the userbot (a volume is mounted here and takes the owner of this directory).
RUN mkdir -p /data/userbot && chown app:app /data/userbot
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- worker ----
FROM browser AS worker
COPY --chown=app:app . .
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO"]

# ---- vision-weights: the detector weights (Apache-2.0), pinned to one revision of the model repository. They are
# baked in at build time and shared by the CPU and GPU images; at run time the worker is offline. The revision is what
# `model_version` of the findings reports. ----
FROM base AS vision-weights
ARG DETECTOR_MODEL=IDEA-Research/grounding-dino-tiny
ARG DETECTOR_REVISION=a2bb814dd30d776dcf7e30523b00659f4f141c71
ENV HF_HOME=/opt/hf
RUN --mount=type=cache,target=/root/.cache/uv uv run --no-project --with huggingface_hub python -c \
    "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], revision=sys.argv[2], ignore_patterns=['*.bin'])" \
    "$DETECTOR_MODEL" "$DETECTOR_REVISION" \
    && mkdir -p /opt/hf/hub/models--$(echo "$DETECTOR_MODEL" | sed 's#/#--#')/refs \
    && printf '%s' "$DETECTOR_REVISION" > /opt/hf/hub/models--$(echo "$DETECTOR_MODEL" | sed 's#/#--#')/refs/main \
    && chmod -R a+rX /opt/hf

# ---- vision-base: ffmpeg (ffprobe included) on top of the worker libraries (before the code, so code changes keep
# these big layers) ----
FROM browser AS vision-base
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=vision-weights /opt/hf /opt/hf
ENV HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1

# ---- vision: the worker image plus ffmpeg and the object detector on CPU. Only the vision images get torch and
# transformers: the api and worker images do not. pyproject.toml and uv.lock are those copied in `base`. ----
FROM vision-base AS vision
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project --extra vision-cpu
COPY --chown=app:app . .
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "-Q", "vision"]

# ---- vision-gpu: the same with CUDA wheels of torch (needs the NVIDIA container runtime; larger image) ----
FROM vision-base AS vision-gpu
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project --extra vision-gpu
COPY --chown=app:app . .
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "-Q", "vision"]
