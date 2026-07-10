# Voice AI Studio Arabic - Docker Image
# Compatible: Python 3.9 - 3.11 | Linux

FROM python:3.11-slim

# Security: Run as non-root user
RUN groupadd -r voiceai && useradd -r -g voiceai -s /bin/false voiceai

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=voiceai:voiceai . .

# Create required directories
RUN mkdir -p uploads outputs cache logs models voices downloads config \
    && chown -R voiceai:voiceai /app

# Switch to non-root user
USER voiceai

# Expose the correct port (must match APP_PORT)
EXPOSE 8000

# Environment variables
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV APP_DEBUG=false
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run application
CMD ["python", "main.py"]
