"""
Batch Routes - With Template Entitlement + Forms Checks for Bulk Processing
"""

from celery_tasks import trigger_parallel_batch, create_batch_zip_task
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
import zipstream
import os
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
    BatchItemResponse,
    SingleFillRequest,
)
from services.batch_service import get_batch_service
from services.csv_processor import get_csv_processor
from services.template_service import get_template_service
from services.auth import get_current_user
from services.entitlement_service import (
    ensure_template_single_fill_access,
    get_entitlement_service,
    EntitlementError,
)

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

entitlement_service = get_entitlement_service()


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


def create_streaming_zip_sync(
    batch_id: str,
    user_id: str,
    only_indices: Optional[Set[int]] = None,
) -> tuple:
    """
    Create ZIP file synchronously (for Celery task).
    Returns (zip_storage_path, signed_url) for immediate download.
    """
    batch_service = get_batch_service()
    pdf_processor = PDFProcessor()
    
    batch = batch_service.get_batch(batch_id, user_id)
    if not batch:
        raise Exception(f"Batch not found: {batch_id}")
    
    completed = batch_service.get_batch_items(batch_id, status="completed")
    if not completed:
        raise Exception(f"No completed items in batch {batch_id}")
    
    if only_indices:
        completed = [
            item for item in completed 
            if item.get("item_index") in only_indices
        ]
    
    print(f"\n📦 [create_streaming_zip_sync] Starting for batch {batch_id}")
    print(f"📦 Total items: {len(completed)}")
    
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', mode='wb') as tmp_zip:
        zip_path = tmp_zip.name
    
    try:
        import zipfile as zf_module
        files_added = 0
        
        with zf_module.ZipFile(zip_path, 'w', zf_module.ZIP_DEFLATED) as zipf:
            for item in completed:
                storage_path = item.get("storage_path")
                item_index = item.get("item_index", 0)
                
                if not storage_path:
                    print(f"   ⚠️ Item {item_index}: No storage_path, skipping")
                    continue
                
                filename = f"form_{item_index}.pdf"
                
                try:
                    pdf_bytes = pdf_processor.supabase.storage.from_(
                        pdf_processor.STORAGE_BUCKET
                    ).download(storage_path)
                    
                    zipf.writestr(filename, pdf_bytes)
                    files_added += 1
                    
                    if files_added % 10 == 0:
                        print(f"   ✅ Added {files_added} files...")
                    
                except Exception as e:
                    print(f"   ⚠️ Item {item_index}: Failed - {str(e)}")
                    continue
        
        print(f"✅ ZIP created locally: {files_added} files")
        
        zip_size = os.path.getsize(zip_path)
        print(f"📤 Uploading {zip_size} bytes to Supabase...")
        
        zip_storage_path = f"{user_id}/batches/{batch_id}/download.zip"
        
        with open(zip_path, 'rb') as f:
            pdf_processor.supabase.storage.from_(
                pdf_processor.STORAGE_BUCKET
            ).upload(
                path=zip_storage_path,
                file=f.read(),
                file_options={"content-type": "application/zip", "upsert": "true"}
            )
        
        signed_url_response = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).create_signed_url(zip_storage_path, 3600)
        
        signed_url = signed_url_response['signedURL']
        
        print(f"✅ ZIP uploaded and ready for download")
        print(f"✅ URL: {signed_url[:80]}...")
        
        return (zip_storage_path, signed_url)
    
    finally:
        if os.path.exists(zip_path):
            os.unlink(zip_path)
            print(f"🧹 Temp ZIP cleaned up")


async def stream_batch_zip(
    batch_id: str,
    user_id: str,
    only_indices: Optional[Set[int]] = None,
):
    batch_service = get_batch_service()
    
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
    
    print(f"\n🎬 [stream_batch_zip] Batch {batch_id} - {len(completed)} items")
    
    from celery_tasks import create_zip_task
    
    print(f"📤 Queueing ZIP creation to Celery...")
    task = create_zip_task.delay(
        batch_id=batch_id,
        user_id=user_id,
        only_indices=list(only_indices) if only_indices else None
    )
    
    print(f"⏳ Waiting for ZIP to be created (task: {task.id})...")
    
    try:
        result = task.get(timeout=300)
        zip_storage_path, signed_url = result
        
        print(f"✅ ZIP created, streaming from storage...")
        
        pdf_processor = PDFProcessor()
        
        zip_bytes = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).download(zip_storage_path)
        
        print(f"✅ Downloaded ZIP ({len(zip_bytes)} bytes), streaming to client...")
        
        chunk_size = 65536
        for i in range(0, len(zip_bytes), chunk_size):
            yield zip_bytes[i:i + chunk_size]
        
        print(f"✅ Stream complete")
    
    except Exception as e:
        print(f"❌ ZIP creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"ZIP creation failed: {str(e)}")


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
    default_font: str | None = Form(None, description="Batch default font"),
    default_size: int | None = Form(None, description="Batch default font size"),
    default_align: str | None = Form(None, description="Batch default align: center|top|bottom"),
    default_image_width: int | None = Form(None, description="Batch default image width"),
    default_image_height: int | None = Form(None, description="Batch default image height"),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload CSV/Excel and create batch job with optional batch-wide defaults.
    
    🔒 Two-layer check:
    1. Template entitlement (must own template or have Library Pass for paid official templates)
    2. Forms availability (must have enough forms_included_in_plan for bulk processing)
    """
    try:
        services = get_services()

        file_extension = validate_file_upload(file)

        try:
            uuid.UUID(template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="template_id must be a valid UUID")

        if not batch_name or len(batch_name.strip()) == 0:
            raise HTTPException(status_code=400, detail="batch_name cannot be empty")
        if len(batch_name) > 200:
            raise HTTPException(status_code=400, detail="batch_name too long (max 200 characters)")

        template = services['template'].get_template(template_id, current_user['id'])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # ✅ STEP 1: Enforce template entitlement (Flow 2: bulk processing)
        # For paid official templates, user needs either:
        # - Single template purchase OR Library Pass for BULK usage
        try:
            ensure_template_single_fill_access(current_user["id"], template)
        except EntitlementError as ee:
            # Return 402 Payment Required with item count hint
            raise HTTPException(
                status_code=402,
                detail=ee.detail,
                headers={"X-Requires-Purchase": "true"}
            )

        required_fields = list(template['field_mappings'].keys())

        file_content = await file.read()

        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )

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

        validate_batch_size(result['data'])

        # ✅ STEP 2: Check forms availability BEFORE creating batch
        # This prevents orphaned batches when user lacks forms
        forms_needed = len(result['data'])
        try:
            entitlement_service.ensure_forms_available(
                user_id=current_user["id"],
                forms_needed=forms_needed,
            )
        except EntitlementError as ee:
            # Return 403 Forbidden with shortfall details
            raise HTTPException(
                status_code=403,
                detail=ee.detail,
                headers={
                    "X-Forms-Needed": str(forms_needed),
                    "X-Forms-Available": str(ee.forms_available or 0)
                }
            )

        options: dict = {}

        allowed_align = {"center", "top", "bottom"}
        align_norm = None
        if default_align is not None:
            align_norm = str(default_align).strip().lower()
            if align_norm not in allowed_align:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid default_align '{default_align}'. Allowed: {', '.join(sorted(allowed_align))}"
                )

        if default_font:
            options["default_font"] = default_font

        if default_size is not None:
            try:
                options["default_size"] = int(default_size)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="default_size must be an integer")

        if align_norm:
            options["default_align"] = align_norm

        image_defaults: dict = {}
        if default_image_width is not None:
            try:
                image_defaults["width"] = int(default_image_width)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="default_image_width must be an integer")
        if default_image_height is not None:
            try:
                image_defaults["height"] = int(default_image_height)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="default_image_height must be an integer")

        if image_defaults:
            options["image_defaults"] = image_defaults
            options["default_image_width"] = image_defaults.get("width")
            options["default_image_height"] = image_defaults.get("height")

        batch_id = services['batch'].create_batch(
            user_id=current_user['id'],
            template_id=template_id,
            items=result['data'],
            batch_name=batch_name.strip(),
            options=options if options else {}
        )

        return BatchCreatedResponse(
            batch_id=batch_id,
            batch_name=batch_name.strip(),
            total_items=result['row_count'],
            status="pending",
            options=options,
            message=f"Batch created with {result['row_count']} items. Use POST /batch/{batch_id}/process to start."
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to create batch from CSV: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create batch from CSV: {str(e)}")


@router.post("", response_model=BatchCreatedResponse, status_code=201)
async def create_batch(
    request: CreateBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create batch from JSON data (no file upload)
    
    🔒 Two-layer check:
    1. Template entitlement
    2. Forms availability
    """
    try:
        services = get_services()
        
        validate_batch_size(request.items)
        
        template = services['template'].get_template(request.template_id, current_user['id'])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # ✅ STEP 1: Template entitlement
        try:
            ensure_template_single_fill_access(current_user["id"], template)
        except EntitlementError as ee:
            raise HTTPException(
                status_code=402,
                detail=ee.detail,
                headers={"X-Requires-Purchase": "true"}
            )
        
        required_fields = set(template['field_mappings'].keys())
        for idx, item in enumerate(request.items):
            item_fields = set(item.keys())
            missing = required_fields - item_fields
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item {idx} missing required fields: {', '.join(missing)}"
                )
        
        # ✅ STEP 2: Forms availability
        forms_needed = len(request.items)
        try:
            entitlement_service.ensure_forms_available(
                user_id=current_user["id"],
                forms_needed=forms_needed,
            )
        except EntitlementError as ee:
            raise HTTPException(
                status_code=403,
                detail=ee.detail,
                headers={
                    "X-Forms-Needed": str(forms_needed),
                    "X-Forms-Available": str(ee.forms_available or 0)
                }
            )
        
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
    
    🔒 Re-validates forms availability at processing time
    (user may have consumed forms between batch creation and processing)
    """
    try:
        services = get_services()
        
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch['status'] not in ['pending', 'failed']:
            raise HTTPException(
                status_code=400,
                detail=f"Batch cannot be processed (status: {batch['status']})"
            )

        # ✅ Re-validate template entitlement (shouldn't fail, but defensive)
        template = services["template"].get_template(batch["template_id"], current_user["id"])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found for batch")

        try:
            ensure_template_single_fill_access(current_user["id"], template)
        except EntitlementError as ee:
            raise HTTPException(status_code=402, detail=ee.detail)

        # ✅ CRITICAL: Re-check forms availability at processing time
        # User may have used forms between batch creation and now
        pending_items = services["batch"].get_batch_items(batch_id, status="pending")
        forms_needed = len(pending_items)
        
        try:
            entitlement_service.ensure_forms_available(
                user_id=current_user["id"],
                forms_needed=forms_needed,
            )
        except EntitlementError as ee:
            raise HTTPException(
                status_code=403,
                detail=ee.detail,
                headers={
                    "X-Forms-Needed": str(forms_needed),
                    "X-Forms-Available": str(ee.forms_available or 0)
                }
            )
        
        trigger_parallel_batch(
            batch_id=batch_id,
            user_id=current_user['id'],
            template_id=batch['template_id']
        )
        
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
    List user's batches (paginated, newest first)
    """
    try:
        services = get_services()
        batch_service = services["batch"]

        batches, total = batch_service.list_batches(
            user_id=current_user["id"],
            status=status,
            limit=limit,
            offset=offset,
        )

        batch_responses = [BatchResponse(**b) for b in batches]

        return BatchListResponse(
            batches=batch_responses,
            total=total,
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
        
        progress = services['batch'].get_batch_progress(batch_id, current_user['id'])
        if 'error' in progress:
            raise HTTPException(status_code=404, detail=progress['error'])

        failed = progress.get('failed', 0)
        pending = progress.get('pending', 0)

        if failed > 0:
            services['batch'].retry_failed_items(batch_id, current_user['id'])

        if pending > 0:
            services['batch'].reset_items_status(
                batch_id=batch_id,
                user_id=current_user['id'],
                from_statuses=["failed", "processing", "pending"],
                to_status='pending'
            )

        if failed == 0 and pending == 0:
            raise HTTPException(status_code=404, detail="Batch not found or no failed/pending items")

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
    return {
        "service": "Batch Processing",
        "status": "operational",
        "version": "2.1-with-entitlements",
        "features": {
            "csv_upload": True,
            "excel_upload": True,
            "background_processing": True,
            "progress_tracking": True,
            "retry_failed": True,
            "batch_size_limit": MAX_BATCH_SIZE,
            "file_size_limit_mb": MAX_FILE_SIZE / 1024 / 1024,
            "streaming_zip_download": True,
            "template_entitlement_check": True,
            "forms_availability_check": True
        }
    }


@router.post("/single-from-json", response_model=ProcessBatchResponse, status_code=201)
async def single_fill_from_json(
    request: SingleFillRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Flow 1 (backend implementation): Single-fill using batch pipeline.

    - Creates a batch with exactly ONE item
    - Enforces Flow 1 entitlement rules via ensure_template_single_fill_access
    - Stores options in batch.options (so programmable options still work)
    - Immediately triggers parallel processing for that one item
    - Returns a normal ProcessBatchResponse (status: processing)

    NOTE: Single-fill DOES NOT consume forms_included_in_plan.
    Only bulk/batch processing consumes forms via /batch/{id}/process.
    """
    try:
        services = get_services()
        template_service = services["template"]

        # 1) Validate template UUID
        try:
            uuid.UUID(request.template_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="template_id must be a valid UUID")

        # 2) Load template
        template = template_service.get_template(request.template_id, current_user["id"])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # 3) Enforce Flow 1 access rules (custom owner, free official, paid official)
        try:
            ensure_template_single_fill_access(current_user["id"], template)
        except EntitlementError as ee:
            raise HTTPException(status_code=402, detail=ee.detail)

        # 4) Validate required fields vs data
        required_fields = set(template["field_mappings"].keys())
        item_fields = set(request.data.keys())
        missing = required_fields - item_fields
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(sorted(missing))}",
            )

        # 5) Build batch_name and items list (ONE row)
        batch_name = (request.batch_name or f"Single Fill - {template.get('name', 'Untitled')}").strip()
        if not batch_name:
            raise HTTPException(status_code=400, detail="batch_name cannot be empty")
        if len(batch_name) > 200:
            raise HTTPException(status_code=400, detail="batch_name too long (max 200 characters)")

        items = [request.data]

        validate_batch_size(items)

        # 6) Options go into batch.options
        options = request.options or {}

        # ❌ NO forms entitlement reservation here
        # Single-fill is "entitlement only" (template access),
        # not metered against forms_included_in_plan.

        # 7) Create batch
        batch_id = services["batch"].create_batch(
            user_id=current_user["id"],
            template_id=request.template_id,
            items=items,
            batch_name=batch_name,
            options=options,
        )

        # 8) Trigger normal parallel batch processing for this ONE item
        trigger_parallel_batch(
            batch_id=batch_id,
            user_id=current_user["id"],
            template_id=request.template_id,
        )

        # 9) Immediately mark as processing
        services["batch"].update_batch_status(batch_id, "processing")

        return ProcessBatchResponse(
            message="Single-fill processing started",
            batch_id=batch_id,
            total_items=1,
            status="processing",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to start single-fill: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start single-fill: {str(e)}")