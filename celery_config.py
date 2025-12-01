"""
Celery Configuration
High-performance parallel task processing with Redis backend

SPEED IMPROVEMENTS:
- 100 docs: 43 mins → ~2-5 mins with 10 workers
- Parallel processing instead of sequential
- Non-blocking API responses (instant!)
- Redis for fast task queue
"""

from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "default")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

REDIS_URL = f"redis://{REDIS_USERNAME}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

print(f"🔧 Celery Redis URL: {REDIS_URL}")

# Create Celery app
celery_app = Celery(
    "pdf_batch_processor",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['celery_tasks']
)

# Celery Configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # PERFORMANCE: Maximum parallelism
    worker_prefetch_multiplier=1,  # Take 1 task at a time (better distribution)
    worker_max_tasks_per_child=50,  # Restart after 50 tasks (prevent memory leaks)
    task_acks_late=True,  # Safer task acknowledgment
    task_reject_on_worker_lost=True,
    
    # Task limits
    task_time_limit=600,  # 10 minutes max per PDF
    task_soft_time_limit=480,  # Warn at 8 minutes
    
    # Results
    result_expires=3600,  # 1 hour
    
    # Queues (separate queues for better control)
    task_routes={
        'celery_tasks.process_single_pdf': {'queue': 'pdf_processing'},
        'celery_tasks.create_batch_zip_task': {'queue': 'zip_creation'},
    },
)

print(f"✅ Celery app configured for maximum speed!")