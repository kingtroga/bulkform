"""
Batch Routes - Main API Router
API endpoints for batch PDF generation from CSV/Excel
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from typing import Optional
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
        
        # Start processing in background (non-async to avoid blocking)
        background_tasks.add_task(
            process_batch_sync,
            batch_id,
            current_user['id'],
            batch['template_id']
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
            
            zip_url = await create_batch_zip(
                batch_id=batch_id,
                batch_name=batch['batch_name'],
                pdf_items=pdf_urls,
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
            zip_url=zip_url
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
        
        # Retry failed items
        success = services['batch'].retry_failed_items(batch_id, current_user['id'])
        
        if not success:
            raise HTTPException(status_code=404, detail="Batch not found or no failed items")
        
        # Get batch to start processing
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        
        # Start processing in background
        background_tasks.add_task(
            process_batch_sync,
            batch_id,
            current_user['id'],
            batch['template_id']
        )
        
        return ProcessBatchResponse(
            message="Retry started for failed items",
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
            "file_size_limit_mb": MAX_FILE_SIZE / 1024 / 1024
        }
    }