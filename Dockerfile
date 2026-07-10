FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-linux.txt .
RUN pip install --no-cache-dir -r requirements-linux.txt

COPY . .

RUN mkdir -p uploads outputs cache logs models voices downloads config

EXPOSE 7860

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

CMD ["python", "main.py"]
