# Voice AI Studio Arabic - Production Dockerfile v3.0
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 libgomp1 git wget curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY requirements-linux.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-linux.txt || true

COPY . .
RUN mkdir -p uploads outputs cache logs models voices downloads config datasets temp

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["python", "main.py"]
