"""
Batch Download - Zip Creation and URL Management
Functions for creating zip archives of batch PDFs and managing signed URLs
"""

import os
import tempfile
import zipfile
from typing import List, Dict, Optional
from urllib.parse import urlparse
import httpx

from services.pdf_processor import PDFProcessor
from .batch_helpers import generate_pdf_filename


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


# ============================================================================
# URL MANAGEMENT
# ============================================================================

def refresh_signed_urls(completed_items: List[Dict], pdf_processor: PDFProcessor) -> List[Dict]:
    """
    Refresh signed URLs for completed items
    
    Ensures all items have valid, non-expired signed URLs
    """
    bucket = pdf_processor.STORAGE_BUCKET

    for item in completed_items:
        storage_path = item.get("storage_path")
        signed = item.get("pdf_url")

        # If we don't have storage_path but we do have a signed URL, try to derive it
        if not storage_path and signed:
            derived = _extract_storage_path_from_signed(signed, bucket)
            if derived:
                item["storage_path"] = derived
                storage_path = derived

        # Always (re)create a fresh signed URL if we have a storage_path
        if storage_path:
            try:
                print(f"  🔄 Regenerating URL for item {item['item_index']}")
                signed_url_response = pdf_processor.supabase.storage.from_(bucket).create_signed_url(
                    storage_path, 3600
                )
                item["pdf_url"] = signed_url_response["signedURL"]
                print(f"  ✅ URL regenerated")
            except Exception as e:
                print(f"  ⚠️  Could not regenerate URL for item {item['item_index']}: {e}")
        else:
            # No storage_path and cannot derive; leave existing pdf_url as-is
            pass
    
    return completed_items


def _extract_storage_path_from_signed(url: str, bucket: str) -> Optional[str]:
    """Extract storage path from signed URL"""
    try:
        p = urlparse(url)
        # expected: /storage/v1/object/sign/<bucket>/<path/to/file>
        marker = f"/storage/v1/object/sign/{bucket}/"
        if marker in p.path:
            return p.path.split(marker, 1)[1]
    except Exception:
        pass
    return None