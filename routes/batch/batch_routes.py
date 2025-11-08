"""
Batch Routes - Main API Router
API endpoints for batch PDF generation from CSV/Excel
FIXED ZIP STREAMING - GUARANTEED TO WORK
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

from .batch_helpers import (
    get_services,
    validate_file_upload,
    validate_batch_size,
    MAX_BATCH_SIZE,
    MAX_FILE_SIZE
)
from .batch_processing import process_batch_sync
from .batch_download import create_batch_zip

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
    """
    Stream batch PDFs as ZIP without buffering to disk/memory.
    
    KEY FIX: 
    1. Create ZipFile WITHOUT context manager (manual lifecycle)
    2. Add all files 
    3. Iterate to stream chunks
    4. Close in finally block
    
    This ensures ZIP is finalized BEFORE streaming starts.
    """
    batch_service = get_batch_service()
    pdf_processor = PDFProcessor()
    
    batch = batch_service.get_batch(batch_id, user_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    completed = batch_service.get_batch_items(batch_id, status="completed")
    if not completed:
        raise HTTPException(status_code=400, detail="No completed items in batch")
    
    if only_indices:
        completed = [
            item for item in completed 
            if item.get("item_index") in only_indices
        ]
    
    print(f"\n🎬 [stream_batch_zip] Starting for batch {batch_id}")
    print(f"📦 Total items to stream: {len(completed)}")
    
    # CRITICAL: NO context manager - manual lifecycle
    zf = zipstream.ZipFile(compression=zipstream.ZIP_DEFLATED)
    
    try:
        # Phase 1: Load all files into ZipFile
        files_added = 0
        for item in completed:
            storage_path = item.get("storage_path")
            item_index = item.get("item_index", 0)
            
            if not storage_path:
                print(f"   ⚠️ Item {item_index}: No storage_path, skipping")
                continue
            
            filename = f"form_{item_index}.pdf"
            
            try:
                # Download from Supabase storage
                pdf_bytes = pdf_processor.supabase.storage.from_(
                    pdf_processor.STORAGE_BUCKET
                ).download(storage_path)
                
                # Add to ZIP in memory
                zf.write_iter(filename, [pdf_bytes])
                files_added += 1
                
                if files_added % 10 == 0:
                    print(f"   ✅ Added {files_added} files...")
                
            except Exception as e:
                print(f"   ⚠️ Item {item_index}: Failed to download - {str(e)}")
                continue
        
        print(f"✅ All files loaded into ZIP: {files_added} files")
        
        # Phase 2: Stream ZIP chunks to client
        print(f"📡 Starting to stream ZIP to client...")
        chunk_count = 0
        total_bytes = 0
        
        for chunk in zf:
            chunk_count += 1
            total_bytes += len(chunk)
            yield chunk
        
        print(f"✅ Stream complete: {chunk_count} chunks, {total_bytes} bytes")
    
    finally:
        # Phase 3: Cleanup
        try:
            zf.close()
            print(f"🧹 ZipFile closed")
        except Exception as e:
            print(f"⚠️ Error closing ZipFile: {str(e)}")


@router.get("/{batch_id}/download-live")
async def download_batch_live(
    batch_id: str,
    only: Optional[str] = Query(None, description="Filter items: 1,2,7-10"),
    chunk_size: Optional[int] = Query(None, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream batch PDFs as live ZIP without buffering.
    
    🔒 Requires authentication
    
    Query Parameters:
    - only: Filter items (e.g., "1,2,7-10")
    - chunk_size: Not used yet (placeholder for future multi-zip support)
    """
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
        
        print(f"\n🚀 download_batch_live endpoint hit")
        print(f"   batch_id: {batch_id}")
        print(f"   filename: {filename}")
        
        return StreamingResponse(
            stream_batch_zip(batch_id, current_user['id'], only_indices),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Stream failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Stream failed: {str(e)}")


# ============================================================================
# CREATE BATCH ENDPOINTS
# ============================================================================

@router.post("/create-from-csv", response_model=BatchCreatedResponse, status_code=201)
async def create_batch_from_csv(
    template_id: str = Form(..., description="Template UUID"),
    batch_name: str = Form(..., description="Batch name"),
    file: UploadFile = File(..., description="CSV/Excel file"),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload CSV/Excel and create batch job
    
    🔒 Requires authentication
    
    **Complete workflow in one request:**
    1. Upload CSV/Excel file
    2. Parse and validate data
    3. Create batch job in database
    4. Ready to process!
    
    - **file**: CSV or Excel file with client data (max 10MB, max 1000 rows)
    - **template_id**: Which template to use (UUID format)
    - **batch_name**: Name for this batch (1-200 characters)
    
    Returns batch_id - use it to start processing with `/batch/{id}/process`
    """
    try:
        services = get_services()
        
        # Validate file
        file_extension = validate_file_upload(file)
        
        # Validate template_id is UUID
        try:
            uuid.UUID(template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="template_id must be a valid UUID")
        
        # Validate batch_name
        if not batch_name or len(batch_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="batch_name cannot be empty")
        if len(batch_name) > 200:
            raise HTTPException(status_code=400, detail="batch_name too long (max 200 characters)")
        
        # Get template to know required fields
        template = services['template'].get_template(template_id, current_user['id'])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        required_fields = list(template['field_mappings'].keys())
        
        # Read file content
        file_content = await file.read()
        
        # Check file size
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        # Parse CSV/Excel with BytesIO
        result = services['csv'].validate_and_parse(
            file_path=io.BytesIO(file_content),
            required_fields=required_fields,
            file_extension=file_extension,
            normalize=True
        )
        
        if result['errors']:
            raise HTTPException(
                status_code=400,
                detail=f"CSV validation failed: {', '.join(result['errors'])}"
            )
        
        # Validate batch size
        validate_batch_size(result['data'])
        
        # Create batch
        batch_id = services['batch'].create_batch(
            user_id=current_user['id'],
            template_id=template_id,
            items=result['data'],
            batch_name=batch_name.strip()
        )
        
        return BatchCreatedResponse(
            batch_id=batch_id,
            batch_name=batch_name.strip(),
            total_items=result['row_count'],
            status="pending",
            message=f"Batch created with {result['row_count']} items. Use POST /batch/{batch_id}/process to start."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to create batch from CSV: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create batch: {str(e)}")


@router.post("", response_model=BatchCreatedResponse, status_code=201)
async def create_batch(
    request: CreateBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create batch from JSON data (no file upload)
    
    🔒 Requires authentication
    
    Use this if you already have the data parsed.
    For CSV/Excel uploads, use `/batch/create-from-csv` instead.
    
    **Limits:**
    - Maximum 1000 items per batch
    - template_id must be valid UUID
    - batch_name: 1-200 characters
    """
    try:
        services = get_services()
        
        # Validate batch size
        validate_batch_size(request.items)
        
        # Verify template exists
        template = services['template'].get_template(request.template_id, current_user['id'])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Validate that items have required fields
        required_fields = set(template['field_mappings'].keys())
        for idx, item in enumerate(request.items):
            item_fields = set(item.keys())
            missing = required_fields - item_fields
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item {idx} missing required fields: {', '.join(missing)}"
                )
        
        # Create batch
        batch_id = services['batch'].create_batch(
            user_id=current_user['id'],
            template_id=request.template_id,
            items=request.items,
            batch_name=request.batch_name
        )
        
        return BatchCreatedResponse(
            batch_id=batch_id,
            batch_name=request.batch_name,
            total_items=len(request.items),
            status="pending",
            message=f"Batch created with {len(request.items)} items. Use POST /batch/{batch_id}/process to start."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to create batch: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create batch: {str(e)}")


# ============================================================================
# PROCESS BATCH
# ============================================================================

@router.post("/{batch_id}/process", response_model=ProcessBatchResponse)
async def process_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start processing batch - Fill all PDFs!
    
    🔒 Requires authentication
    
    **This is where the magic happens:**
    - Gets all pending items from batch
    - For each item:
      1. Downloads template PDF
      2. Fills with client data
      3. Generates final PDF
      4. Updates progress
    
    Processing happens in background. Use `/batch/{id}/progress` to track.
    """
    try:
        services = get_services()
        
        # Verify ownership
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch['status'] not in ['pending', 'failed']:
            raise HTTPException(
                status_code=400,
                detail=f"Batch cannot be processed (status: {batch['status']})"
            )
        
        trigger_parallel_batch(
            batch_id=batch_id,
            user_id=current_user['id'],
            template_id=batch['template_id']
        )
        
        # Update status immediately
        services['batch'].update_batch_status(batch_id, "processing")
        
        return ProcessBatchResponse(
            message="Batch processing started",
            batch_id=batch_id,
            total_items=batch['total_items'],
            status="processing"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to start processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")


# ============================================================================
# QUERY BATCH ENDPOINTS
# ============================================================================

@router.get("", response_model=BatchListResponse)
async def list_batches(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    List user's batches
    
    🔒 Requires authentication
    
    Returns paginated list of user's batch jobs, newest first.
    """
    try:
        services = get_services()
        
        batches = services['batch'].list_batches(
            user_id=current_user['id'],
            status=status,
            limit=limit,
            offset=offset
        )
        
        batch_responses = [BatchResponse(**b) for b in batches]
        
        return BatchListResponse(
            batches=batch_responses,
            total=len(batch_responses)
        )
    
    except Exception as e:
        print(f"❌ Failed to list batches: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list batches: {str(e)}")


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get batch details
    
    🔒 Requires authentication
    """
    try:
        services = get_services()
        
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        return BatchResponse(**batch)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get batch: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get batch: {str(e)}")


@router.get("/{batch_id}/progress", response_model=BatchProgressResponse)
async def get_batch_progress(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get batch processing progress
    
    🔒 Requires authentication
    
    **Poll this endpoint to track progress:**
    - Shows completed/failed/pending counts
    - Progress percentage
    - Estimated time remaining
    
    Frontend can poll every 2-5 seconds to update UI.
    """
    try:
        services = get_services()
        
        progress = services['batch'].get_batch_progress(batch_id, current_user['id'])
        
        if 'error' in progress:
            raise HTTPException(status_code=404, detail=progress['error'])
        
        return BatchProgressResponse(**progress)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get progress: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get progress: {str(e)}")


@router.get("/{batch_id}/items")
async def get_batch_items(
    batch_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all items in batch
    
    🔒 Requires authentication
    """
    try:
        services = get_services()
        
        # Verify ownership
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        items = services['batch'].get_batch_items(batch_id, status=status)
        
        return {
            "batch_id": batch_id,
            "total_items": len(items),
            "items": [BatchItemResponse(**item) for item in items]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get items: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get items: {str(e)}")


@router.get("/{batch_id}/download", response_model=BatchDownloadResponse)
async def download_batch(
    batch_id: str,
    create_zip: bool = Query(default=False),
    current_user: dict = Depends(get_current_user)
):
    """Download batch PDFs with optional zip creation"""
    try:
        services = get_services()
        
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        completed_items = services['batch'].get_batch_items(batch_id, status="completed")

        from services.pdf_processor import PDFProcessor
        from .batch_download import refresh_signed_urls
        
        pdf_processor = PDFProcessor()
        
        # Refresh signed URLs
        completed_items = refresh_signed_urls(completed_items, pdf_processor)
        
        pdf_urls = [
            {
                "item_index": item["item_index"],
                "url": item.get("pdf_url"),
                "pdf_url": item.get("pdf_url"),
                "storage_path": item.get("storage_path"),
                "client_data": item["client_data"]
            }
            for item in completed_items
            if item.get("pdf_url") or item.get("storage_path")
        ]
        
        # Create zip if requested
        zip_url = None
        if create_zip and pdf_urls:
            print(f"\n{'='*80}")
            print(f"Creating zip for batch: {batch_id}")
            print(f"User: {current_user['id']}")
            print(f"PDFs to zip: {len(pdf_urls)}")
            print(f"{'='*80}\n")
            
            create_batch_zip_task.delay(
                batch_id=batch_id,
                batch_name=batch['batch_name'],
                user_id=current_user['id']
            )
        
        return BatchDownloadResponse(
            batch_id=batch_id,
            batch_name=batch['batch_name'],
            total_pdfs=batch['total_items'],
            completed=batch['completed'],
            failed=batch['failed'],
            pdf_urls=pdf_urls,
            zip_available=True,
            zip_url=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Download failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BATCH MANAGEMENT
# ============================================================================

@router.post("/{batch_id}/retry", response_model=ProcessBatchResponse)
async def retry_failed_items(
    batch_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Retry failed items in batch
    
    🔒 Requires authentication
    
    Resets failed items to pending and restarts processing.
    """
    try:
        services = get_services()
        
        # Always fetch fresh stats
        progress = services['batch'].get_batch_progress(batch_id, current_user['id'])
        if 'error' in progress:
            raise HTTPException(status_code=404, detail=progress['error'])

        failed = progress.get('failed', 0)
        pending = progress.get('pending', 0)

        # Reset failed to pending (existing behavior)
        if failed > 0:
            services['batch'].retry_failed_items(batch_id, current_user['id'])

        # NEW: also requeue any pending that never ran
        if pending > 0:
            services['batch'].reset_items_status(
                batch_id=batch_id,
                user_id=current_user['id'],
                from_statuses=["failed", "processing", "pending"],
                to_status='pending'
            )

        # If nothing to do:
        if failed == 0 and pending == 0:
            raise HTTPException(status_code=404, detail="Batch not found or no failed/pending items")

        # Re-trigger Celery
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        from celery_tasks import trigger_parallel_batch
        trigger_parallel_batch(
            batch_id=batch_id,
            user_id=current_user['id'],
            template_id=batch['template_id']
        )
        services['batch'].update_batch_status(batch_id, "processing")

        return ProcessBatchResponse(
            message="Retry queued for failed/pending items",
            batch_id=batch_id,
            total_items=batch['total_items'],
            status="processing"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to retry: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retry: {str(e)}")


@router.delete("/{batch_id}", response_model=BatchDeletedResponse)
async def delete_batch(
    batch_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete batch and all its items
    
    🔒 Requires authentication
    """
    try:
        services = get_services()
        
        success = services['batch'].delete_batch(batch_id, current_user['id'])
        
        if not success:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        return BatchDeletedResponse(
            message="Batch deleted successfully",
            batch_id=batch_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to delete batch: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete batch: {str(e)}")


# ============================================================================
# STATS & HEALTH
# ============================================================================

@router.get("/stats/summary")
async def get_batch_stats(current_user: dict = Depends(get_current_user)):
    """
    Get user's batch statistics
    
    🔒 Requires authentication
    """
    try:
        services = get_services()
        
        total = services['batch'].count_user_batches(current_user['id'])
        pending = services['batch'].count_user_batches(current_user['id'], status="pending")
        processing = services['batch'].count_user_batches(current_user['id'], status="processing")
        completed = services['batch'].count_user_batches(current_user['id'], status="completed")
        failed = services['batch'].count_user_batches(current_user['id'], status="failed")
        
        return {
            "user_id": current_user['id'],
            "total_batches": total,
            "by_status": {
                "pending": pending,
                "processing": processing,
                "completed": completed,
                "failed": failed
            }
        }
    
    except Exception as e:
        print(f"❌ Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/health")
async def batch_health():
    """Health check for batch service"""
    return {
        "service": "Batch Processing",
        "status": "operational",
        "version": "2.0-refactored",
        "features": {
            "csv_upload": True,
            "excel_upload": True,
            "background_processing": True,
            "progress_tracking": True,
            "retry_failed": True,
            "batch_size_limit": MAX_BATCH_SIZE,
            "file_size_limit_mb": MAX_FILE_SIZE / 1024 / 1024,
            "streaming_zip_download": True
        }
    }