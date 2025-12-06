#!/bin/bash
# start.sh

# Start Celery worker in background
uv run celery -A celery_config worker --loglevel=info --concurrency=10 -Q pdf_processing,zip_creation,celery -E &

# Start web server in foreground
uv run uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1