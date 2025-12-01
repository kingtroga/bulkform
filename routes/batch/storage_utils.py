"""
Storage Utilities - Supabase Storage Download with Retries
Robust download functions with retry logic and caching
"""

import os
import time
import random
import threading
from typing import Optional

from services.supabase_client import init_supabase, get_supabase


# ============================================================================
# GLOBAL CACHE AND STATE
# ============================================================================

_STORAGE_BYTES_CACHE = {}
_STORAGE_BYTES_LOCK = threading.Lock()
_SUPABASE_ENV_LOGGED = False  # avoid noisy repeated logs


# ============================================================================
# DOWNLOAD WITH RETRIES
# ============================================================================

def download_with_retries(
    supabase_client,
    bucket: str,
    storage_path: str,
    *,
    max_attempts: int = 5,
    base_delay: float = 0.25,
    template_hint: Optional[str] = None
) -> bytes:
    """
    Robust download for Supabase Storage with:
    - path normalization
    - parent prefix listing for existence check
    - exponential backoff + jitter on 404/edge errors
    - in-process memoization cache
    - automatic client refresh on 404 errors
    """
    # Detect accidental signed URL in pdf_url field
    if storage_path.startswith("http://") or storage_path.startswith("https://"):
        raise Exception(
            f"Template pdf_url looks like a URL, expected storage path (got: {storage_path[:80]}...)"
        )

    path = _normalize_storage_path(storage_path)
    cache_key = f"{bucket}:{path}"

    # Cache hit?
    with _STORAGE_BYTES_LOCK:
        if cache_key in _STORAGE_BYTES_CACHE:
            print(f"🧠 Cache hit for {cache_key}")
            return _STORAGE_BYTES_CACHE[cache_key]

    # Pre-list the parent prefix once (helps with read-after-write and path typos)
    prefix = "/".join(path.split("/")[:-1])
    fname = path.split("/")[-1]
    
    current_client = get_supabase()
    
    try:
        listing = current_client.storage.from_(bucket).list(prefix)
        names = [obj.get("name") for obj in listing]
        print(f"📂 Listing '{prefix}' → {names[:20]}")
        if fname not in names:
            print("⚠️ Exact filename not found in prefix listing (may be case/space mismatch or eventual consistency).")
    except Exception as e:
        print(f"⚠️ Could not list prefix '{prefix}': {e}")

    # Retry loop
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"⬇️  download() attempt {attempt}/{max_attempts} → {bucket}/{path}")
            
            current_client = get_supabase()
            pdf_bytes = current_client.storage.from_(bucket).download(path)
            
            print(f"✅ download() ok → {len(pdf_bytes)} bytes")
            with _STORAGE_BYTES_LOCK:
                _STORAGE_BYTES_CACHE[cache_key] = pdf_bytes
            return pdf_bytes
        except Exception as e:
            last_err = e
            msg = str(e)
            is_404 = "404" in msg or "not_found" in msg.lower()
            print(f"❌ download() failed (attempt {attempt}): {msg}")

            # CORE FIX: If 404 is detected, refresh the client for the next retry
            if is_404 and attempt < max_attempts:
                print(f"🔄 Detected 404/not_found error. Reinitializing global Supabase client...")
                init_supabase()
                
            # On the last attempt, dump env/role once to help spot RLS/env issues quickly
            if attempt == max_attempts and is_404:
                _log_supabase_env_once(current_client)

            # Backoff before retrying (only if more attempts remain)
            if attempt < max_attempts:
                # Tiny re-list to help with consistency checks
                try:
                    listing = current_client.storage.from_(bucket).list(prefix)
                    names = [obj.get("name") for obj in listing]
                    print(f"🔎 Retrying, current '{prefix}' listing → {names[:20]}")
                except Exception as e2:
                    print(f"⚠️ Could not re-list prefix before retry: {e2}")

                sleep_s = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.15)
                print(f"⏳ Backoff {sleep_s:.2f}s before retry...")
                time.sleep(sleep_s)
            else:
                break

    # Out of attempts
    hint = f" | template={template_hint}" if template_hint else ""
    raise Exception(f"storage download 404/failed after {max_attempts} attempts for '{bucket}/{path}'{hint}: {last_err}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _normalize_storage_path(raw_path: str) -> str:
    """Normalize storage path by stripping leading slashes"""
    return (raw_path or "").strip().lstrip("/")


def _log_supabase_env_once(supabase_client):
    """Log Supabase environment details once for debugging"""
    global _SUPABASE_ENV_LOGGED
    if _SUPABASE_ENV_LOGGED:
        return
    _SUPABASE_ENV_LOGGED = True
    try:
        import re, jwt
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        proj = ""
        m = re.search(r"https://([a-z0-9\-]+)\.supabase\.co", url)
        if m: proj = m.group(1)
        role = "unknown"
        try:
            claims = jwt.decode(key, options={"verify_signature": False})
            role = claims.get("role", role)
        except Exception:
            pass
        print(f"🌍 Supabase env: url={url} project_ref={proj} key_len={len(key)} role={role}")
    except Exception as e:
        print(f"⚠️ Could not log Supabase env: {e}")


# ============================================================================
# ASYNC DOWNLOAD (Optional)
# ============================================================================

async def download_pdf_bytes(url: str) -> bytes:
    """Download PDF from URL or storage path"""
    import httpx
    from services.pdf_processor import PDFProcessor
    
    # If it's an HTTP(S) URL, fetch over network
    if url.lower().startswith(("http://", "https://")):
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    
    # Otherwise, treat as Supabase storage path in the configured bucket
    pdf_processor = PDFProcessor()
    return pdf_processor.supabase.storage.from_(pdf_processor.STORAGE_BUCKET).download(url)