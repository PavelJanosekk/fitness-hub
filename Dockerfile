# syntax=docker/dockerfile:1

# ---- Minimal ffmpeg: only what app/services/audio.py needs (webm/mp4/ogg in, 16 kHz mono FLAC out) ----
# Debian's ffmpeg package adds ~450 MB; this build is a few MB. Same base image as `base`, so glibc matches.
# Source checked against the FFmpeg release signing key (FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8)
# and pinned by sha256 below. To bump: verify the new tarball's .asc the same way, then update URL + checksum.
FROM python:3.13-slim AS ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential xz-utils \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3 \
    https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz /tmp/ffmpeg.tar.xz
WORKDIR /tmp/ffmpeg
RUN tar xf /tmp/ffmpeg.tar.xz --strip-components=1 \
    && ./configure \
        --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug \
        --disable-ffplay --disable-ffprobe --disable-avdevice --disable-swscale --disable-x86asm \
        --enable-protocol=pipe,file \
        --enable-demuxer=matroska,mov,ogg,wav,mp3,aac,flac \
        --enable-parser=opus,vorbis,aac,flac,mpegaudio \
        --enable-decoder=opus,vorbis,aac,mp3float,flac,pcm_s16le,pcm_f32le \
        --enable-encoder=flac --enable-muxer=flac \
        --enable-filter=aresample,aformat,anull \
    && make -j"$(nproc)" ffmpeg \
    && strip ffmpeg

# ---- Python base: runtime dependencies only ----
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY --from=ffmpeg /tmp/ffmpeg/ffmpeg /usr/local/bin/ffmpeg
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
