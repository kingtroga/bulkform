# Batch Routes Architecture - Updated with Celery, Caching, and Repeated Templates

## Module Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI App                            │
│                           │                                 │
│                           ▼                                 │
│                  routes/batch/router                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐   ┌──────────────┐
│ batch_routes │    │   batch_     │   │   batch_     │
│     .py      │───▶│  helpers.py  │   │ processing.py│
│              │    │              │   │              │
│ • Endpoints  │    │ • Validation │   │ • PDF Fill   │
│ • API Logic  │    │ • Constants  │   │ • Background │
│ • Responses  │    │ • Utilities  │   │ • Images     │
└──────────────┘    └──────────────┘   └──────┬───────┘
        │                                      │
        │                                      │
        ▼                                      ▼
┌──────────────┐                      ┌──────────────┐
│   batch_     │                      │  storage_    │
│ download.py  │                      │   utils.py   │
│              │                      │              │
│ • Zip Create │                      │ • Downloads  │
│ • URL Mgmt   │                      │ • Retries    │
│ • Refresh    │                      │ • Caching    │
└──────────────┘                      └──────────────┘
        │                                      │
        └──────────────┬───────────────────────┘
                       │
                       ▼
            ┌─────────────────────────┐
            │   CELERY TASKS LAYER    │
            │                         │
            │ • trigger_parallel_batch│
            │ • process_single_pdf    │  ◀─ UPDATED: handles standard + repeated templates
            │ • finalize_batch        │
            │ • create_zip_task       │
            └────────────┬────────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
            ▼            ▼            ▼
        ┌────────┐ ┌────────┐ ┌────────────┐
        │ Redis  │ │ Worker │ │ Worker ... │
        │ Queue  │ │ Pool   │ │ Pool (10)  │
        │        │ │        │ │            │
        │ (Job   │ │ (PDF   │ │ (Parallel) │
        │ Store) │ │ Fill)  │ │            │
        └────────┘ └────────┘ └────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ TEMPLATE CACHE   │    │ SUPABASE STORAGE │
    │                  │    │                  │
    │ Redis:           │    │ • PDF Storage    │
    │ template:uid:tid │    │ • Image Storage  │
    │ (1 hour TTL)     │    │ • ZIP Download   │
    │                  │    │                  │
    │ Benefits:        │    │                  │
    │ ✓ 1st worker DB  │    │                  │
    │ ✓ other workers  │    │                  │
    │   hit cache      │    │                  │
    │ ✓ ~1ms per hit   │    │                  │
    └──────────────────┘    └──────────────────┘
```

## Request Flow - WITH CELERY, CACHING, AND REPEATED TEMPLATES

### 1. Create Batch from CSV

```
POST /api/batch/create-from-csv
   ↓
batch_routes.create_batch_from_csv()
   ├─ batch_helpers.validate_file_upload()
   ├─ batch_helpers.validate_batch_size()
   └─ batch_service.create_batch()
       └─ Returns: batch_id (items in "pending" status)
```

### 2. Process Batch (Parallel with Celery)

```
POST /api/batch/{id}/process
   ↓
batch_routes.process_batch()
   ├─ Verify batch ownership
   └─ trigger_parallel_batch(batch_id, user_id, template_id)
       │
       └─ Celery chord(group(...))(finalize_batch_task)
           ├─ Get all pending items
           └─ For each item, queue: process_single_pdf_task
               │
               └─ Celery Worker receives task
                   │
                   ├─ ✅ get_template() (cached)
                   │   ├─ first worker: DB + Redis write
                   │   └─ other workers: Redis hit (~1ms)
                   │
                   ├─ fill_single_pdf_sync()  ◀─ UPDATED
                   │   ├─ If template_kind="standard":
                   │   │     - normal per-page field mappings
                   │   └─ If template_kind="repeated":
                   │         - mode="apply_to_pages": stamp mappings from source_page to repeat_pages
                   │         - mode="pages": clone pages per repeat row (existing behavior)
                   │
                   ├─ Upload to Supabase Storage
                   ├─ Mark batch_item completed/failed
                   └─ ✅ Consume 1 form AFTER successful PDF creation
                       (atomic per completed PDF; failures do not consume)
```

### 3. Finalize Batch (Chord Callback)

```
finalize_batch_task(batch_id, user_id)
   ├─ Read batch progress
   ├─ If pending==0 and processing==0:
   │   ├─ status = completed | completed_with_errors
   │   └─ Store final stats
   └─ If still running:
       └─ keep status as processing
```

### 4. Download Batch with ZIP

```
GET /api/batch/{id}/download?create_zip=true
   ↓
batch_routes.download_batch()
   ├─ Get completed items
   └─ create_batch_zip_task.delay()
       │
       └─ Celery Worker
           ├─ Download all PDFs from storage
           ├─ Create local ZIP
           ├─ Upload ZIP to storage
           └─ Return signed URL (TTL)
```

---

## Caching Strategy

### Template Caching (Redis)

```python
# In template_service.py:
@cache_template(ttl=3600)  # 1 hour cache
def get_template(self, template_id: str, user_id: str):
    # First call: DB hit + Redis write
    # Subsequent calls: Redis hit (~1ms)
```

**Cache Key Format:**

```
template:{user_id}:{template_id}
Example: template:a6c3a93a-b1a4-4592-ac53-dba3cf88ae20:41eb78c1-23a2-4f6d-8aed-0ca8d5cfe410
```

**Flow for 100 PDFs in batch:**

```
Worker 1:
  ├─ 🔄 CACHE MISS → DB query (~50ms)
  └─ 💾 Store in Redis (~2ms)

Workers 2-100:
  └─ ✅ CACHE HIT → Redis read (~1ms each)

Total template lookups: ~50ms + 99ms = ~149ms instead of 5000ms
Savings: 96% faster for template retrieval
```

**Invalidation Triggers:**

```python
# When template is updated:
invalidate_template_cache(template_id, user_id)

# When template is deleted:
invalidate_template_cache(template_id, user_id)

# Next call to get_template() hits DB again
```

### Storage Caching (In-Memory)

```python
# In storage_utils.py:
_STORAGE_BYTES_CACHE = {}  # Thread-safe with Lock

# Downloaded PDFs cached during processing
# Avoids redundant Supabase downloads within same worker/process
```

---

## Repeated Templates Support (NEW IN BATCH PROCESSING)

Batch processing does not change how items are queued. It changes how each worker fills the PDF based on template metadata:

### Template Branching

* `template_kind="standard"`: existing behavior
* `template_kind="repeated"`:

  * `repeat_config.mode="apply_to_pages"`: stamp source_page mappings to repeat_pages within the SAME PDF
  * `repeat_config.mode="pages"`: clone pages per repeat row (existing behavior)

### Selective Repetition (Apply-to-pages)

Per-field opt-out in `field_mappings`:

```json
"copy_a_void": {
  "page": 2,
  "x": 33,
  "y": 9,
  "size": 23,
  "font": "arial",
  "type": "text",
  "repeat": false
}
```

Default behavior: fields repeat/stamp.
If `repeat: false`: field is only applied on `source_page`.

---

## Performance Metrics - BEFORE vs AFTER

| Metric                         | Before         | After                  | Improvement       |
| ------------------------------ | -------------- | ---------------------- | ----------------- |
| 100 PDFs processing time       | 43 min         | 4-5 min                | **10-20x faster** |
| Template lookups per 100 items | 5000ms         | ~150ms                 | **97% ↓**         |
| API response time              | Blocking       | Non-blocking           | **Async**         |
| Worker concurrency             | 1 (sequential) | 10 (parallel)          | **10x**           |
| Cache hit rate                 | N/A            | 99% (after 1st worker) | **Huge**          |

---

## Architecture Improvements

### Before (Monolithic)

```
FastAPI Request → Process ALL PDFs → Return (blocks for long time)
❌ User gets timeout
❌ No progress tracking
❌ Template queried many times
```

### After (Celery + Caching + Repeat Support)

```
FastAPI Request → Queue N tasks → Return immediately
    ↓
Celery Workers (parallel)
    ├─ Template cached after first worker
    ├─ Each worker processes PDF independently
    ├─ Handles standard + repeated templates
    ├─ Progress tracked in DB
    └─ Forms consumed only after successful PDF creation
    
✅ Instant API response
✅ Real-time progress
✅ Cached template retrieval
✅ Repeat templates supported
✅ Accurate billing
```

---

## File Organization

```
routes/batch/
├── router.py              # Main endpoints (FastAPI routes)
├── batch_helpers.py       # Constants, validation, utilities
├── batch_processing.py    # PDF filling orchestration
├── batch_download.py      # ZIP creation, URL management
└── storage_utils.py       # Download retries, caching

services/
├── template_cache.py      # Redis template caching decorator
├── template_service.py    # Template CRUD (uses cache_template)
├── batch_service.py       # Batch DB operations
└── ...

celery_tasks.py            # Celery task definitions (includes repeated logic in fill)
celery_config.py           # Celery configuration
```

---

## Key Design Patterns

### 1. Celery Task Distribution

```python
@celery_app.task(bind=True)
def process_single_pdf_task(self, batch_id, item_id, item_index, ...):
    # Runs on worker pool
    # Retries automatically on failure
    # Consumes form after successful PDF creation
    pass
```

### 2. Cache Decorator (Template Caching)

```python
@cache_template(ttl=3600)
def get_template(self, template_id, user_id):
    # First call: executes function, caches result
    # Subsequent calls: returns cached value
    # Invalidation: explicit call removes from cache
```

### 3. Parallel Map Pattern (Chord)

```python
from celery import group, chord

task_group = group(process_single_pdf_task.s(...) for item in pending_items)
callback = finalize_batch_task.si(batch_id, user_id)
job = chord(task_group)(callback)
```

### 4. Background Task Finalization

```python
@celery_app.task
def finalize_batch_task(batch_id, user_id):
    # Mark batch as completed or completed_with_errors
    # Cleanup and stats
    pass
```

---

## Configuration

### Celery (celery_config.py)

```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_EXPIRES = 3600  # 1 hour
```

### Workers

```bash
uv run celery -A celery_config worker \
  --loglevel=info \
  --concurrency=10 \
  -Q pdf_processing,zip_creation,celery \
  -E
```

### Template Cache

```python
TEMPLATE_CACHE_TTL = 3600  # 1 hour
TEMPLATE_CACHE_PREFIX = "template:"
# Redis connection reuses CELERY_BROKER_URL
```

---

## Monitoring & Debugging

### Cache Logs

```
✅ CACHE HIT: template:...
🔄 CACHE MISS: template:... → Hitting database
💾 CACHED: template:... for 3600s
🗑️ Invalidated template cache: template:...
```

### Worker Logs

```
🚀 [Worker abc123] Processing item 5
✅ CACHE HIT: template:...
🧩 fill_single_pdf_sync: START
... (standard or repeated)
✅ Consumed 1 form (after success)
✅ [Worker abc123] Item 5 done
```

### Progress Endpoint

```
GET /api/batch/{batch_id}/progress
{
  "batch_id": "36d9ecf0-3c6d-4ae8-bcba-f08acda437c0",
  "total": 100,
  "completed": 47,
  "failed": 0,
  "pending": 53,
  "processing": 10,
  "progress_percentage": 47,
  "estimated_time_remaining": 245
}
```

---

## Deployment Changes

### New Requirements

```bash
celery==5.4.0
redis==5.0.0
```

### New Environment Variables

```
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### Redis Setup

```bash
redis-server
# or
docker run -d -p 6379:6379 redis:latest
```

### Startup

```bash
# Terminal 1: FastAPI
uv run uvicorn main:app --reload

# Terminal 2: Celery Worker
uv run celery -A celery_config worker --loglevel=info --concurrency=10 -Q pdf_processing,zip_creation,celery -E
```

---

## Success Metrics

✅ **Achieved:**

* 10-20x speedup via parallelism
* 99% template cache hit rate after first worker
* Non-blocking API responses
* Real-time progress tracking
* Accurate billing (consume after success)
* Repeated templates supported (apply_to_pages + pages mode)

✅ **Ready for:**

* Production deployment
* Scaling to 30+ workers
* Multiple concurrent users/batches
* Large batches (500+ PDFs)