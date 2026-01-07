"""
Celery Tasks - PARALLEL PDF PROCESSING WITH FORMS CONSUMPTION
Each PDF is processed independently and consumes 1 form atomically

CRITICAL: Forms are consumed AFTER successful PDF creation (not before)
to ensure accurate billing even if some PDFs fail.
"""

from celery_config import celery_app
from typing import Dict, List, Optional, Set
import time

# Import your existing services
from services.batch_service import get_batch_service
from services.template_service import get_template_service
from services.pdf_processor import PDFProcessor
from services.image_service import get_image_service
import asyncio
import os
import tempfile
from utils.storage_utils import download_with_retries
import httpx
import zipfile
import gc

ZIP_TTL_SECONDS = 5 * 60 * 60  # 5 hours

import json, re, shutil

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
# REPEAT CONFIG (UPDATED: supports "pages" + "apply_to_pages")
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

    # de-dupe, keep order
    seen = set()
    out = []
    for p in pages:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def expand_field_mappings_from_source_page(field_mappings: Dict, source_page: int, target_pages: List[int]) -> Dict:
    """
    Take mappings on source_page and stamp them onto each target page.
    IMPORTANT: stamped mappings read values from the ORIGINAL field name via "__client_key__".
    """
    source_page = int(source_page)
    targets = [int(p) for p in target_pages]

    source = {
        fname: cfg for fname, cfg in (field_mappings or {}).items()
        if int(cfg.get("page", 1)) == source_page
    }
    if not source:
        raise ValueError(f"No field mappings found on source_page={source_page}")

    out = dict(field_mappings or {})  # keep existing mappings too

    for p in targets:
        for fname, cfg in source.items():
            new_cfg = dict(cfg)
            new_cfg["page"] = p
            if p == source_page:
                out[fname] = new_cfg
            else:
                stamped_name = f"{fname}__p{p}"
                new_cfg["__client_key__"] = fname  # read same CSV column
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
    # 1) __repeats__
    r = _safe_json(client_data.get("__repeats__"))
    if isinstance(r, list) and r:
        return [x for x in r if isinstance(x, dict)]

    # 2) repeats
    r = _safe_json(client_data.get("repeats"))
    if isinstance(r, list) and r:
        return [x for x in r if isinstance(x, dict)]

    # 3) suffix columns: field_1..field_N
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
    # ✅ This matches your PDFProcessor implementation exactly
    return f"{pdf_processor.TEMP_FOLDER}/{session_id}/page_{page_num}.png"


# ============================================================================
# MEMORY MANAGEMENT
# ============================================================================

def force_memory_cleanup():
    """Aggressively clear memory after processing"""
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except:
        pass


# ============================================================================
# CLEANUP UTILITIES
# ============================================================================

def cleanup_temp_files(temp_pdf_path: str, temp_image_paths: list, session_id: str, pdf_processor):
    """Clean up temporary files and session folders"""
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


# ============================================================================
# FIELD DATA BUILDER
# ============================================================================

def resolve_text_style(field_name: str, client_data: Dict, field_config: Dict, batch_options: Dict):
    """
    Precedence:
    1) per-field (row):   <field>_font, <field>_size, <field>_align
    2) per-row (global):  __font__, __size__, __align__  (also accept legacy 'font','size','align')
    3) batch defaults:    options.default_font/size/align
    4) template defaults: field_config.font/size/align
    5) hard defaults:     arial / 12 / 'center'
    """
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
    """
    Precedence:
    1) per-field (row): <field>_width, <field>_height | <field>__width/__height | <field>_w/_h
    2) per-row (global): __image_width__, __image_height__
    3) batch defaults: options.image_defaults.width/height OR default_image_width/height
    4) template defaults: field_config.width/height
    5) hard defaults: 200 x 60
    """
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
    """Build pages_data and images_data from field mappings and client data"""
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

        # ✅ UPDATED: allow stamped fields to read from original CSV key
        client_key = field_config.get("__client_key__") or field_name

        if field_type in ['image', 'signature', 'stamp']:
            # ✅ UPDATED
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

        # ✅ UPDATED
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
    """Load image from local path or download from service"""
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
    else:
        raise Exception(f"No image bytes returned for ref='{image_ref}'")


def handle_checkbox(value, field_config: Dict) -> str:
    """Convert checkbox value to display text"""
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
    """Resolve font and size from per-field or global settings"""
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


# ============================================================================
# SINGLE PDF FILLER
# ============================================================================

def fill_single_pdf_sync(
    template: dict,
    client_data: dict,
    user_id: str,
    batch_id: str,
    item_index: int,
    batch_options: Dict = None
) -> Dict[str, str]:
    """
    Fill a single PDF.
    - standard: current behavior unchanged
    - repeated:
        mode="pages"          -> your existing "clone pages per repeat row" behavior
        mode="apply_to_pages" -> stamp source_page mappings onto repeat_pages within the SAME PDF
    """
    print("\n" + "=" * 80)
    print(f"🧩 fill_single_pdf_sync: START | batch_id={batch_id} item_index={item_index}")

    batch_options = batch_options or {}

    pdf_processor = PDFProcessor()
    image_service = get_image_service()

    session_id = f"{batch_id}_{item_index}"
    temp_pdf_path = None
    temp_image_paths = []
    temp_sessions_to_cleanup: List[str] = []

    try:
        # --------------------------------------------------------------------
        # Step 1: Download template PDF bytes
        # --------------------------------------------------------------------
        raw_path = template.get('pdf_url', '')
        bucket = pdf_processor.STORAGE_BUCKET
        print(f"📥 Downloading template PDF: {raw_path}")

        pdf_bytes = download_with_retries(
            pdf_processor.supabase,
            bucket,
            raw_path,
            max_attempts=5,
            base_delay=0.25,
            template_hint=template.get("name")
        )
        print(f"✅ Downloaded: {len(pdf_bytes)} bytes")

        # --------------------------------------------------------------------
        # Step 2: Save to temp file
        # --------------------------------------------------------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp:
            tmp.write(pdf_bytes)
            temp_pdf_path = tmp.name
        print(f"📄 Temp PDF: {temp_pdf_path}")

        # --------------------------------------------------------------------
        # Step 3: Get page count (no full load)
        # --------------------------------------------------------------------
        num_pages_src = pdf_processor.get_pdf_page_count(temp_pdf_path)
        print(f"📊 Source PDF pages: {num_pages_src}")

        # --------------------------------------------------------------------
        # Step 4: Decide mode
        # --------------------------------------------------------------------
        kind = (template.get("template_kind") or "standard").strip().lower()
        repeat_cfg = template.get("repeat_config") or {}
        if isinstance(repeat_cfg, str):
            repeat_cfg = _safe_json(repeat_cfg) or {}
        if kind == "repeated":
            validate_repeat_config_min(repeat_cfg)

        # ====================================================================
        # MODE A) STANDARD (unchanged)
        # ====================================================================
        if kind != "repeated":
            field_mappings = template.get("field_mappings") or {}
            pages_data, images_data, text_count, image_count = build_field_data(
                field_mappings,
                client_data,
                image_service,
                user_id,
                temp_image_paths,
                batch_options=batch_options
            )

            print(f"📋 Field data built: {text_count} text fields, {image_count} images")

            for page_num in range(1, num_pages_src + 1):
                print(f"\n🔄 Processing page {page_num}/{num_pages_src}...")
                pdf_processor.pdf_to_images_single_page(temp_pdf_path, session_id, page_num)

                if page_num in pages_data and pages_data[page_num]:
                    print(f"   ✍️  Writing {len(pages_data[page_num])} text items")
                    pdf_processor.write_text_on_page(session_id, page_num, pages_data[page_num])

                if page_num in images_data and images_data[page_num]:
                    print(f"   🖼️  Placing {len(images_data[page_num])} images")
                    pdf_processor.add_images_to_page(session_id, page_num, images_data[page_num])

                force_memory_cleanup()
                print(f"   ✅ Page {page_num} complete")

            out_name = f"batch_{batch_id}_item_{item_index}.pdf"
            print(f"\n🧪 Creating final PDF: {out_name}")
            result = pdf_processor.create_pdf_with_upload(
                session_id=session_id,
                user_id=user_id,
                num_pages=num_pages_src,
                output_name=out_name
            )

            print(f"✅ PDF uploaded: {result['storage_path']}")
            cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)
            print(f"🧩 fill_single_pdf_sync: END ✅")
            print("=" * 80 + "\n")

            return {'storage_url': result['storage_url'], 'storage_path': result['storage_path']}

        # ====================================================================
        # MODE B) REPEATED (two sub-modes)
        # ====================================================================
        mode = (repeat_cfg.get("mode") or "pages").strip().lower()

        # --------------------------------------------------------------------
        # MODE B1) apply_to_pages (STAMP source page mappings onto target pages)
        # --------------------------------------------------------------------
        if mode == "apply_to_pages":
            print("🧷 Repeated template detected. mode=apply_to_pages")

            source_page = int(repeat_cfg.get("source_page") or 1)
            if source_page < 1 or source_page > num_pages_src:
                raise Exception(f"source_page={source_page} is invalid; source PDF has {num_pages_src} pages")

            target_pages = compute_apply_pages(repeat_cfg, num_pages_src)
            print(f"🧷 Stamping mappings from page {source_page} -> pages {target_pages}")

            base_mappings = template.get("field_mappings") or {}
            stamped_mappings = expand_field_mappings_from_source_page(
                base_mappings,
                source_page=source_page,
                target_pages=target_pages
            )

            pages_data, images_data, text_count, image_count = build_field_data(
                stamped_mappings,
                client_data,
                image_service,
                user_id,
                temp_image_paths,
                batch_options=batch_options
            )

            print(f"📋 Field data built (stamped): {text_count} text fields, {image_count} images")

            for page_num in range(1, num_pages_src + 1):
                print(f"\n🔄 Processing page {page_num}/{num_pages_src}...")
                pdf_processor.pdf_to_images_single_page(temp_pdf_path, session_id, page_num)

                if page_num in pages_data and pages_data[page_num]:
                    pdf_processor.write_text_on_page(session_id, page_num, pages_data[page_num])

                if page_num in images_data and images_data[page_num]:
                    pdf_processor.add_images_to_page(session_id, page_num, images_data[page_num])

                force_memory_cleanup()

            out_name = f"batch_{batch_id}_item_{item_index}.pdf"
            result = pdf_processor.create_pdf_with_upload(
                session_id=session_id,
                user_id=user_id,
                num_pages=num_pages_src,
                output_name=out_name
            )

            cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)
            return {'storage_url': result['storage_url'], 'storage_path': result['storage_path']}

        # --------------------------------------------------------------------
        # MODE B2) pages (your existing "clone pages per repeat row" behavior)
        # --------------------------------------------------------------------
        print("🔁 Repeated template detected. mode=pages")

        repeat_pages = compute_repeat_pages(template, repeat_cfg)
        for p in repeat_pages:
            if p < 1 or p > num_pages_src:
                raise Exception(f"repeat_pages contains invalid page {p}; source PDF has {num_pages_src} pages")

        repeat_rows = extract_repeat_rows(client_data or {}, repeat_cfg)
        if not repeat_rows:
            raise Exception("template_kind='repeated' but no repeat rows found in client_data")

        max_repeats = repeat_cfg.get("max_repeats")
        if isinstance(max_repeats, (int, float)) and max_repeats > 0:
            repeat_rows = repeat_rows[: int(max_repeats)]

        total_out_pages = len(repeat_rows) * len(repeat_pages)
        print(f"🔁 repeat_pages={repeat_pages} repeats={len(repeat_rows)} => out_pages={total_out_pages}")

        # We'll generate base PNGs into temp sessions, then copy them into MAIN session temp folder
        out_page_counter = 0

        for r_idx, row_data in enumerate(repeat_rows, start=1):
            merged_data = dict(client_data or {})
            merged_data.update(row_data or {})

            print(f"\n🔁 Repeat {r_idx}/{len(repeat_rows)}")

            for src_page in repeat_pages:
                out_page_counter += 1
                out_page = out_page_counter

                temp_session = f"{session_id}__r{r_idx}__p{src_page}"
                temp_sessions_to_cleanup.append(temp_session)

                # 1) convert src_page into temp session
                pdf_processor.pdf_to_images_single_page(temp_pdf_path, temp_session, src_page)

                src_img = temp_png_path(pdf_processor, temp_session, src_page)
                if not os.path.exists(src_img):
                    raise Exception(f"Missing converted image: {src_img}")

                # 2) copy base PNG into MAIN session temp folder as page_<out_page>.png
                dst_img = temp_png_path(pdf_processor, session_id, out_page)
                os.makedirs(os.path.dirname(dst_img), exist_ok=True)
                shutil.copy(src_img, dst_img)

                # 3) build mappings only for src_page, remapped to out_page
                remapped = subset_and_remap_field_mappings(template.get("field_mappings") or {}, src_page, out_page)

                pages_data, images_data, _, _ = build_field_data(
                    remapped,
                    merged_data,
                    image_service,
                    user_id,
                    temp_image_paths,
                    batch_options=batch_options
                )

                # 4) apply text/images onto the out_page using MAIN session_id
                if out_page in pages_data and pages_data[out_page]:
                    pdf_processor.write_text_on_page(session_id, out_page, pages_data[out_page])

                if out_page in images_data and images_data[out_page]:
                    pdf_processor.add_images_to_page(session_id, out_page, images_data[out_page])

                force_memory_cleanup()
                print(f"   ✅ out_page {out_page} done (from src_page {src_page})")

        # 5) create final PDF using total_out_pages
        out_name = f"batch_{batch_id}_item_{item_index}.pdf"
        result = pdf_processor.create_pdf_with_upload(
            session_id=session_id,
            user_id=user_id,
            num_pages=total_out_pages,
            output_name=out_name
        )

        # cleanup temp conversion sessions
        for s in temp_sessions_to_cleanup:
            try:
                pdf_processor.cleanup_folders(s)
            except Exception:
                pass

        cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)

        return {'storage_url': result['storage_url'], 'storage_path': result['storage_path']}

    except Exception as e:
        print(f"⛔ ERROR: {e}")

        # Cleanup temp sessions if any
        for s in temp_sessions_to_cleanup:
            try:
                pdf_processor.cleanup_folders(s)
            except Exception:
                pass

        cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)
        print("=" * 80 + "\n")
        raise Exception(f"PDF generation failed: {str(e)}")


# ============================================================================
# FILENAME HELPERS
# ============================================================================

def clean_filename(text: str) -> str:
    """Clean text for use in filename"""
    if not text:
        return ""

    cleaned = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in str(text))
    cleaned = cleaned.replace(' ', '_')
    cleaned = '_'.join(filter(None, cleaned.split('_')))

    return cleaned[:50] if cleaned else ""


def generate_pdf_filename(client_data: Dict, item_index: int) -> str:
    """Generate friendly filename from client data"""
    if 'last_name' in client_data and 'first_name' in client_data:
        last = clean_filename(str(client_data['last_name']))
        first = clean_filename(str(client_data['first_name']))
        if last and first:
            return f"{last}_{first}.pdf"

    if 'full_name' in client_data:
        name = clean_filename(str(client_data['full_name']))
        if name:
            return f"{name}.pdf"

    if 'name' in client_data:
        name = clean_filename(str(client_data['name']))
        if name:
            return f"{name}.pdf"

    return f"document_{item_index + 1}.pdf"


# ============================================================================
# ZIP CREATION
# ============================================================================

async def create_batch_zip(
    batch_id: str,
    batch_name: str,
    pdf_items: List[Dict],
    user_id: str
) -> str:
    """Create zip file with all PDFs"""
    pdf_processor = PDFProcessor()

    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', mode='wb') as tmp_zip:
        zip_path = tmp_zip.name
    print(f"📦 Creating zip at: {zip_path}")
    print(f"📦 Total PDFs to add: {len(pdf_items)}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:

                for idx, item in enumerate(pdf_items, 1):
                    pdf_url = item.get('pdf_url')
                    storage_path = item.get('storage_path')

                    if not pdf_url and not storage_path:
                        print(f"  ⚠️  Item {idx}: No PDF URL or storage path")
                        continue

                    try:
                        client_data = item.get('client_data', {})
                        filename = generate_pdf_filename(client_data, item['item_index'])

                        pdf_bytes = b""

                        if storage_path:
                            print(f"  📥 [{idx}/{len(pdf_items)}] Downloading via storage_path: {filename}")
                            print(f"      PATH: {storage_path}")
                            pdf_bytes = pdf_processor.supabase.storage.from_(
                                pdf_processor.STORAGE_BUCKET
                            ).download(storage_path)

                        if (not pdf_bytes) and pdf_url:
                            try:
                                print(f"  📥 [{idx}/{len(pdf_items)}] Downloading via URL: {filename}")
                                print(f"      URL: {pdf_url[:80]}...")
                                response = await client.get(pdf_url)
                                response.raise_for_status()
                                pdf_bytes = response.content
                            except httpx.HTTPStatusError as http_err:
                                print(f"  ⚠️  [{idx}/{len(pdf_items)}] URL fetch failed ({http_err.response.status_code}). Trying storage fallback...")
                                if storage_path:
                                    pdf_bytes = pdf_processor.supabase.storage.from_(
                                        pdf_processor.STORAGE_BUCKET
                                    ).download(storage_path)
                                else:
                                    raise

                        if not pdf_bytes or len(pdf_bytes) == 0:
                            print(f"  ❌ [{idx}/{len(pdf_items)}] Empty PDF content!")
                            continue

                        print(f"  ✅ [{idx}/{len(pdf_items)}] Downloaded {len(pdf_bytes)} bytes")

                        zipf.writestr(filename, pdf_bytes)
                        print(f"  ✅ [{idx}/{len(pdf_items)}] Added to zip: {filename}")

                    except Exception as e:
                        print(f"  ❌ [{idx}/{len(pdf_items)}] Failed: {str(e)}")
                        continue

        zip_size = os.path.getsize(zip_path)
        print(f"📦 Zip file size: {zip_size} bytes")

        if zip_size < 100:
            raise Exception("Zip file is empty! No PDFs were added.")

        with zipfile.ZipFile(zip_path, 'r') as zipf:
            file_count = len(zipf.namelist())
            print(f"📦 Zip contains {file_count} file(s)")
            if file_count == 0:
                raise Exception("Zip created but contains no files!")

        print(f"📤 Uploading zip to storage...")
        zip_storage_path = f"{user_id}/batches/{batch_id}/download.zip"

        with open(zip_path, 'rb') as f:
            zip_data = f.read()
            print(f"📤 Uploading {len(zip_data)} bytes...")

            pdf_processor.supabase.storage.from_(
                pdf_processor.STORAGE_BUCKET
            ).upload(
                path=zip_storage_path,
                file=zip_data,
                file_options={"content-type": "application/zip", "upsert": "true"}
            )

        signed_url_response = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).create_signed_url(zip_storage_path, 3600)

        zip_url = signed_url_response['signedURL']
        cleanup_zip_task.apply_async(
            args=[user_id, batch_id, zip_storage_path],
            countdown=ZIP_TTL_SECONDS
        )

        print(f"✅ Zip created successfully!")
        print(f"✅ URL: {zip_url[:80]}...")

        force_memory_cleanup()

        return zip_url

    except Exception as e:
        print(f"❌ Zip creation failed: {str(e)}")
        raise

    finally:
        if os.path.exists(zip_path):
            print(f"🧹 Cleaning up temp file: {zip_path}")
            os.unlink(zip_path)


@celery_app.task(
    name='celery_tasks.cleanup_zip',
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def cleanup_zip_task(self, user_id: str, batch_id: str, zip_storage_path: str):
    """Delete ZIP from Supabase after TTL and clear download_url"""
    try:
        print(f"\n🧹 Cleanup ZIP for batch={batch_id}")
        pdf_processor = PDFProcessor()
        supa = pdf_processor.supabase
        bucket = pdf_processor.STORAGE_BUCKET

        try:
            supa.storage.from_(bucket).remove([zip_storage_path])
            print(f"✅ Removed from storage: {bucket}/{zip_storage_path}")
        except Exception as e:
            print(f"⚠️  Storage remove warning ({zip_storage_path}): {e}")

        batch_service = get_batch_service()
        try:
            batch_service.supabase.table(batch_service.batch_table).update({
                "download_url": None
            }).eq("id", batch_id).execute()
            print(f"✅ Cleared download_url for batch {batch_id}")
        except Exception as e:
            print(f"⚠️  Failed to clear download_url for {batch_id}: {e}")

        print(f"🧹 Cleanup complete for batch={batch_id}")
        force_memory_cleanup()

    except Exception as e:
        print(f"❌ cleanup_zip_task error: {e}")
        raise self.retry(exc=e)


@celery_app.task(name='celery_tasks.process_single_pdf', bind=True)
def process_single_pdf_task(
    self,
    batch_id: str,
    item_id: str,
    item_index: int,
    client_data: Dict,
    template_id: str,
    user_id: str,
    skip_forms_consumption: bool = False
):
    """
    Process a SINGLE PDF in parallel.

    ✅ CRITICAL: Consumes 1 form AFTER successful PDF creation.
    This ensures accurate billing even if some PDFs fail.
    """
    task_start = time.time()
    print(f"\n🚀 [Worker {self.request.id[:8]}] Processing item {item_index}")

    try:
        batch_service = get_batch_service()
        template_service = get_template_service()

        batch = batch_service.get_batch(batch_id, user_id) or {}
        batch_options = (batch.get("options") or {})
        batch_service.update_batch_item(item_id, "processing")

        template = template_service.get_template(template_id, user_id)
        if not template:
            raise Exception(f"Template not found: {template_id}")

        # ============================================================
        # STEP 1: Create the PDF
        # ============================================================
        pdf_start = time.time()
        result = fill_single_pdf_sync(
            template=template,
            client_data=client_data,
            user_id=user_id,
            batch_id=batch_id,
            item_index=item_index,
            batch_options=batch_options,
        )
        pdf_time = time.time() - pdf_start

        # ============================================================
        # STEP 2: ✅ CONSUME 1 FORM (atomic, after success)
        # ============================================================
        if not skip_forms_consumption:
            from services.entitlement_service import get_entitlement_service
            entitlement_service = get_entitlement_service()

            try:
                consumed = entitlement_service.consume_forms(user_id=user_id, count=1)
                forms_remaining = consumed.get('forms_remaining', 'unknown')
                print(f"💰 [Worker {self.request.id[:8]}] ✅ Consumed 1 form. Remaining: {forms_remaining}")
            except Exception as consume_error:
                # ⚠️  Log but don't fail the task
                print(f"⚠️  [Worker {self.request.id[:8]}] ❌ Forms consumption FAILED: {consume_error}")
                print(f"⚠️  PDF was created successfully but billing not recorded!")

        # ============================================================
        # STEP 3: Mark item as completed
        # ============================================================
        batch_service.update_batch_item(
            item_id,
            "completed",
            pdf_url=result['storage_url'],
            storage_path=result['storage_path']
        )

        task_time = time.time() - task_start
        print(f"✅ [Worker {self.request.id[:8]}] Item {item_index} done in {task_time:.1f}s (PDF: {pdf_time:.1f}s)")

        force_memory_cleanup()

        return {
            'item_id': item_id,
            'item_index': item_index,
            'storage_url': result['storage_url'],
            'storage_path': result['storage_path'],
            'processing_time': task_time
        }

    except Exception as e:
        error_msg = str(e)
        print(f"❌ [Worker {self.request.id[:8]}] Item {item_index} failed: {error_msg}")

        batch_service = get_batch_service()
        batch_service.update_batch_item(
            item_id,
            "failed",
            error_message=error_msg
        )

        force_memory_cleanup()

        raise self.retry(exc=e, countdown=5, max_retries=2)


@celery_app.task(name='celery_tasks.finalize_batch')
def finalize_batch_task(batch_id: str, user_id: str):
    """Finalize batch after all items processed"""
    print(f"\n🏁 Finalizing batch: {batch_id}")

    try:
        batch_service = get_batch_service()
        stats = batch_service.get_batch_progress(batch_id, user_id)
        total      = stats.get('total', 0)
        completed  = stats.get('completed', 0)
        failed     = stats.get('failed', 0)
        pending    = stats.get('pending', 0)
        processing = stats.get('processing', 0)

        print(f"🔎 Finalize check: total={total} completed={completed} failed={failed} "
              f"pending={pending} processing={processing}")

        if pending == 0 and processing == 0:
            new_status = 'completed' if failed == 0 else 'completed_with_errors'
            batch_service.update_batch_status(batch_id, new_status)
            print(f"✅ Batch {batch_id} marked {new_status}")
            if total > 1:
                print(f"💰 Total forms consumed: {completed}")
        else:
            batch_service.update_batch_status(batch_id, "processing")
            print(f"⏳ Batch {batch_id} still in progress; leaving status as processing")

        force_memory_cleanup()

    except Exception as e:
        print(f"❌ Failed to finalize batch: {str(e)}")


@celery_app.task(
    name='celery_tasks.create_batch_zip_task',
    soft_time_limit=1800,
    time_limit=2000
)
def create_batch_zip_task(
    batch_id: str,
    batch_name: str,
    user_id: str
):
    """Create zip file asynchronously"""
    print(f"\n📦 Creating zip for batch: {batch_id}")

    try:
        batch_service = get_batch_service()

        completed_items = batch_service.get_batch_items(batch_id, status="completed")

        if not completed_items:
            print(f"⚠️  No completed items to zip")
            return None

        pdf_items = [
            {
                "item_index": item["item_index"],
                "pdf_url": item.get("pdf_url"),
                "storage_path": item.get("storage_path"),
                "client_data": item["client_data"]
            }
            for item in completed_items
        ]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        zip_url = loop.run_until_complete(
            create_batch_zip(
                batch_id=batch_id,
                batch_name=batch_name,
                pdf_items=pdf_items,
                user_id=user_id
            )
        )

        loop.close()

        batch_service.update_batch_status(batch_id, "completed", download_url=zip_url)

        print(f"✅ Zip created: {zip_url[:80]}...")

        force_memory_cleanup()

        return zip_url

    except Exception as e:
        print(f"❌ Zip creation failed: {str(e)}")
        raise


# ============================================================================
# HELPER FUNCTION - Trigger parallel processing
# ============================================================================

def trigger_parallel_batch(batch_id: str, user_id: str, template_id: str, skip_forms_consumption: bool = False):
    """Trigger parallel processing of entire batch"""
    print(f"\n⚡ PARALLEL PROCESSING START: {batch_id}")
    start_time = time.time()

    batch_service = get_batch_service()

    items = batch_service.get_batch_items(batch_id, status="pending")

    if not items:
        print(f"⚠️  No items to process")
        return

    print(f"📊 Queuing {len(items)} tasks for parallel processing...")

    batch_service.update_batch_status(batch_id, "processing")

    from celery import group, chord

    task_group = group(
        process_single_pdf_task.s(
            batch_id=batch_id,
            item_id=item['id'],
            item_index=item['item_index'],
            client_data=item['client_data'],
            template_id=template_id,
            user_id=user_id,
            skip_forms_consumption=skip_forms_consumption
        )
        for item in items
    )

    callback = finalize_batch_task.si(batch_id, user_id)
    job = chord(task_group)(callback)

    queue_time = time.time() - start_time

    print(f"✅ {len(items)} tasks queued in {queue_time:.2f}s")
    print(f"🔥 Workers will process in parallel!")
    print(f"⏱️  Expected time with 10 workers: ~{len(items) / 10 * 3:.0f}s ({len(items) / 10 * 3 / 60:.1f} min)")
    print(f"💰 Will consume {len(items)} forms when completed")

    return job.id
