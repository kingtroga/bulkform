# worker.Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Copy application code
COPY . .

# ONLY run Celery worker (same command from your start.sh)
CMD ["uv", "run", "celery", "-A", "celery_config", "worker", "--loglevel=info", "--concurrency=10", "-Q", "pdf_processing,zip_creation,celery", "-E"]