"""
Batch Routes - Main API Router with DIAGNOSTIC LOGGING
API endpoints for batch PDF generation from CSV/Excel
"""

from celery_tasks import trigger_parallel_batch, create_batch_zip_task
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
import zipstream
import httpx
from services.pdf_processor import PDFProcessor
from typing import Optional, Set
import uuid
import io

from models.batch_models import (
    CreateBatchRequest,
    BatchCreatedResponse,
    BatchProgressResponse,
    BatchResponse,
    BatchListResponse,
    BatchDeletedResponse,
    ProcessBatchResponse,
    BatchDownloadResponse,
    BatchItemResponse
)
from services.batch_service import get_batch_service
from services.csv_processor import get_csv_processor
from services.template_service import get_template_service
from services.auth import get_current_user

from routes.batch.batch_helpers import (
    get_services,
    validate_file_upload,
    validate_batch_size,
    MAX_BATCH_SIZE,
    MAX_FILE_SIZE
)
from routes.batch.batch_processing import process_batch_sync
from routes.batch.batch_download import create_batch_zip

router = APIRouter(prefix="/api/batch", tags=["Batch Processing"])

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


async def stream_batch_zip(
    batch_id: str,
    user_id: str,
    only_indices: Optional[Set[int]] = None,
):
    """Generator: stream ZIP without buffering to memory/disk."""
    batch_service = get_batch_service()
    
    batch = batch_service.get_batch(batch_id, user_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # DIAGNOSTIC: Check what we got
    completed = batch_service.get_batch_items(batch_id, status="completed")
    print(f"\n{'='*80}")
    print(f"[STREAM DEBUG] Batch ID: {batch_id}")
    print(f"[STREAM DEBUG] Completed items query returned: {len(completed) if completed else 0} items")
    if completed:
        for idx, item in enumerate(completed[:3]):
            print(f"[STREAM DEBUG]   Item {idx}: index={item.get('item_index')}, has pdf_url={bool(item.get('pdf_url'))}, pdf_url={item.get('pdf_url', 'NONE')[:60] if item.get('pdf_url') else 'NONE'}")
    print(f"{'='*80}\n")
    
    if not completed:
        raise HTTPException(status_code=400, detail="No completed items in batch")
    
    if only_indices:
        completed = [
            item for item in completed 
            if item.get("item_index") in only_indices
        ]
        print(f"[STREAM DEBUG] After filter: {len(completed)} items\n")
    
    files_added = 0
    files_failed = 0
    
    print(f"[STREAM DEBUG] Creating ZipFile with ZIP_DEFLATED compression\n")
    with zipstream.ZipFile(compression=zipstream.ZIP_DEFLATED) as zf:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for item in completed:
                pdf_url = item.get("pdf_url")
                item_index = item.get("item_index", 0)
                
                if not pdf_url:
                    print(f"[STREAM DEBUG] Item {item_index}: No pdf_url found, skipping")
                    files_failed += 1
                    continue
                
                filename = f"form_{item_index}.pdf"
                
                try:
                    print(f"[STREAM DEBUG] Streaming {filename} from URL...")
                    async with client.stream("GET", pdf_url) as resp:
                        print(f"[STREAM DEBUG]   HTTP Status: {resp.status_code}")
                        if resp.status_code == 200:
                            # CRITICAL FIX: Collect bytes from async iterator FIRST
                            # write_iter() expects sync iterable, not async generator
                            data = b""
                            byte_count = 0
                            async for chunk in resp.aiter_bytes(chunk_size=8192):
                                data += chunk
                                byte_count += 1
                            print(f"[STREAM DEBUG]   Collected {len(data)} bytes ({byte_count} chunks)")
                            print(f"[STREAM DEBUG]   Adding to ZIP as {filename}")
                            # Pass as list of bytes, not async generator
                            zf.write_iter(filename, [data])
                            files_added += 1
                            print(f"[STREAM DEBUG]   ✓ Added {filename}")
                        else:
                            print(f"[STREAM DEBUG]   ✗ HTTP {resp.status_code}, skipping")
                            files_failed += 1
                except Exception as e:
                    print(f"[STREAM DEBUG] ✗ Exception for {filename}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    files_failed += 1
                    continue
        
        print(f"\n[STREAM DEBUG] ZIP write complete: {files_added} added, {files_failed} failed")
        print(f"[STREAM DEBUG] ZipFile context exiting, ZIP finalizer running...")
    
    print(f"[STREAM DEBUG] ZIP context closed, beginning iteration...")
    chunk_count = 0
    total_bytes = 0
    with zipstream.ZipFile(compression=zipstream.ZIP_DEFLATED) as zf:
        # Re-open to iterate
        for item in completed:
            pdf_url = item.get("pdf_url")
            item_index = item.get("item_index", 0)
            if not pdf_url:
                continue
            filename = f"form_{item_index}.pdf"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("GET", pdf_url) as resp:
                        if resp.status_code == 200:
                            data = b""
                            async for chunk in resp.aiter_bytes(chunk_size=8192):
                                data += chunk
                            zf.write_iter(filename, [data])
            except:
                pass
        
        for chunk in zf:
            chunk_count += 1
            total_bytes += len(chunk)
            print(f"[STREAM DEBUG] Yielding chunk {chunk_count}: {len(chunk)} bytes (total: {total_bytes})")
            yield chunk
    
    print(f"[STREAM DEBUG] Stream complete: {chunk_count} chunks, {total_bytes} total bytes\n")


@router.get("/{batch_id}/download-live")
async def download_batch_live(
    batch_id: str,
    only: Optional[str] = Query(None, description="Filter items: 1,2,7-10"),
    chunk_size: Optional[int] = Query(None, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Stream batch PDFs as live ZIP without buffering."""
    try:
        batch_service = get_batch_service()
        
        batch = batch_service.get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        only_indices = None
        if only:
            try:
                only_indices = parse_item_filter(only)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        filename = f"{batch['batch_name']}.zip"
        
        return StreamingResponse(
            stream_batch_zip(batch_id, current_user['id'], only_indices),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Stream failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stream failed: {str(e)}")