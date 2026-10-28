# BulkForm — Project Guidelines & Architecture

## Overview
BulkForm is an automated PDF form-filling platform designed to take static PDF forms (tax documents, visa applications, HR packets, lease agreements, etc.) and accurately map and populate fields using an adaptive 150×150 grid coordinate system at 300 DPI.

## Tech Stack & Architecture
- **Language & Runtime:** Python 3.12+ managed via `uv`
- **Web Framework:** FastAPI (`app.py`), running via Uvicorn
- **Rate Limiting & Security:** `slowapi` (`limiter.py`), Fernet grid/payload encryption (`utils/encryption.py`), HTTP Basic Auth for protected `/docs` and `/redoc` in production
- **PDF & Image Processing:** Pillow (PIL), `pdf2image` (Poppler), `img2pdf`, `reportlab`
- **Async Queue & Caching:** Celery (`celery_config.py`, `celery_tasks.py`) backed by Redis for parallel batch PDF generation and Redis caching for templates (`services/template_cache.py`)
- **Database, Auth & Storage:** Supabase (PostgreSQL with RLS, Supabase Auth with Google OAuth PKCE and email/password, Supabase Storage buckets `pdfs` and `blog-covers`)
- **Billing & Subscriptions:** Stripe (webhooks, subscriptions, pay-as-you-go packs, template purchases, library pass)
- **Deployment:** Render (`render.yaml`, `Dockerfile` for FastAPI, `worker.Dockerfile` for Celery)

## Key Project Structure
- `app.py`: Main FastAPI entrypoint with lifecycle hooks, middleware, rate limiter, and router inclusions.
- `main.py`: Single-script standalone CLI prototype for coordinate grid mapping and PDF filling.
- `celery_config.py` & `celery_tasks.py`: Celery broker setup and distributed tasks for parallel PDF generation (`chord` pipeline) and ZIP packaging.
- `routes/`:
  - `auth/`: `basic_auth.py`, `token_auth.py`, `password_auth.py`, `google_auth.py`, `email_confirmation.py`
  - `pdf_routes.py`: PDF uploads, grid generation, single/batch coordinate fill, image/signature insertion, export
  - `template_routes.py`: Standard and repeated template management (custom user templates & official templates)
  - `batch/`: CSV batch creation, parallel job processing triggers, status polling, and zip downloads
  - `payment_routes.py`: Stripe checkout sessions (subscriptions, PAYG, library pass) and webhook handlers
  - `presets_routes.py`: Reusable user profile/form data presets
  - `image_routes.py`: Asset storage for stamps, signatures, and logos
  - `blog_routes.py`: Content endpoints and automated cover image generation
  - `portal_routes.py`: Public intake portals, login-free submissions, and continuous CSV/Excel live data feeds
- `services/`: Encapsulated domain logic (`pdf_processor.py`, `template_service.py`, `batch_service.py`, `entitlement_service.py`, `payment_service.py`, `csv_processor.py`, `image_service.py`, `preset_service.py`, `blog_service.py`, `session_service.py`, `portal_service.py`)
- `models/`: Pydantic request/response schemas for all modules (`pdf_models.py`, `template_models.py`, `batch_models.py`, `portal_models.py`, etc.)

## Development & Run Commands
- **Install dependencies:** `uv sync`
- **FastAPI server:** `uv run uvicorn app:app --reload`
- **Celery worker:** `uv run celery -A celery_config worker --loglevel=info --concurrency=10 -Q pdf_processing,zip_creation,celery -E`
