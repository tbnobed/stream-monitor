# OTT Stream Monitor — API (FastAPI) image
# Build context is the repository root (see deploy/docker-compose.yml).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies:
#   ffmpeg  -> device/HLS workers (blackdetect/freezedetect/silencedetect, ffprobe)
#   libsrtp2/libopus/libvpx -> runtime libs used by aiortc (WebRTC probe in device_worker)
#   curl    -> container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsrtp2-1 \
        libopus0 \
        libvpx7 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY artifacts/api-server/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI backend source.
COPY artifacts/api-server/backend/ ./

# Wait-for-db entrypoint, then run uvicorn (no --reload in production).
COPY deploy/api/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080

# Bind to loopback only. With host networking, nginx (also host-networked) reaches
# the API at 127.0.0.1:8080, while the LAN cannot hit the backend directly — nginx
# stays the single ingress. Device control is all OUTBOUND, so loopback binding
# does not affect remote-control reachability.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080", "--log-level", "info"]
