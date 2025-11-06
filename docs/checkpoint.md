# README: Supabase Storage 404 Issue & Hypothetical Fix

## Problem Summary

During batch PDF generation, template downloads from Supabase Storage intermittently fail with the following error:

```
❌ Download failed from primary bucket 'pdfs': {'statusCode': 404, 'error': 'not_found', 'message': 'Object not found'}
```

This happens even though:

* The `pdf_url` path exists in the Supabase dashboard.
* The same object downloads successfully in production.
* The issue appears randomly and inconsistently during background task processing (especially locally).

### Symptoms

* The same template file works for some items, fails for others.
* Retries on a new run sometimes succeed without any changes.
* The error logs show no consistent pattern in failed object paths.
* Production environment (using service key) behaves normally.

### Observations

* Supabase’s Python client occasionally returns `404` for valid paths during prolonged sessions or background jobs.
* The issue does **not** persistently affect the same object, which implies it’s not a true file-not-found error.
* The failures disappear when the Supabase client is freshly reinitialized or when a new session key is used.

### Probable Cause

1. **Supabase Storage session or token expiration**:
   Background tasks use a stale `anon` or `service` client initialized hours earlier. When it expires or loses access to the storage policy, the client silently fails with a 404 instead of 403.

2. **Temporary CDN or storage cache inconsistency**:
   Sometimes the object store behind Supabase (S3-compatible) lags replication. A retry often fixes it, which aligns with this theory.

3. **Local vs. production environment mismatch**:

   * Local uses `anon` key → subject to Row-Level Security (RLS).
   * Production uses `service_role` key → bypasses RLS.
     This mismatch explains why production never fails.

4. **Long-lived Supabase client reuse**:
   The same client instance persists across multiple asynchronous or threaded operations. When one loses connection or token context, subsequent calls fail.

---

## Hypothesis for Fix

Reinitializing the Supabase client for each **batch process** and retrying failed template downloads will:

* Refresh authentication and network state.
* Ensure the latest storage policy context applies.
* Remove session-level caching or stale headers.
* Prevent poisoned client instances from affecting future downloads.

### Strategy Overview

1. **Recreate all Supabase service clients at batch start.**

   * Destroy old singleton/service instances.
   * Instantiate new `supabase.Client()` objects with fresh credentials.

2. **Implement backoff + client refresh on storage 404/401.**

   * If `.download()` fails with 404 or 401, rebuild the client and retry.
   * Retry up to 3–4 times with exponential backoff (0.5s, 1s, 2s, 4s).

3. **Optionally, refresh clients between each item on repeated 404s.**

   * Ensures per-item isolation for large batches.

4. **Add `retry_failed_items` endpoint.**

   * Allows reprocessing previously failed items after client restart.

---

## Implementation Summary

### a) New `make_services_fresh()` factory

Creates a **fresh Supabase client** and all dependent services:

```python
def make_services_fresh():
    supabase_client = create_supabase_client(
        url=os.getenv("SUPABASE_URL"),
        key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"),
    )
    return {
        "supabase": supabase_client,
        "batch": BatchService(supabase_client),
        "template": TemplateService(supabase_client),
        "pdf_proc": PDFProcessor(),
        "image": get_image_service()
    }
```

### b) Retry wrapper for template download

```python
def download_template_with_retries(pdf_proc, bucket, path, refresh_client):
    for attempt in range(4):
        try:
            return pdf_proc.supabase.storage.from_(bucket).download(path)
        except Exception as e:
            if "404" in str(e) or "not_found" in str(e):
                refresh_client()
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise
    raise Exception("Template download failed after retries")
```

### c) Batch worker changes

* On batch start: call `make_services_fresh()`.
* On each item failure: rebuild services before continuing.
* Use retry wrapper for all Supabase storage calls.

---

## Expected Outcome

✅ Reduced intermittent 404s from Supabase Storage.
✅ Automatic recovery from stale or expired client sessions.
✅ Retry mechanism ensures stable batch completion.
✅ Local and production behavior become consistent.

---

## Future Improvements

* Switch storage to Cloudflare R2 or Backblaze B2 for consistent S3 endpoints.
* Cache template files locally after first successful download per batch.
* Add structured metrics (e.g., retry count, latency, error frequency) to logs.
* Eventually move to a service-layer abstraction that auto-refreshes the Supabase client internally.

---

### TL;DR

The 404 issue isn’t missing files — it’s **stale Supabase clients** or **auth drift** in background tasks. Restarting the client and adding a retry layer with client refresh between failed downloads stabilizes everything.
