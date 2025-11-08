"""
Celery Tasks - PARALLEL PDF PROCESSING
Each PDF is processed independently in parallel by different workers

SPEED: 100 PDFs in ~2-5 minutes with 10 workers (vs 43 mins sequential)
"""

from celery_config import celery_app
from typing import Dict, List
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



# ============================================================================
# FIELD DATA BUILDER
# ============================================================================

def build_field_data(field_mappings: Dict, client_data: Dict, image_service, user_id: str, temp_image_paths: list):
    """Build pages_data and images_data from field mappings and client data"""
    pages_data = {}
    images_data = {}
    text_field_count = 0
    image_field_count = 0

    print(f"🧭 Iterating field_mappings...")
    for field_name, field_config in field_mappings.items():
        page = field_config.get('page', 1)
        field_type = field_config.get('type', 'text')
        print(f"   • Field '{field_name}' → page={page} type={field_type}")

        # Handle IMAGE/signature/stamp fields
        if field_type in ['image', 'signature', 'stamp']:
            image_ref = client_data.get(field_name, '')
            print(f"     - image_ref: {repr(image_ref)[:120]}")
            if image_ref and str(image_ref).strip():
                try:
                    image_path = load_image(image_ref, image_service, user_id, temp_image_paths)
                    
                    if page not in images_data:
                        images_data[page] = []
                    
                    entry = {
                        'image_path': image_path,
                        'x': field_config['x'],
                        'y': field_config['y'],
                        'width': field_config.get('width', 200),
                        'height': field_config.get('height', 60)
                    }
                    images_data[page].append(entry)
                    image_field_count += 1
                    print(f"     - Queued image placement: {entry}")
                except Exception as e:
                    print(f"     ❌ Failed to load/place image '{image_ref}': {e}")
            else:
                print(f"     - No image provided in client_data for '{field_name}'")
            continue

        # Handle TEXT / CHECKBOX fields
        if page not in pages_data:
            pages_data[page] = []

        value = client_data.get(field_name, '')

        # Checkbox handling
        if field_type == 'checkbox':
            value = handle_checkbox(value, field_config)

        # Font & size resolution
        font_value, size_value = resolve_font_and_size(field_name, client_data, field_config)

        value = str(value) if value is not None else ''
        entry = {
            'text': value,
            'x': field_config['x'],
            'y': field_config['y'],
            'size': size_value,
            'font': font_value,
            'align': field_config.get('align', 'left')
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
    item_index: int
) -> Dict[str, str]:
    """Fill a single PDF with text AND images — with verbose logs"""
    print("\n" + "=" * 80)
    print(f"🧩 fill_single_pdf_sync: START | batch_id={batch_id} item_index={item_index} user_id={user_id}")
    
    pdf_processor = PDFProcessor()
    image_service = get_image_service()
    session_id = f"{batch_id}_{item_index}"
    temp_pdf_path = None
    temp_image_paths = []  # Track temp images for cleanup

    # Log template summary
    try:
        fm = template.get("field_mappings", {})
        print(f"🧾 Template summary:"
              f"\n  - id: {template.get('id')}"
              f"\n  - name: {template.get('name')}"
              f"\n  - is_official: {template.get('is_official')}"
              f"\n  - pdf_url (storage path): {template.get('pdf_url')}"
              f"\n  - field_mappings keys: {list(fm.keys())[:10]} (total={len(fm)})")
    except Exception as e:
        print(f"⚠️  Failed to log template summary: {e}")

    # Log client data keys
    try:
        print(f"👤 Client data keys (first 20): {list(client_data.keys())[:20]}")
    except Exception as e:
        print(f"⚠️  Failed to log client data keys: {e}")

    try:
        # Step 1: Download template PDF
        raw_path = template.get('pdf_url', '')
        bucket = pdf_processor.STORAGE_BUCKET
        print(f"📦 Storage bucket: {bucket}")
        print(f"📥 Attempting to download template PDF:\n    - path: {raw_path}")

        try:
            pdf_bytes = download_with_retries(
                pdf_processor.supabase,
                bucket,
                raw_path,
                max_attempts=5,
                base_delay=0.25,
                template_hint=template.get("name")
            )
            print(f"✅ Downloaded template bytes: {len(pdf_bytes)}")
        except Exception as dl_err:
            print(f"❌ Download failed from primary bucket '{pdf_processor.STORAGE_BUCKET}': {dl_err}")
            fb = getattr(pdf_processor, "FALLBACK_STORAGE_BUCKET", None)
            if fb:
                print(f"🔁 Trying fallback bucket: {fb}")
                try:
                    pdf_bytes = pdf_processor.supabase.storage.from_(fb).download(raw_path)
                    print(f"✅ Downloaded from fallback bucket '{fb}': {len(pdf_bytes)} bytes")
                except Exception as fb_err:
                    print(f"❌ Fallback download also failed: {fb_err}")
                    raise
            else:
                raise

        # Step 2: Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp:
            tmp.write(pdf_bytes)
            temp_pdf_path = tmp.name
        print(f"📄 Temp PDF path: {temp_pdf_path}")

        # Step 3: Convert PDF to images
        print(f"🖼️ Converting PDF to images for session: {session_id}")
        num_pages = pdf_processor.pdf_to_images(temp_pdf_path, session_id)
        print(f"🖨️  Conversion done. Pages: {num_pages}")

        # Step 4: Build field data (text and images)
        pages_data, images_data, text_count, image_count = build_field_data(
            template['field_mappings'],
            client_data,
            image_service,
            user_id,
            temp_image_paths
        )

        # Step 5: Fill text fields
        total_text_items = sum(len(t) for t in pages_data.values())
        print(f"✍️  Writing text fields: pages={sorted(pages_data.keys())}, "
              f"total_text_items={total_text_items}, counted={text_count}")
        for page_num, text_data in pages_data.items():
            if text_data:
                print(f"   → Page {page_num}: {len(text_data)} item(s)")
                pdf_processor.write_text_on_page(session_id, page_num, text_data)

        # Step 6: Fill image fields
        if images_data:
            total_images = sum(len(imgs) for imgs in images_data.values())
            print(f"🖼️  Placing images: pages={sorted(images_data.keys())}, "
                  f"total_images={total_images}, counted={image_count}")
            for page_num, image_list in images_data.items():
                if image_list:
                    print(f"   → Page {page_num}: {len(image_list)} image(s)")
                    pdf_processor.add_images_to_page(session_id, page_num, image_list)
        else:
            print("🖼️  No images to place")

        # Step 7: Generate final PDF
        out_name = f"batch_{batch_id}_item_{item_index}.pdf"
        print(f"🧪 Creating final PDF (upload) → {out_name}")
        result = pdf_processor.create_pdf_with_upload(
            session_id=session_id,
            user_id=user_id,
            num_pages=num_pages,
            output_name=out_name
        )
        storage_url = result['storage_url']
        final_storage_path = result['storage_path']

        print(f"✅ PDF generated & uploaded")
        print(f"   - signed URL: {storage_url[:100]}{'...' if len(storage_url) > 100 else ''}")
        print(f"   - storage_path: {final_storage_path}")

        # Step 8: Cleanup
        cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)

        print(f"🧩 fill_single_pdf_sync: END | batch_id={batch_id} item_index={item_index} ✅")
        print("=" * 80 + "\n")

        return {
            'storage_url': storage_url,
            'storage_path': final_storage_path
        }

    except Exception as e:
        print(f"⛔ ERROR in fill_single_pdf_sync | batch_id={batch_id} item_index={item_index}: {e}")
        cleanup_temp_files(temp_pdf_path, temp_image_paths, session_id, pdf_processor)
        print(f"🧩 fill_single_pdf_sync: END (ERROR) | batch_id={batch_id} item_index={item_index} ❌")
        print("=" * 80 + "\n")
        raise Exception(f"PDF generation failed: {str(e)}")


# ============================================================================
# FILENAME HELPERS
# ============================================================================

def clean_filename(text: str) -> str:
    """Clean text for use in filename"""
    if not text:
        return ""

    # Remove or replace special characters
    cleaned = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in str(text))

    # Replace spaces with underscores
    cleaned = cleaned.replace(' ', '_')

    # Collapse multiple underscores into one
    cleaned = '_'.join(filter(None, cleaned.split('_')))

    # Trim excessively long names
    return cleaned[:50] if cleaned else ""


def generate_pdf_filename(client_data: Dict, item_index: int) -> str:
    """Generate friendly filename from client data"""
    # Try different name combinations
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
    
    # Fallback to index-based name
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
    """Create zip file with all PDFs - FIXED VERSION"""  
    pdf_processor = PDFProcessor()
    
    # Create temp zip file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', mode='wb') as tmp_zip:
        zip_path = tmp_zip.name
    
    print(f"📦 Creating zip at: {zip_path}")
    print(f"📦 Total PDFs to add: {len(pdf_items)}")
    
    try:
        # Create zip and add PDFs
        async with httpx.AsyncClient(timeout=30.0) as client:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                
                for idx, item in enumerate(pdf_items, 1):
                    pdf_url = item.get('pdf_url')
                    storage_path = item.get('storage_path')

                    if not pdf_url and not storage_path:
                        print(f"  ⚠️  Item {idx}: No PDF URL or storage path")
                        continue
                    
                    try:
                        # Generate filename
                        client_data = item.get('client_data', {})
                        filename = generate_pdf_filename(client_data, item['item_index'])
                        
                        pdf_bytes = b""

                        # Prefer storage_path (avoids expired signed URLs)
                        if storage_path:
                            print(f"  📥 [{idx}/{len(pdf_items)}] Downloading via storage_path: {filename}")
                            print(f"      PATH: {storage_path}")
                            pdf_bytes = pdf_processor.supabase.storage.from_(
                                pdf_processor.STORAGE_BUCKET
                            ).download(storage_path)

                        # If no storage_path bytes (or not provided), try signed URL
                        if (not pdf_bytes) and pdf_url:
                            try:
                                print(f"  📥 [{idx}/{len(pdf_items)}] Downloading via URL: {filename}")
                                print(f"      URL: {pdf_url[:80]}...")
                                response = await client.get(pdf_url)
                                response.raise_for_status()
                                pdf_bytes = response.content
                            except httpx.HTTPStatusError as http_err:
                                # Fallback: signed URL likely expired
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
                        
                        # Add to zip
                        zipf.writestr(filename, pdf_bytes)
                        print(f"  ✅ [{idx}/{len(pdf_items)}] Added to zip: {filename}")
                        
                    except Exception as e:
                        print(f"  ❌ [{idx}/{len(pdf_items)}] Failed: {str(e)}")
                        continue
        
        # Verify zip has content
        zip_size = os.path.getsize(zip_path)
        print(f"📦 Zip file size: {zip_size} bytes")
        
        if zip_size < 100:  # Zip with no files is ~22 bytes
            raise Exception("Zip file is empty! No PDFs were added.")
        
        # Verify zip contents
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            file_count = len(zipf.namelist())
            print(f"📦 Zip contains {file_count} file(s)")
            if file_count == 0:
                raise Exception("Zip created but contains no files!")
        
        # Upload zip to storage
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
        
        # Generate signed URL
        signed_url_response = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).create_signed_url(zip_storage_path, 3600)
        
        zip_url = signed_url_response['signedURL']
        
        print(f"✅ Zip created successfully!")
        print(f"✅ URL: {zip_url[:80]}...")
        
        return zip_url
    
    except Exception as e:
        print(f"❌ Zip creation failed: {str(e)}")
        raise
    
    finally:
        # Cleanup temp file
        if os.path.exists(zip_path):
            print(f"🧹 Cleaning up temp file: {zip_path}")
            os.unlink(zip_path)





@celery_app.task(name='celery_tasks.process_single_pdf', bind=True)
def process_single_pdf_task(
    self,
    batch_id: str,
    item_id: str,
    item_index: int,
    client_data: Dict,
    template_id: str,
    user_id: str
):
    """
    Process a SINGLE PDF in parallel
    
    This runs independently on different workers
    100 items = 100 parallel tasks across your workers
    
    Args:
        self: Celery task instance (for retries)
        batch_id: Batch UUID
        item_id: Item UUID
        item_index: Item number (0-99 for 100 items)
        client_data: Client form data
        template_id: Template UUID
        user_id: User UUID
        
    Returns:
        Dict with storage_url and storage_path
    """
    task_start = time.time()
    print(f"\n🚀 [Worker {self.request.id[:8]}] Processing item {item_index}")
    
    try:
        batch_service = get_batch_service()
        template_service = get_template_service()
        
        # Mark as processing
        batch_service.update_batch_item(item_id, "processing")
        
        # Get template
        template = template_service.get_template(template_id, user_id)
        if not template:
            raise Exception(f"Template not found: {template_id}")
        
        # Fill PDF (this is the heavy work)
        pdf_start = time.time()
        result = fill_single_pdf_sync(
            template=template,
            client_data=client_data,
            user_id=user_id,
            batch_id=batch_id,
            item_index=item_index
        )
        pdf_time = time.time() - pdf_start
        
        # Mark as completed
        batch_service.update_batch_item(
            item_id,
            "completed",
            pdf_url=result['storage_url'],
            storage_path=result['storage_path']
        )
        
        # Increment counters
        #batch_service.increment_batch_counters(batch_id, completed=1)
        
        task_time = time.time() - task_start
        print(f"✅ [Worker {self.request.id[:8]}] Item {item_index} done in {task_time:.1f}s (PDF: {pdf_time:.1f}s)")
        
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
        
        # Mark as failed
        batch_service = get_batch_service()
        batch_service.update_batch_item(
            item_id,
            "failed",
            error_message=error_msg
        )
        #batch_service.increment_batch_counters(batch_id, failed=1)
        
        # Retry logic (Celery auto-retries)
        raise self.retry(exc=e, countdown=5, max_retries=2)


@celery_app.task(name='celery_tasks.finalize_batch')
def finalize_batch_task(batch_id: str, user_id: str):
    """
    Finalize batch after all items processed
    
    Called by a Celery chord/chain after all PDFs done
    Checks final status and marks batch complete
    """
    print(f"\n🏁 Finalizing batch: {batch_id}")
    
    try:
        batch_service = get_batch_service()
        # Recompute fresh stats from DB (DO NOT trust incremented counters)
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
        else:
            # Still work left somewhere—do NOT mark complete
            batch_service.update_batch_status(batch_id, "processing")
            print(f"⏳ Batch {batch_id} still in progress; leaving status as processing")
    except Exception as e:
        print(f"❌ Failed to finalize batch: {str(e)}")


@celery_app.task(
    name='celery_tasks.create_batch_zip_task',
    soft_time_limit=1800,   # 30 min
    time_limit=2000         # hard kill a bit after soft
)
def create_batch_zip_task(
    batch_id: str,
    batch_name: str,
    user_id: str
):
    """
    Create zip file asynchronously
    
    This is also slow, so we offload it to Celery
    User gets instant response, zip created in background
    """
    print(f"\n📦 Creating zip for batch: {batch_id}")
    
    try:
        batch_service = get_batch_service()
        
        # Get completed items
        completed_items = batch_service.get_batch_items(batch_id, status="completed")
        
        if not completed_items:
            print(f"⚠️  No completed items to zip")
            return None
        
        # Build pdf_items list
        pdf_items = [
            {
                "item_index": item["item_index"],
                "pdf_url": item.get("pdf_url"),
                "storage_path": item.get("storage_path"),
                "client_data": item["client_data"]
            }
            for item in completed_items
        ]
        
        # Create zip (async function, so we need event loop)
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
        
        # Update batch with zip URL
        batch_service.update_batch_status(batch_id, "completed", download_url=zip_url)
        
        print(f"✅ Zip created: {zip_url[:80]}...")
        return zip_url
    
    except Exception as e:
        print(f"❌ Zip creation failed: {str(e)}")
        raise


# ============================================================================
# HELPER FUNCTION - Trigger parallel processing
# ============================================================================

def trigger_parallel_batch(batch_id: str, user_id: str, template_id: str):
    """
    Trigger parallel processing of entire batch
    
    Instead of processing items sequentially, this sends ALL items
    to Celery queue immediately. Workers process them in parallel.
    
    100 items → 100 Celery tasks → Processed by 10 workers in parallel
    = ~10x faster (or more with more workers!)
    
    Args:
        batch_id: Batch UUID
        user_id: User UUID
        template_id: Template UUID
    """
    print(f"\n⚡ PARALLEL PROCESSING START: {batch_id}")
    start_time = time.time()
    
    batch_service = get_batch_service()
    
    # Get ALL pending items
    items = batch_service.get_batch_items(batch_id, status="pending")
    
    if not items:
        print(f"⚠️  No items to process")
        return
    
    print(f"📊 Queuing {len(items)} tasks for parallel processing...")
    
    # Update batch status
    batch_service.update_batch_status(batch_id, "processing")
    
    # Create task group (all tasks run in parallel!)
    from celery import group, chord
    
    # Build parallel task group
    task_group = group(
        process_single_pdf_task.s(
            batch_id=batch_id,
            item_id=item['id'],
            item_index=item['item_index'],
            client_data=item['client_data'],
            template_id=template_id,
            user_id=user_id
        )
        for item in items
    )
    
    # Execute with callback when all done
    callback = finalize_batch_task.si(batch_id, user_id)
    job = chord(task_group)(callback)
    
    queue_time = time.time() - start_time
    
    print(f"✅ {len(items)} tasks queued in {queue_time:.2f}s")
    print(f"🔥 Workers will process in parallel!")
    print(f"⏱️  Expected time with 10 workers: ~{len(items) / 10 * 3:.0f}s ({len(items) / 10 * 3 / 60:.1f} min)")
    
    return job.id