"""
celery_tasks.py — UPDATED (minimal necessary changes)

✅ What changed (only what we must change):
1) process_upload_session_task now matches pdf_routes.py:
   - args = (session_id, user_id, original_storage_path)
   - Worker downloads original PDF from Supabase Storage (no local path passed)
2) Writes session metadata into pdf_sessions:
   - status: processing -> ready / failed
   - num_pages, pages(jsonb), dpi, grid_size, progress, error_message
3) Stores pages as a plain LIST (NOT {"pages": pages}) so routes can return it directly.

Everything else (batch processing / zip / repeat logic) is left untouched.
"""
#is this code working??
from celery_config import celery_app
from typing import Dict, List, Optional, Set
import time

# Import your existing services
from services.batch_service import get_batch_service
from services.template_service import get_template_service
from services.pdf_processor import PDFProcessor
from services.session_service import SessionService
from services.image_service import get_image_service

import asyncio
import os
import tempfile
import httpx
import zipfile
import gc
import json
import re
import shutil

from utils.storage_utils import download_with_retries

ZIP_TTL_SECONDS = 5 * 60 * 60  # 5 hours


def _safe_json(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return None


# =============================================================================
# REPEAT CONFIG (UNCHANGED)
# =============================================================================

def validate_repeat_config_min(cfg: Dict):
    if not isinstance(cfg, dict):
        raise ValueError("repeat_config must be a dict/object")

    mode = (cfg.get("mode") or "pages").strip().lower()
    if mode not in ("pages", "apply_to_pages"):
        raise ValueError("repeat_config.mode must be 'pages' or 'apply_to_pages'")

    rp = cfg.get("repeat_pages")
    if isinstance(rp, str):
        rp = _safe_json(rp)
    if rp is not None and (not isinstance(rp, list) or not rp):
        raise ValueError("repeat_config.repeat_pages must be a non-empty list")

    if mode == "apply_to_pages":
        sp = cfg.get("source_page")
        if sp is None:
            raise ValueError("repeat_config.source_page is required for apply_to_pages")
        try:
            int(sp)
        except Exception:
            raise ValueError("repeat_config.source_page must be an integer")


def compute_apply_pages(repeat_cfg: Dict, num_pages_src: int) -> List[int]:
    rp = repeat_cfg.get("repeat_pages")
    if isinstance(rp, str):
        rp = _safe_json(rp)
    pages = [int(x) for x in (rp or [])]

    bad = [p for p in pages if p < 1 or p > num_pages_src]
    if bad:
        raise ValueError(f"repeat_pages contains invalid pages {bad}; source PDF has {num_pages_src} pages")

    seen = set()
    out = []
    for p in pages:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def expand_field_mappings_from_source_page(field_mappings: Dict, source_page: int, target_pages: List[int]) -> Dict:
    source_page = int(source_page)
    targets = [int(p) for p in target_pages]

    source = {
        fname: cfg for fname, cfg in (field_mappings or {}).items()
        if int(cfg.get("page", 1)) == source_page
    }
    if not source:
        raise ValueError(f"No field mappings found on source_page={source_page}")

    out = dict(field_mappings or {})

    for p in targets:
        for fname, cfg in source.items():
            should_repeat = cfg.get("repeat", True)
            if should_repeat is False:
                if p == source_page:
                    new_cfg = dict(cfg)
                    new_cfg["page"] = source_page
                    out[fname] = new_cfg
                continue

            new_cfg = dict(cfg)
            new_cfg["page"] = p

            if p == source_page:
                out[fname] = new_cfg
            else:
                stamped_name = f"{fname}__p{p}"
                new_cfg["__client_key__"] = fname
                out[stamped_name] = new_cfg

    return out


def compute_repeat_pages(template: Dict, repeat_cfg: Dict) -> List[int]:
    rp = repeat_cfg.get("repeat_pages")
    if isinstance(rp, str):
        rp = _safe_json(rp)
    if isinstance(rp, list) and rp:
        return [int(x) for x in rp]

    pages = set()
    for _, fc in (template.get("field_mappings") or {}).items():
        pages.add(int(fc.get("page", 1)))
    return sorted(pages) if pages else [1]


def extract_repeat_rows(client_data: Dict, repeat_cfg: Dict) -> List[Dict]:
    r = _safe_json(client_data.get("__repeats__"))
    if isinstance(r, list) and r:
        return [x for x in r if isinstance(x, dict)]

    r = _safe_json(client_data.get("repeats"))
    if isinstance(r, list) and r:
        return [x for x in r if isinstance(x, dict)]

    suffix_re = re.compile(r"^(?P<base>.+?)_(?P<idx>\d+)$")
    buckets: Dict[int, Dict] = {}
    for k, v in (client_data or {}).items():
        if not isinstance(k, str):
            continue
        m = suffix_re.match(k.strip())
        if not m:
            continue
        base = m.group("base").strip()
        idx = int(m.group("idx"))
        if idx <= 0:
            continue
        buckets.setdefault(idx, {})[base] = v

    if not buckets:
        return []

    rows = [buckets[i] for i in sorted(buckets.keys())]
    merge_base = repeat_cfg.get("merge_base_fields", True)

    if merge_base:
        base_defaults = {str(k).strip(): v for k, v in (client_data or {}).items() if not suffix_re.match(str(k).strip())}
        merged = []
        for row in rows:
            d = dict(base_defaults)
            d.update(row)
            merged.append(d)
        return merged

    return rows


def subset_and_remap_field_mappings(field_mappings: Dict, src_page: int, out_page: int) -> Dict:
    out = {}
    for fname, cfg in (field_mappings or {}).items():
        if int(cfg.get("page", 1)) != int(src_page):
            continue
        new_cfg = dict(cfg)
        new_cfg["page"] = int(out_page)
        out[fname] = new_cfg
    return out


def temp_png_path(pdf_processor, session_id: str, page_num: int) -> str:
    return f"{pdf_processor.TEMP_FOLDER}/{session_id}/page_{page_num}.png"


# =============================================================================
# MEMORY MANAGEMENT (UNCHANGED)
# =============================================================================

def force_memory_cleanup():
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


# =============================================================================
# CLEANUP UTILITIES (UNCHANGED)
# =============================================================================

def cleanup_temp_files(temp_pdf_path: str, temp_image_paths: list, session_id: str, pdf_processor):
    if temp_pdf_path and os.path.exists(temp_pdf_path):
        try:
            os.unlink(temp_pdf_path)
            print(f"🧹 Temp PDF removed: {temp_pdf_path}")
        except Exception as e:
            print(f"⚠️  Failed to remove temp PDF {temp_pdf_path}: {e}")

    for img_path in temp_image_paths:
        if os.path.exists(img_path):
            try:
                os.unlink(img_path)
                print(f"🧹 Temp image removed: {img_path}")
            except Exception as e:
                print(f"⚠️  Failed to remove temp image {img_path}: {e}")

    try:
        pdf_processor.cleanup_folders(session_id)
        print(f"🧽 Session folder cleanup done for: {session_id}")
    except Exception as e:
        print(f"⚠️  Session cleanup failed for {session_id}: {e}")

    force_memory_cleanup()


def parse_item_filter(only_param: Optional[str]) -> Optional[Set[int]]:
    if not only_param:
        return None
    indices = set()
    for part in only_param.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                indices.update(range(start, end + 1))
            except ValueError:
                raise ValueError(f"Invalid range: {part}")
        else:
            try:
                indices.add(int(part))
            except ValueError:
                raise ValueError(f"Invalid item index: {part}")
    return indices


# =============================================================================
# FIELD DATA BUILDER (UNCHANGED)
# =============================================================================

def resolve_text_style(field_name: str, client_data: Dict, field_config: Dict, batch_options: Dict):
    pf_font  = client_data.get(f"{field_name}_font")
    pf_size  = client_data.get(f"{field_name}_size")
    pf_align = client_data.get(f"{field_name}_align")

    row_font  = client_data.get("__font__")  or client_data.get("font")
    row_size  = client_data.get("__size__")  or client_data.get("size")
    row_align = client_data.get("__align__") or client_data.get("align")

    b_font  = batch_options.get("default_font")
    b_size  = batch_options.get("default_size")
    b_align = batch_options.get("default_align")

    t_font  = field_config.get("font", "arial")
    t_size  = field_config.get("size", 12)
    t_align = field_config.get("align", "center")

    font  = pf_font or row_font or b_font or t_font or "arial"
    try:
        size = int(pf_size or row_size or b_size or t_size or 12)
    except (TypeError, ValueError):
        size = 12

    align = (pf_align or row_align or b_align or t_align or "center")
    align = str(align).lower()
    if align not in ("top", "center", "bottom"):
        align = "top"
    return font, size, align


def resolve_image_dims(field_name: str, client_data: Dict, field_config: Dict, batch_options: Dict):
    def pick(*keys):
        for k in keys:
            if k in client_data and client_data[k] not in (None, ""):
                return client_data[k]
        return None

    pf_w = pick(f"{field_name}_width", f"{field_name}__width", f"{field_name}_w")
    pf_h = pick(f"{field_name}_height", f"{field_name}__height", f"{field_name}_h")

    row_w = client_data.get("__image_width__")
    row_h = client_data.get("__image_height__")

    img_defaults = (batch_options.get("image_defaults") or {})
    b_w = batch_options.get("default_image_width")  or img_defaults.get("width")
    b_h = batch_options.get("default_image_height") or img_defaults.get("height")

    t_w = field_config.get("width")
    t_h = field_config.get("height")

    def to_int(v, fallback):
        try:
            return int(float(str(v).strip()))
        except Exception:
            return fallback

    width  = to_int(pf_w or row_w or b_w or t_w, 200)
    height = to_int(pf_h or row_h or b_h or t_h, 60)

    print(f"     - resolve_image_dims[{field_name}] -> width={width}, height={height}")
    return width, height


def build_field_data(field_mappings: Dict, client_data: Dict, image_service, user_id: str, temp_image_paths: list, batch_options: Dict = None):
    client_data = {str(k).strip(): v for k, v in client_data.items()}
    pages_data = {}
    images_data = {}
    text_field_count = 0
    image_field_count = 0
    batch_options = batch_options or {}

    print(f"🧭 Iterating field_mappings...")
    for field_name, field_config in field_mappings.items():
        page = field_config.get('page', 1)
        field_type = field_config.get('type', 'text')
        print(f"   • Field '{field_name}' → page={page} type={field_type}")

        client_key = field_config.get("__client_key__") or field_name

        if field_type in ['image', 'signature', 'stamp']:
            image_ref = client_data.get(client_key, '')
            print(f"     - image_ref: {repr(image_ref)[:120]}")
            if image_ref and str(image_ref).strip():
                try:
                    image_path = load_image(image_ref, image_service, user_id, temp_image_paths)

                    if page not in images_data:
                        images_data[page] = []
                    w, h = resolve_image_dims(field_name, client_data, field_config, batch_options)
                    entry = {
                        'image_path': image_path,
                        'x': field_config['x'],
                        'y': field_config['y'],
                        'width': w,
                        'height': h
                    }
                    print(f"     - IMAGE entry for '{field_name}': x={field_config['x']} y={field_config['y']} width={w} height={h}")
                    images_data[page].append(entry)
                    image_field_count += 1
                    print(f"     - Queued image placement: {entry}")
                except Exception as e:
                    print(f"     ❌ Failed to load/place image '{image_ref}': {e}")
            else:
                print(f"     - No image provided in client_data for '{field_name}'")
            continue

        if page not in pages_data:
            pages_data[page] = []

        value = client_data.get(client_key, '')

        if field_type == 'checkbox':
            value = handle_checkbox(value, field_config)

        font_value, size_value, align_value = resolve_text_style(
            field_name, client_data, field_config, batch_options
        )

        value = str(value) if value is not None else ''
        entry = {
            'text': value,
            'x': field_config['x'],
            'y': field_config['y'],
            'size': size_value,
            'font': font_value,
            'align': align_value,
        }

        pages_data[page].append(entry)
        text_field_count += 1
        log_val = value[:77] + "..." if len(value) > 80 else value
        print(f"     - Queued text: {log_val!r} at (x={entry['x']}, y={entry['y']}) "
              f"[font={font_value}, size={size_value}] page={page}")

    return pages_data, images_data, text_field_count, image_field_count


def load_image(image_ref: str, image_service, user_id: str, temp_image_paths: list) -> str:
    if os.path.exists(image_ref):
        print(f"     - Local image found: {image_ref}")
        return image_ref

    print(f"     - Downloading image bytes via image_service for ref='{image_ref}'")
    image_bytes = image_service.download_image_bytes(image_ref, user_id)
    if image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
            tmp_img.write(image_bytes)
            image_path = tmp_img.name
        temp_image_paths.append(image_path)
        print(f"     - Image saved to temp: {image_path} (bytes={len(image_bytes)})")
        return image_path
    raise Exception(f"No image bytes returned for ref='{image_ref}'")


def handle_checkbox(value, field_config: Dict) -> str:
    original = value
    if isinstance(value, bool):
        value = field_config.get('text', '●') if value else ''
    elif value in ['true', 'True', '1', 'yes', 'Yes', 'TRUE', 'YES']:
        value = field_config.get('text', '●')
    elif value and str(value).strip():
        value = field_config.get('text', '●')
    else:
        value = ''
    print(f"     - Checkbox normalized: {repr(original)} → {repr(value)}")
    return value


def resolve_font_and_size(field_name: str, client_data: Dict, field_config: Dict):
    font_key = f"{field_name}_font"
    size_key = f"{field_name}_size"

    font_value = (
        client_data.get(font_key)
        or client_data.get("font")
        or field_config.get("font", "arial")
    )
    size_value = (
        client_data.get(size_key)
        or client_data.get("size")
        or field_config.get("size", 12)
    )
    try:
        size_value = int(size_value)
    except (ValueError, TypeError):
        size_value = 12

    return font_value, size_value


# =============================================================================
# SINGLE PDF FILLER (UNCHANGED)
# =============================================================================
# ... (your entire fill_single_pdf_sync and the rest of your batch/zip code stays EXACTLY as you pasted)
# I am not re-pasting it again to avoid accidental edits — leave it as-is.


# =============================================================================
# ✅ UPDATED TASK: process_upload_session_task
# ============================================================================

@celery_app.task(name="celery_tasks.process_upload_session", bind=True)
def process_upload_session_task(self, session_id: str, user_id: str, original_storage_path: str):
    """
    Called by /api/pdf/upload

    Args:
      - session_id: uuid
      - user_id: auth.users.id
      - original_storage_path: storage path returned by pdf_processor.upload_original_pdf
        (example: f"{user_id}/{session_id}/original.pdf")
    """
    pdf_processor = PDFProcessor()
    session_service = SessionService()

    tmp_pdf_path = None

    try:
        # Mark processing + clear errors
        session_service.supabase.table("pdf_sessions").update({
            "status": "processing",
            "progress": 5,
            "error_message": None,
            "updated_at": datetime.now().isoformat(),
        }).eq("session_id", session_id).execute()

        # Download original into a local temp file for conversion
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_pdf_path = tmp.name

        print(f"📥 [upload_session] Downloading original from storage: {original_storage_path}")
        pdf_processor.download_file_from_storage(original_storage_path, tmp_pdf_path)

        # Convert to images (writes into TEMP_FOLDER/session_id/page_X.png)
        session_service.supabase.table("pdf_sessions").update({
            "progress": 25,
            "updated_at": datetime.now().isoformat(),
        }).eq("session_id", session_id).execute()

        num_pages = pdf_processor.pdf_to_images(tmp_pdf_path, session_id)

        session_service.supabase.table("pdf_sessions").update({
            "progress": 65,
            "num_pages": num_pages,
            "dpi": pdf_processor.DPI,
            "grid_size": getattr(pdf_processor, "GRID_SIZE", 150),
            "updated_at": datetime.now().isoformat(),
        }).eq("session_id", session_id).execute()

        # Extract page dimensions grid metadata
        pages = pdf_processor.get_all_page_dimensions(session_id, num_pages)

        # ✅ Persist final metadata (pages is a LIST)
        session_service.supabase.table("pdf_sessions").update({
            "status": "ready",
            "progress": 100,
            "num_pages": num_pages,
            "pages": pages,  # ✅ store list directly
            "dpi": pdf_processor.DPI,
            "grid_size": getattr(pdf_processor, "GRID_SIZE", 150),
            "original_storage_path": original_storage_path,
            "updated_at": datetime.now().isoformat(),
        }).eq("session_id", session_id).execute()

        print(f"✅ [upload_session] ready session={session_id} pages={num_pages}")

        # OPTIONAL: cleanup local session folder to save worker disk.
        # Routes can restore on-demand later.
        try:
            pdf_processor.cleanup_folders(session_id)
        except Exception as e:
            print(f"⚠️  cleanup_folders warning: {e}")

        return {"session_id": session_id, "num_pages": num_pages, "status": "ready"}

    except Exception as e:
        err = str(e)
        print(f"❌ [upload_session] failed session={session_id}: {err}")
        session_service.supabase.table("pdf_sessions").update({
            "status": "failed",
            "error_message": err,
            "progress": 0,
            "updated_at": datetime.now().isoformat(),
        }).eq("session_id", session_id).execute()
        raise

    finally:
        try:
            if tmp_pdf_path and os.path.exists(tmp_pdf_path):
                os.remove(tmp_pdf_path)
        except Exception:
            pass
        force_memory_cleanup()


# =============================================================================
# IMPORTANT: add missing import (your original file didn’t import datetime)
# =============================================================================
from datetime import datetime

