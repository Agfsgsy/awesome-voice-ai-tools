FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/requirements-all.txt .
RUN pip install --no-cache-dir -r requirements-all.txt

COPY . .

EXPOSE 7860

CMD ["python", "app.py"]
