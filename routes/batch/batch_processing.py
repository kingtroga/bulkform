"""
Batch Processing - PDF Generation Logic
Background task that processes batch items and fills PDFs
"""

import os
import tempfile
from typing import Dict

from services.pdf_processor import PDFProcessor
from services.image_service import get_image_service
from .batch_helpers import get_services
from .storage_utils import download_with_retries


# ============================================================================
# MAIN BATCH PROCESSOR
# ============================================================================

def process_batch_sync(batch_id: str, user_id: str, template_id: str):
    """
    Background task that actually fills the PDFs (SYNCHRONOUS)
    
    This is synchronous to properly handle blocking I/O operations:
    - Supabase calls (sync)
    - File I/O (sync)
    - PDF processing (sync)
    
    FastAPI will run this in a thread pool automatically.
    """
    try:
        services = get_services()
        print(f"\n🚀 Starting batch processing: {batch_id}")
        
        # Get template
        template = services['template'].get_template(template_id, user_id)
        if not template:
            services['batch'].update_batch_status(batch_id, "failed")
            print(f"❌ Template not found: {template_id}")
            return
        
        print(f"✅ Template: {template['name']}")
        
        # Get pending items
        items = services['batch'].get_batch_items(batch_id, status="pending")
        print(f"✅ Found {len(items)} pending items")
        
        if not items:
            print(f"⚠️  No pending items to process")
            # Check if there are any items at all
            all_items = services['batch'].get_batch_items(batch_id)
            if all_items:
                services['batch'].update_batch_status(batch_id, "completed")
                print(f"✅ Batch marked as completed (no pending items)")
            return
        
        # Update status to processing
        services['batch'].update_batch_status(batch_id, "processing")
        
        # Process each item sequentially
        for item in items:
            try:
                print(f"\n📄 Processing item {item['item_index']} of {len(items)}...")
                
                # Mark as processing
                services['batch'].update_batch_item(item['id'], "processing")
                
                # Fill PDF using helper function
                result = fill_single_pdf_sync(
                    template=template,
                    client_data=item['client_data'],
                    user_id=user_id,
                    batch_id=batch_id,
                    item_index=item['item_index']
                )
                
                # Mark as completed
                services['batch'].update_batch_item(
                    item['id'],
                    "completed",
                    pdf_url=result['storage_url'],
                    storage_path=result['storage_path']
                )
                
                services['batch'].increment_batch_counters(batch_id, completed=1)
                
                print(f"✅ Item {item['item_index']} completed: {result['storage_url']}")
            
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Item {item['item_index']} failed: {error_msg}")
                
                services['batch'].update_batch_item(
                    item['id'],
                    "failed",
                    error_message=error_msg
                )
                
                services['batch'].increment_batch_counters(batch_id, failed=1)
        
        # After processing all items, check if batch is truly complete
        batch_status = services['batch'].get_batch(batch_id, user_id)
        remaining_pending = services['batch'].get_batch_items(batch_id, status="pending")
        
        if len(remaining_pending) == 0:
            # All items processed (either completed or failed)
            services['batch'].update_batch_status(batch_id, "completed")
            print(f"\n🎉 Batch processing complete: {batch_id}")
            print(f"   ✅ Completed: {batch_status['completed']}")
            print(f"   ❌ Failed: {batch_status['failed']}")
        else:
            # Some items still pending (shouldn't happen, but handle it)
            print(f"\n⚠️  Batch processing incomplete: {batch_id}")
            print(f"   ⏳ Still pending: {len(remaining_pending)} items")
    
    except Exception as e:
        print(f"❌ Batch processing failed critically: {str(e)}")
        try:
            services = get_services()
            services['batch'].update_batch_status(batch_id, "failed")
        except:
            print(f"❌ Could not update batch status to failed")


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