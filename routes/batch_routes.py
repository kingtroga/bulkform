"""
Batch Routes - FIXED VERSION
API endpoints for batch PDF generation from CSV/Excel

All critical issues from analysis document have been fixed:
✅ All imports at module level
✅ Proper async/sync handling
✅ Better error handling
✅ Temp file cleanup
✅ Deterministic session IDs
✅ Batch size limits
✅ Field validation
✅ Proper BytesIO handling
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from typing import Optional
import asyncio
import uuid
import os
import io
import tempfile
from pathlib import Path
    

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
from services.pdf_processor import PDFProcessor
from services.image_service import get_image_service

router = APIRouter(prefix="/api/batch", tags=["Batch Processing"])

# Configuration constants
MAX_BATCH_SIZE = 1000  # Maximum items per batch
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_services():
    """Get service instances (lazy initialization)"""
    return {
        'batch': get_batch_service(),
        'csv': get_csv_processor(),
        'template': get_template_service()
    }


def validate_file_upload(file: UploadFile) -> str:
    """
    Validate uploaded file
    
    Returns:
        File extension if valid
        
    Raises:
        HTTPException if invalid
    """
    filename = file.filename.lower()
    ext = Path(filename).suffix
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size (if available)
    if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    return ext


def validate_batch_size(items: list) -> None:
    """
    Validate batch size
    
    Raises:
        HTTPException if too large
    """
    if len(items) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch too large. Maximum {MAX_BATCH_SIZE} items allowed. You have {len(items)} items."
        )
    
    if len(items) == 0:
        raise HTTPException(
            status_code=400,
            detail="Batch cannot be empty"
        )


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
# PROCESS BATCH (THE BIG ONE!)
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
            services['batch'].update_batch_status(batch_id, "completed")
            return
        
        # Process each item sequentially (TODO: Add concurrent processing)
        for item in items:
            try:
                print(f"\n📄 Processing item {item['item_index']} of {len(items)}...")
                
                # Mark as processing
                services['batch'].update_batch_item(item['id'], "processing")
                
                # Fill PDF using helper function
                pdf_url = fill_single_pdf_sync(
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
                    pdf_url=pdf_url
                )
                
                services['batch'].increment_batch_counters(batch_id, completed=1)
                
                print(f"✅ Item {item['item_index']} completed: {pdf_url}")
            
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Item {item['item_index']} failed: {error_msg}")
                
                services['batch'].update_batch_item(
                    item['id'],
                    "failed",
                    error_message=error_msg
                )
                
                services['batch'].increment_batch_counters(batch_id, failed=1)
        
        print(f"\n🎉 Batch processing complete: {batch_id}")
    
    except Exception as e:
        print(f"❌ Batch processing failed critically: {str(e)}")
        try:
            services = get_services()
            services['batch'].update_batch_status(batch_id, "failed")
        except:
            print(f"❌ Could not update batch status to failed")


def fill_single_pdf_sync(
    template: dict,
    client_data: dict,
    user_id: str,
    batch_id: str,
    item_index: int
) -> str:
    """Fill a single PDF with text AND images"""
    pdf_processor = PDFProcessor()
    image_service = get_image_service()
    session_id = f"{batch_id}_{item_index}"
    temp_pdf_path = None
    temp_image_paths = []  # Track temp images for cleanup
    
    try:
        # Steps 1-3: Download template, convert to images (same as before)
        storage_path = template['pdf_url']
        pdf_bytes = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).download(storage_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp:
            tmp.write(pdf_bytes)
            temp_pdf_path = tmp.name
        
        num_pages = pdf_processor.pdf_to_images(temp_pdf_path, session_id)
        
        # Step 4: Build text data AND image data
        field_mappings = template['field_mappings']
        pages_data = {}      # Text fields
        images_data = {}     # Image fields  ← NEW!
        
        for field_name, field_config in field_mappings.items():
            page = field_config.get('page', 1)
            field_type = field_config.get('type', 'text')
            
            # Handle IMAGE fields  ← NEW!
            if field_type in ['image', 'signature', 'stamp']:
                image_ref = client_data.get(field_name, '')
                
                if image_ref and image_ref.strip():
                    # Resolve image reference to file path
                    try:
                        # Check if local file
                        if os.path.exists(image_ref):
                            image_path = image_ref
                        else:
                            # Download from database (by ID or name)
                            image_bytes = image_service.download_image_bytes(
                                image_ref, user_id
                            )
                            
                            if image_bytes:
                                # Save to temp file
                                with tempfile.NamedTemporaryFile(
                                    delete=False, suffix='.png'
                                ) as tmp_img:
                                    tmp_img.write(image_bytes)
                                    image_path = tmp_img.name
                                
                                temp_image_paths.append(image_path)
                                print(f"  📥 Downloaded image: {image_ref}")
                            else:
                                print(f"  ⚠️  Image not found: {image_ref}")
                                continue
                        
                        # Add to images_data
                        if page not in images_data:
                            images_data[page] = []
                        
                        images_data[page].append({
                            'image_path': image_path,
                            'x': field_config['x'],
                            'y': field_config['y'],
                            'width': field_config.get('width', 200),
                            'height': field_config.get('height', 60)
                        })
                    
                    except Exception as e:
                        print(f"  ❌ Failed to load image {image_ref}: {str(e)}")
                
                continue  # Don't add to text fields
            
            # Handle TEXT fields (same as before)
            if page not in pages_data:
                pages_data[page] = []
            
            value = client_data.get(field_name, '')
            
            # Checkbox handling
            if field_type == 'checkbox':
                if isinstance(value, bool):
                    value = field_config.get('text', '●') if value else ''
                elif value in ['true', 'True', '1', 'yes', 'Yes', 'TRUE', 'YES']:
                    value = field_config.get('text', '●')
                elif value and str(value).strip():
                    value = field_config.get('text', '●')
                else:
                    value = ''
            
            value = str(value) if value is not None else ''
            
            pages_data[page].append({
                'text': value,
                'x': field_config['x'],
                'y': field_config['y'],
                'size': field_config.get('size', 12),
                'font': field_config.get('font', 'arial'),
                'align': field_config.get('align', 'left')
            })
        
        # Step 5: Fill text fields
        print(f"  ✍️  Filling {sum(len(t) for t in pages_data.values())} text field(s)...")
        for page_num, text_data in pages_data.items():
            if text_data:
                pdf_processor.write_text_on_page(session_id, page_num, text_data)
        
        # Step 5.5: Fill image fields  ← NEW!
        if images_data:
            total_images = sum(len(imgs) for imgs in images_data.values())
            print(f"  🖼️  Filling {total_images} image field(s)...")
            for page_num, image_list in images_data.items():
                if image_list:
                    pdf_processor.add_images_to_page(session_id, page_num, image_list)
        
        # Step 6: Generate final PDF
        result = pdf_processor.create_pdf_with_upload(
            session_id=session_id,
            user_id=user_id,
            num_pages=num_pages,
            output_name=f"batch_{batch_id}_item_{item_index}.pdf"
        )
        
        storage_url = result['storage_url']
        
        # Step 7: Cleanup
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)
        
        # Cleanup temp images  ← NEW!
        for img_path in temp_image_paths:
            if os.path.exists(img_path):
                os.unlink(img_path)
        
        pdf_processor.cleanup_folders(session_id)
        
        return storage_url
    
    except Exception as e:
        # Cleanup on error
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except:
                pass
        
        # Cleanup temp images
        for img_path in temp_image_paths:
            if os.path.exists(img_path):
                try:
                    os.unlink(img_path)
                except:
                    pass
        
        try:
            pdf_processor.cleanup_folders(session_id)
        except:
            pass
        
        raise Exception(f"PDF generation failed: {str(e)}")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def batch_health():
    """Health check for batch service"""
    return {
        "service": "Batch Processing",
        "status": "operational",
        "version": "2.0-fixed",
        "features": {
            "csv_upload": True,
            "excel_upload": True,
            "background_processing": True,
            "progress_tracking": True,
            "retry_failed": True,
            "batch_size_limit": MAX_BATCH_SIZE,
            "file_size_limit_mb": MAX_FILE_SIZE / 1024 / 1024
        },
        "fixes_applied": [
            "All imports at module level",
            "Proper async/sync handling",
            "Temp file cleanup",
            "Deterministic session IDs",
            "Batch size validation",
            "Field validation",
            "Better error handling"
        ]
    }

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
    current_user: dict = Depends(get_current_user)
):
    """
    Get download URLs for all completed PDFs
    
    🔒 Requires authentication
    
    Returns list of signed download URLs for each completed PDF in the batch.
    URLs are valid for 1 hour.
    """
    try:
        services = get_services()
        
        # Get batch
        batch = services['batch'].get_batch(batch_id, current_user['id'])
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Get completed items
        completed_items = services['batch'].get_batch_items(batch_id, status="completed")
        
        # Build download URLs (they're already signed from storage)
        pdf_urls = [
            {
                "item_index": item['item_index'],
                "url": item['pdf_url'],
                "client_data": item['client_data']
            }
            for item in completed_items
            if item.get('pdf_url')
        ]
        
        return BatchDownloadResponse(
            batch_id=batch_id,
            batch_name=batch['batch_name'],
            total_pdfs=batch['total_items'],
            completed=batch['completed'],
            failed=batch['failed'],
            pdf_urls=pdf_urls,
            zip_available=False,  # TODO: Implement zip creation
            zip_url=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get download URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get download URLs: {str(e)}")


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
# STATS
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


