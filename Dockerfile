# syntax=docker/dockerfile:1

# Clipwise: web + cloud API + per-workspace FFmpeg/Whisper engines in one image.

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS deps
WORKDIR /app
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential ffmpeg libglib2.0-0 libgomp1 \
  && rm -rf /var/lib/apt/lists/*
COPY engine/requirements-hosted.txt /app/requirements-hosted.txt
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements-hosted.txt

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    CLIPFORGE_CLOUD_DIR=/data/cloud \
    WEB_DIST=/app/web/dist \
    FFMPEG_BIN=/usr/bin/ffmpeg \
    FFPROBE_BIN=/usr/bin/ffprobe \
    HF_HOME=/data/models \
    WHISPER_MODEL=medium \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE=int8
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates libglib2.0-0 libgomp1 \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --system --uid 10001 --create-home clipwise

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY engine /app/engine
COPY --from=web /web/dist /app/web/dist

RUN mkdir -p /data/cloud /data/models /app/engine/data \
  && chown -R clipwise:clipwise /app /data
USER clipwise

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/public/config', timeout=4)"

CMD ["python", "-m", "uvicorn", "engine.cloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
