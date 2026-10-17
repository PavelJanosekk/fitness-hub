# syntax=docker/dockerfile:1

# ---- Python base: runtime dependencies only ----
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# ffmpeg transcodes browser recordings (webm/mp4) for Gemini (app/services/audio.py)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

# ---- Dev: + test/lint tools; code is bind-mounted, uvicorn reloads on change ----
FROM base AS dev
COPY backend/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt -c constraints.txt
# Runs as the host user (see docker-compose.dev.yml), which has no home directory in the image
ENV HOME=/tmp \
    RUFF_CACHE_DIR=/tmp/ruff-cache
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

# ---- Frontend build (React + Vite) ----
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Prod: API + built SPA in one image ----
FROM base AS prod
RUN useradd --system --uid 10001 --no-create-home app
COPY backend/ ./
COPY --from=frontend /frontend/dist /app/static
ENV STATIC_DIR=/app/static
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
