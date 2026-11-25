FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including ffmpeg for vertical 9:16 video & TTS audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure data directory exists for SQLite database persistence
RUN mkdir -p /app/data /app/web/static/videos /app/web/static/thumbnails /app/web/static/audio

ENV PYTHONUNBUFFERED=1
ENV TEMUAN_DB=/app/data/temuan_harian.db

EXPOSE 8000

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
