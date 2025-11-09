# BulkForm
```
██████╗ ██╗   ██╗██╗     ██╗  ██╗███████╗ ██████╗ ██████╗ ███╗   ███╗
██╔══██╗██║   ██║██║     ██║ ██╔╝██╔════╝██╔═══██╗██╔══██╗████╗ ████║
██████╔╝██║   ██║██║     █████╔╝ █████╗  ██║   ██║██████╔╝██╔████╔██║
██╔══██╗██║   ██║██║     ██╔═██╗ ██╔══╝  ██║   ██║██╔══██╗██║╚██╔╝██║
██████╔╝╚██████╔╝███████╗██║  ██╗██║     ╚██████╔╝██║  ██║██║ ╚═╝ ██║
╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝
```

**Making the tedious automatic.**

---

## What This Does

Takes static PDF forms (like T4s, visa applications, HR docs) and fills them automatically using a grid-based coordinate system.

**No more manual data entry.**

---

## Current Status

**Production-Ready API** - Deployed & Scalable

### ✅ **Core Features**
- PDF to image conversion (300 DPI)
- 150×150 grid overlay system
- Precise text/image/signature placement
- Multi-page document support
- Async processing (30 workers)
- Session persistence

### ✅ **Authentication**
- Email/Password signup/signin
- Google OAuth (PKCE)
- JWT tokens + refresh
- Password reset flow
- User profiles + roles

### ✅ **Template System**
- Custom user templates
- Official BulkForm templates
- Field mapping validation
- Template categories
- Redis caching (99% hit rate)

### ✅ **Batch Processing**
- CSV to 100+ filled PDFs
- Celery workers (parallel)
- 4-5 min for 100 PDFs (was 43 min!)
- Real-time progress tracking
- ZIP download
- Template caching

### 🚧 **In Progress**
- Payment integration (Stripe/Paystack)
- Usage tracking & limits
- Subscription management

---

---

## Tech Stack

**Backend:**
- FastAPI (async endpoints)
- Celery + Redis (background jobs)
- ThreadPoolExecutor (30 workers)
- Python 3.11+

**Processing:**
- Pillow (PIL) - image manipulation
- ImageFont - text rendering
- ImageDraw - drawing operations
- pdf2image (PDF conversion)
- img2pdf (image to PDF)

**Infrastructure:**
- Supabase (auth + database + storage)
- Redis (caching + job queue)
- Render (deployment)
- Row-Level Security (RLS)

**Performance:**
- 10-20x speedup (parallel processing)
- 99% template cache hit rate
- Non-blocking async I/O
- <1ms Redis reads

---

## Architecture Highlights

### Async Everything
```
Upload → Convert → Grid → Fill → Generate
   ↓        ↓       ↓      ↓        ↓
 Async    Async   Async  Async   Async
(ThreadPool for CPU-intensive work)
```

### Parallel Batch Processing
```
100 PDFs → 10 Celery Workers → 5 minutes
(Sequential would take 43 minutes)
```

### Template Caching
```
Worker 1: DB query (50ms)
Workers 2-100: Redis cache (1ms each)
Total: 150ms instead of 5000ms (97% faster)
```

---

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Create account
- `POST /api/auth/signin` - Login
- `POST /api/auth/refresh` - Refresh token
- `GET /api/auth/google` - OAuth flow
- `POST /api/auth/password-reset` - Reset password

### PDF Processing
- `POST /api/pdf/upload` - Upload + grid
- `POST /api/pdf/fill-text` - Fill single page
- `POST /api/pdf/fill-text-batch` - Fill multiple pages (parallel)
- `POST /api/pdf/add-image` - Add images/stamps/signatures
- `POST /api/pdf/generate` - Create final PDF
- `GET /api/pdf/download/{id}` - Download filled PDF

### Templates
- `POST /api/templates` - Create custom template
- `GET /api/templates` - List user templates
- `GET /api/templates/{id}` - Get template (cached)
- `GET /api/templates/official/list` - Official templates

### Batch Processing
- `POST /api/batch/create-from-csv` - Upload CSV
- `POST /api/batch/{id}/process` - Start batch (Celery)
- `GET /api/batch/{id}/progress` - Real-time progress
- `GET /api/batch/{id}/download` - Download ZIP

---

## Quick Start (Development)
```bash
# Install dependencies
uv pip install -r requirements.txt

# Set environment variables
export SUPABASE_URL=your_url
export SUPABASE_KEY=your_key
export REDIS_URL=redis://localhost:6379/0

# Start Redis
redis-server

# Terminal 1: FastAPI
uv run uvicorn main:app --reload

# Terminal 2: Celery Worker
uv run celery -A celery_config worker --loglevel=info --concurrency=10 -Q pdf_processing,zip_creation,celery -E
```

---

## Deployment

**Hosted on:**
- Render (FastAPI backend) *PENDING*
- Supabase (database + storage) *PENDING*
- Redis Cloud (caching + jobs) *PENDING*

**Environment:**
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_key
REDIS_URL=redis://...
OAUTH_CALLBACK_URL=https://api.bulkform.io/api/auth/google/callback
```

---

## Target Market

**Primary:**
- Immigration paralegals (50-200 forms/month)
- HR departments (onboarding packets)
- Small law firms (court forms)
- Real estate agents (lease agreements)
- Tax preparers (seasonal volume)

**Pricing:**
- Starter: $49/month (500 forms)
- Professional: $99/month (2,000 forms)
- Business: $199/month (10,000 forms)
- Enterprise: Custom

---

## Project Structure
```
bulkform/
├── routes/
│   ├── auth/          # Authentication
│   ├── pdf/           # PDF processing
│   ├── templates/     # Template management
│   └── batch/         # Batch processing
├── services/
│   ├── auth_service.py
│   ├── template_service.py
│   ├── batch_service.py
│   └── template_cache.py
├── models/
├── celery_tasks.py
├── celery_config.py
├── main.py
└── docs/
    ├── AUTH_GUIDE.md
    ├── BATCH_ARCHITECTURE.md
    ├── PDF_ARCHITECTURE.md
    └── TEMPLATE_ARCHITECTURE.md
```

--


## How It Works

1. **Load PDF** → Convert pages to images
2. **Apply Grid** → Overlay 150×150 coordinate system
3. **Map Fields** → User specifies grid coordinates for each field
4. **Fill Forms** → Place text at exact positions
5. **Export** → Generate filled PDF

---

## Target Market

- Immigration paralegals
- HR departments (onboarding)
- Small law firms
- Real estate agents
- Tax preparers

**Anyone filling 50+ PDF forms per month.**

---

## Goal

**10 paying customers by December 31, 2025**

Revenue target: $1,000/month

**Current Status:**
- API: Production-ready ✅
- Auth: Complete ✅
- Processing: Optimized ✅
- Payments: In progress 🚧
---

## Notes to Self

- Keep it simple - no over-engineering
- Ship fast, iterate based on real feedback
- Build → Test → Ship → Repeat
- Revenue > Engagement
- Customers > Followers

---

**Last Updated:** November 8, 2025  
**Status:** Production-ready, adding payments  
**Built by:** Solo founder, remote from Nigeria 🇳🇬