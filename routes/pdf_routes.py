"""
PDF Routes - FULLY ASYNC OPTIMIZED (FIXED)
🔒 Protected with JWT authentication
💾 Database-backed sessions (survives restarts!)
☁️  Supabase Storage for PDFs
⚡ TRUE ASYNC - No blocking, no pickle errors!
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query
from fastapi.responses import FileResponse
from models.pdf_models import (
    GridResponse, FillTextRequest, FillTextResponse,
    AddImageRequest, AddImageResponse, GeneratePDFResponse,
    SessionInfo, UserSessionsResponse, EncryptedGridResponse,
    EncryptedFillTextRequest, BatchFillTextRequest, EncryptedBatchFillTextRequest,
    BatchFillTextResponse
)
from utils.encryption import encrypt_grid_data, decrypt_data
from services.pdf_processor import PDFProcessor
from services.session_service import SessionService
from services.auth import get_current_user
import os
import shutil
import uuid
from typing import Optional
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

router = APIRouter(prefix="/api/pdf", tags=["PDF Processing"])

# Initialize services
pdf_processor = PDFProcessor()
session_service = SessionService()

# ============================================================================
# ASYNC EXECUTOR - Single Thread Pool (Avoids Pickle Issues!)
# ============================================================================

# Why only ThreadPoolExecutor?
# - ProcessPoolExecutor can't pickle Supabase client (has thread locks)
# - ThreadPoolExecutor is fast enough for our use case
# - Can handle both I/O and CPU work effectively with enough threads

executor = ThreadPoolExecutor(max_workers=30, thread_name_prefix="bulkform")

print("✅ Async executor initialized: 30 threads")


# ============================================================================
# HELPER FUNCTION
# ============================================================================

async def run_async(func, *args, **kwargs):
    """Run any blocking operation in thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor,
        partial(func, *args, **kwargs)
    )


# ============================================================================
# UPLOAD ENDPOINTS
# ============================================================================

@router.post("/upload", response_model=GridResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload PDF and get grid coordinates for all pages
    
    🔒 PROTECTED - Requires JWT token
    💾 Session saved to database (survives server restarts!)
    ⚡ TRULY ASYNC - Non-blocking!
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    user_id = current_user['id']
    
    try:
        # Prepare paths
        upload_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        os.makedirs(upload_path, exist_ok=True)
        pdf_path = f"{upload_path}/original.pdf"
        
        # ⚡ ASYNC: Read file content
        file_content = await file.read()
        
        # ⚡ ASYNC: Save uploaded PDF
        await run_async(lambda: open(pdf_path, "wb").write(file_content))
        
        # ⚡ ASYNC: Upload to Supabase Storage
        storage_path = await run_async(
            pdf_processor.upload_original_pdf,
            pdf_path,
            user_id,
            session_id
        )
        
        # ⚡ ASYNC: Convert to images (CPU-intensive but in thread pool)
        num_pages = await run_async(
            pdf_processor.pdf_to_images,
            pdf_path,
            session_id
        )
        
        # ⚡ ASYNC: Get dimensions
        page_dimensions = await run_async(
            pdf_processor.get_all_page_dimensions,
            session_id,
            num_pages
        )
        
        # ⚡ ASYNC: Save session to database
        await run_async(
            session_service.create_session,
            session_id,
            user_id,
            file.filename,
            num_pages
        )
        
        print(f"✅ Upload complete: {session_id} ({num_pages} pages) - ASYNC!")
        
        return GridResponse(
            total_pages=num_pages,
            pages=page_dimensions,
            dpi=pdf_processor.DPI,
            session_id=session_id
        )
    
    except Exception as e:
        # Cleanup on error
        await run_async(pdf_processor.cleanup_folders, session_id)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/upload-encrypted", response_model=EncryptedGridResponse)
async def upload_pdf_encrypted(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload PDF and return ENCRYPTED grid coordinates"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    session_id = str(uuid.uuid4())
    user_id = current_user['id']
    
    try:
        upload_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        os.makedirs(upload_path, exist_ok=True)
        pdf_path = f"{upload_path}/original.pdf"
        
        file_content = await file.read()
        await run_async(lambda: open(pdf_path, "wb").write(file_content))
        
        storage_path = await run_async(
            pdf_processor.upload_original_pdf,
            pdf_path,
            user_id,
            session_id
        )
        
        num_pages = await run_async(
            pdf_processor.pdf_to_images,
            pdf_path,
            session_id
        )
        
        page_dimensions = await run_async(
            pdf_processor.get_all_page_dimensions,
            session_id,
            num_pages
        )
        
        encrypted_grid = await run_async(
            encrypt_grid_data,
            {"pages": page_dimensions, "dpi": pdf_processor.DPI}
        )
        
        await run_async(
            session_service.create_session,
            session_id,
            user_id,
            file.filename,
            num_pages
        )
        
        return EncryptedGridResponse(
            encrypted_data=encrypted_grid,
            total_pages=num_pages,
            session_id=session_id,
            dpi=pdf_processor.DPI
        )
    
    except Exception as e:
        await run_async(pdf_processor.cleanup_folders, session_id)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


# ============================================================================
# FILL TEXT ENDPOINTS
# ============================================================================

@router.post("/fill-text", response_model=FillTextResponse)
async def fill_text(
    session_id: str,
    request: FillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    """Fill text on a specific PDF page"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        
        if not os.path.exists(session_temp_path):
            print(f"⚠️  Restoring session {session_id}...")
            
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                await run_async(
                    session_service.update_session_status,
                    session_id,
                    "processing"
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found and cannot be restored"
                )
        
        text_data = [item.dict() for item in request.text_data]
        
        await run_async(
            pdf_processor.write_text_on_page,
            session_id,
            request.page_number,
            text_data
        )
        
        return FillTextResponse(
            page_number=request.page_number,
            items_added=len(text_data)
        )
    
    except Exception as e:
        error_message = str(e)
        if "No such file or directory" in error_message:
            raise HTTPException(
                status_code=400,
                detail="File or page doesn't exist. Check session and page number."
            )
        else:
            raise HTTPException(status_code=500, detail=f"Fill text failed: {error_message}")


@router.post("/fill-text-encrypted", response_model=FillTextResponse)
async def fill_text_encrypted(
    request: EncryptedFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    """Fill text on PDF (encrypted)"""
    try:
        decrypted = await run_async(decrypt_data, request.encrypted_data)
        
        session_id = request.session_id
        page_number = decrypted["page_number"]
        text_data = decrypted["text_data"]
        
        session = session_service.get_session(session_id)
        if not session or session["user_id"] != current_user['id']:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                await run_async(
                    session_service.update_session_status,
                    session_id,
                    "processing"
                )
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        await run_async(
            pdf_processor.write_text_on_page,
            session_id,
            page_number,
            text_data
        )
        
        return FillTextResponse(
            page_number=page_number,
            items_added=len(text_data)
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fill text failed: {str(e)}")


# ============================================================================
# IMAGE OPERATIONS
# ============================================================================

@router.post("/add-image", response_model=AddImageResponse)
async def add_image(
    session_id: str = Form(...),
    page_number: int = Form(...),
    x: int = Form(...),
    y: int = Form(...),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    image_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Add generic image to PDF"""
    return await _add_image_helper(
        session_id, page_number, x, y, width, height, 
        image_file, current_user, "images"
    )


@router.post("/add-stamp", response_model=AddImageResponse)
async def add_stamp(
    session_id: str = Form(...),
    page_number: int = Form(...),
    x: int = Form(...),
    y: int = Form(...),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    stamp_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Add stamp to PDF"""
    return await _add_image_helper(
        session_id, page_number, x, y, width, height, 
        stamp_file, current_user, "stamps"
    )


@router.post("/add-signature", response_model=AddImageResponse)
async def add_signature(
    session_id: str = Form(...),
    page_number: int = Form(...),
    x: int = Form(...),
    y: int = Form(...),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    signature_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Add signature to PDF"""
    return await _add_image_helper(
        session_id, page_number, x, y, width, height, 
        signature_file, current_user, "signatures"
    )


async def _add_image_helper(
    session_id: str,
    page_number: int,
    x: int,
    y: int,
    width: Optional[int],
    height: Optional[int],
    image_file: UploadFile,
    current_user: dict,
    subfolder: str
):
    """Shared logic for adding images/stamps/signatures"""
    
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    if not image_file.content_type in ["image/png", "image/jpeg", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Only PNG and JPG allowed")
    
    try:
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                await run_async(
                    session_service.update_session_status,
                    session_id,
                    "processing"
                )
        
        images_folder = f"{pdf_processor.TEMP_FOLDER}/{session_id}/{subfolder}"
        os.makedirs(images_folder, exist_ok=True)
        image_path = f"{images_folder}/{image_file.filename}"
        
        image_content = await image_file.read()
        await run_async(lambda: open(image_path, "wb").write(image_content))
        
        image_data = [{'x': x, 'y': y, 'image_path': image_path}]
        
        if width and height:
            image_data[0]['width'] = width
            image_data[0]['height'] = height
        
        await run_async(
            pdf_processor.add_images_to_page,
            session_id,
            page_number,
            image_data
        )
        
        return AddImageResponse(
            page_number=page_number,
            images_added=1
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add {subfolder} failed: {str(e)}")


# ============================================================================
# GENERATE PDF
# ============================================================================

@router.post("/generate", response_model=GeneratePDFResponse)
async def generate_pdf(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generate final filled PDF and upload to Supabase Storage"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        user_id = current_user['id']
        num_pages = session["num_pages"]
        
        # ⚡ ASYNC: Create PDF
        result = await run_async(
            pdf_processor.create_pdf_with_upload,
            session_id,
            user_id,
            num_pages
        )
        
        # ⚡ ASYNC: Update session
        await run_async(
            session_service.update_session_status,
            session_id,
            "completed",
            result["storage_path"]
        )
        
        # ⚡ ASYNC: Cleanup
        await run_async(pdf_processor.cleanup_folders, session_id)
        
        print(f"✅ PDF generated: {session_id}")
        
        return GeneratePDFResponse(
            pdf_url=result["storage_url"],
            storage_path=result["storage_path"],
            total_pages=num_pages
        )
    
    except Exception as e:
        await run_async(
            session_service.update_session_status,
            session_id,
            "failed"
        )
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# ============================================================================
# GET ORIGINAL PDF FOR TEMPLATE CREATION
# ============================================================================

@router.get("/get-original/{session_id}")
async def get_original_pdf(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves the original PDF file (before any filling) for template creation.
    
    This is necessary because the template API requires the file object, 
    and the client needs to re-upload it via multipart/form-data.
    """
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Define paths
    user_id = current_user['id']
    local_pdf_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}/original.pdf"
    
    # CRITICAL: Use the specified storage path convention
    original_storage_path = f"{user_id}/{session_id}/original.pdf"
    
    try:
        # 1. Check if the file still exists locally (best case)
        if os.path.exists(local_pdf_path):
            return FileResponse(
                local_pdf_path,
                media_type="application/pdf",
                filename=session["filename"]
            )
        
        # 2. If not local, restore it from Supabase Storage
        elif session.get("storage_path"):
            
            print(f"⚠️ Restoring original PDF from storage: {original_storage_path}")

            # ⚡ ASYNC: Download file from storage to temp folder
            await run_async(
                pdf_processor.download_file_from_storage,
                original_storage_path,
                local_pdf_path
            )

            # ⚡ ASYNC: Update session status back to processing after restoration
            await run_async(
                session_service.update_session_status,
                session_id,
                "processing"
            )
            
            # Now serve the newly downloaded file
            return FileResponse(
                local_pdf_path,
                media_type="application/pdf",
                filename=session["filename"]
            )

        raise HTTPException(status_code=404, detail="Original PDF not found in session storage.")

    except HTTPException:
        # Re-raise 403/404 errors
        raise
    except Exception as e:
        print(f"Error fetching original PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve original PDF: {str(e)}") 

# ============================================================================
# BATCH OPERATIONS (PARALLEL!)
# ============================================================================

@router.post("/fill-text-batch", response_model=BatchFillTextResponse)
async def fill_text_batch(
    session_id: str,
    request: BatchFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    """Fill text on MULTIPLE pages at once - IN PARALLEL!"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        
        if not os.path.exists(session_temp_path):
            print(f"⚠️  Restoring session {session_id}...")
            
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                await run_async(
                    session_service.update_session_status,
                    session_id,
                    "processing"
                )
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        # 🚀 PARALLEL PROCESSING!
        tasks = []
        page_numbers = []
        
        for page_request in request.pages:
            text_data = [item.dict() for item in page_request.text_data]
            
            task = run_async(
                pdf_processor.write_text_on_page,
                session_id,
                page_request.page_number,
                text_data
            )
            
            tasks.append(task)
            page_numbers.append(page_request.page_number)
        
        print(f"🚀 Processing {len(tasks)} pages in PARALLEL...")
        await asyncio.gather(*tasks)
        print(f"✅ All {len(tasks)} pages completed!")
        
        total_items_added = sum(
            len(page_request.text_data) 
            for page_request in request.pages
        )
        
        return BatchFillTextResponse(
            session_id=session_id,
            total_pages_filled=len(page_numbers),
            total_items_added=total_items_added,
            pages_processed=page_numbers
        )
    
    except Exception as e:
        error_message = str(e)
        if "No such file or directory" in error_message:
            raise HTTPException(status_code=400, detail="File or page doesn't exist")
        else:
            raise HTTPException(status_code=500, detail=f"Batch fill failed: {error_message}")


@router.post("/fill-text-batch-encrypted", response_model=BatchFillTextResponse)
async def fill_text_batch_encrypted(
    request: EncryptedBatchFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    """Fill text on MULTIPLE pages (ENCRYPTED) - IN PARALLEL!"""
    try:
        decrypted = await run_async(decrypt_data, request.encrypted_data)
        
        session_id = request.session_id
        pages_data = decrypted["pages"]
        
        session = session_service.get_session(session_id)
        if not session or session["user_id"] != current_user['id']:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                await run_async(
                    session_service.update_session_status,
                    session_id,
                    "processing"
                )
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        # 🚀 PARALLEL PROCESSING!
        tasks = []
        page_numbers = []
        
        for page_data in pages_data:
            page_number = page_data["page_number"]
            text_data = page_data["text_data"]
            
            task = run_async(
                pdf_processor.write_text_on_page,
                session_id,
                page_number,
                text_data
            )
            
            tasks.append(task)
            page_numbers.append(page_number)
        
        print(f"🚀 Processing {len(tasks)} encrypted pages in PARALLEL...")
        await asyncio.gather(*tasks)
        print(f"✅ All {len(tasks)} pages completed!")
        
        total_items_added = sum(
            len(page_data["text_data"]) 
            for page_data in pages_data
        )
        
        return BatchFillTextResponse(
            session_id=session_id,
            total_pages_filled=len(page_numbers),
            total_items_added=total_items_added,
            pages_processed=page_numbers
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch fill failed: {str(e)}")


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@router.get("/my-sessions", response_model=UserSessionsResponse)
async def get_my_sessions(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get PDF sessions for current user (paginated).

    - limit: page size
    - offset: how many records to skip from the start
    """
    user_id = current_user["id"]

    # 1) Get total count for this user
    total_sessions = await run_async(
        session_service.count_user_sessions,
        user_id
    )

    # 2) Get only the slice we want for this page
    sessions = await run_async(
        session_service.get_user_sessions,
        user_id,
        limit,
        offset,
    )

    session_infos = [
        SessionInfo(
            session_id=s["session_id"],
            filename=s["filename"],
            num_pages=s["num_pages"],
            status=s["status"],
            storage_path=s.get("storage_path"),
            created_at=s["created_at"],
            updated_at=s["updated_at"],
        )
        for s in sessions
    ]

    return UserSessionsResponse(
        user_id=user_id,
        total_sessions=total_sessions,  # total in DB, not just this page
        limit=limit,
        offset=offset,
        sessions=session_infos,
    )


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a PDF session"""
    if not session_service.verify_session_ownership(session_id, current_user['id']):
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    await run_async(pdf_processor.cleanup_folders, session_id)
    await run_async(session_service.delete_session, session_id)
    
    return {
        "message": "Session deleted successfully",
        "session_id": session_id
    }


@router.get("/history", response_model=UserSessionsResponse)
async def get_pdf_history(
    limit: int = 50,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get user's complete PDF history"""
    if limit > 100:
        limit = 100
    
    def _get_history():
        query = session_service.supabase.table("pdf_sessions").select("*").eq(
            "user_id", current_user['id']
        )
        
        if status:
            query = query.eq("status", status)
        
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data if result.data else []
    
    sessions = await run_async(_get_history)
    
    session_infos = [
        SessionInfo(
            session_id=s["session_id"],
            filename=s["filename"],
            num_pages=s["num_pages"],
            status=s["status"],
            storage_path=s.get("storage_path"),
            created_at=s["created_at"],
            updated_at=s["updated_at"]
        )
        for s in sessions
    ]
    
    return UserSessionsResponse(
        user_id=current_user['id'],
        total_sessions=len(session_infos),
        sessions=session_infos
    )


@router.get("/download/{session_id}")
async def download_pdf(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download a previously filled PDF"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    if not session.get("storage_path"):
        raise HTTPException(
            status_code=404, 
            detail=f"Completed PDF not found in storage (Current status: {session['status']})."
        )
    
    try:
        def _create_signed_url():
            signed_url_response = pdf_processor.supabase.storage.from_(
                pdf_processor.STORAGE_BUCKET
            ).create_signed_url(session["storage_path"], 3600)
            return signed_url_response['signedURL']
        
        def _update_download_count():
            session_service.supabase.table("pdf_sessions").update({
                "download_count": session.get("download_count", 0) + 1,
                "last_downloaded_at": datetime.now().isoformat()
            }).eq("session_id", session_id).execute()

        signed_url, _ = await asyncio.gather(
            run_async(_create_signed_url),
            run_async(_update_download_count)
        )
        
        return {
            "download_url": signed_url,
            "filename": session["filename"],
            "expires_in_seconds": 3600,
            "message": "Download link expires in 1 hour"
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download link: {str(e)}"
        )


@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    """Get user's PDF filling statistics"""
    user_id = current_user['id']
    
    all_sessions = await run_async(
        session_service.get_user_sessions,
        user_id,
        limit=1000
    )
    
    total_pdfs = len(all_sessions)
    completed = len([s for s in all_sessions if s["status"] == "completed"])
    processing = len([s for s in all_sessions if s["status"] == "processing"])
    failed = len([s for s in all_sessions if s["status"] == "failed"])
    
    from datetime import datetime, timezone
    
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    this_month = 0
    for s in all_sessions:
        try:
            created_at_str = s["created_at"]
            
            if isinstance(created_at_str, str):
                if created_at_str.endswith('Z'):
                    created_at_str = created_at_str[:-1] + '+00:00'
                
                created_at = datetime.fromisoformat(created_at_str)
            else:
                created_at = created_at_str
            
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            if created_at >= month_start:
                this_month += 1
        
        except Exception as e:
            continue
    
    return {
        "user_id": user_id,
        "total_pdfs_filled": total_pdfs,
        "completed": completed,
        "processing": processing,
        "failed": failed,
        "this_month": this_month,
        "success_rate": round((completed / total_pdfs * 100) if total_pdfs > 0 else 0, 2)
    }


# ============================================================================
# PREVIEW ENDPOINTS
# ============================================================================

@router.get("/preview/{session_id}/page/{page_number}")
async def preview_page(
    session_id: str,
    page_number: int,
    current_user: dict = Depends(get_current_user)
):
    """Preview a specific page"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
        
        filled_path = f"{pdf_processor.OUTPUT_FOLDER}/{session_id}/page_{page_number}_filled.png"
        original_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}/page_{page_number}.png"
        
        if os.path.exists(filled_path):
            return FileResponse(filled_path, media_type="image/png")
        elif os.path.exists(original_path):
            return FileResponse(original_path, media_type="image/png")
        else:
            raise HTTPException(status_code=404, detail="Page not found")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.get("/preview/{session_id}/all-pages")
async def preview_all_pages(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get URLs to preview all pages"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    num_pages = session["num_pages"]
    
    return {
        "session_id": session_id,
        "total_pages": num_pages,
        "preview_urls": [
            f"/api/pdf/preview/{session_id}/page/{i}" 
            for i in range(1, num_pages + 1)
        ]
    }


@router.get("/gridded/{session_id}/page/{page_number}")
async def get_gridded_page(
    session_id: str,
    page_number: int,
    current_user: dict = Depends(get_current_user)
):
    """Get page with grid overlay"""
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                await run_async(
                    pdf_processor.restore_session_from_storage,
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
        
        gridded_path = await run_async(
            pdf_processor.apply_grid_to_page,
            session_id,
            page_number
        )
        
        return FileResponse(gridded_path, media_type="image/png")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid generation failed: {str(e)}")


# ============================================================================
# FONT MANAGEMENT
# ============================================================================

@router.post("/upload-font")
async def upload_custom_font(
    font_name: str = Form(...),
    font_file: UploadFile = File(...)
):
    """Upload a custom font (not tied to a session)"""
    if not font_file.filename.lower().endswith('.ttf'):
        raise HTTPException(status_code=400, detail="Only TTF fonts allowed")

    try:
        fonts_folder = "fonts"
        os.makedirs(fonts_folder, exist_ok=True)

        font_path = f"{fonts_folder}/{font_name}.ttf"

        font_content = await font_file.read()
        await run_async(lambda: open(font_path, "wb").write(font_content))

        return {
            "message": f"Font '{font_name}' uploaded successfully",
            "font_name": font_name,
            "usage": f"Set 'font': '{font_name}' in text_data"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Font upload failed: {str(e)}")



@router.get("/available-fonts")
async def get_available_fonts():
    """Get list of built-in fonts"""
    from services.pdf_processor import AVAILABLE_FONTS
    
    return {
        "fonts": list(AVAILABLE_FONTS.keys()),
        "total": len(AVAILABLE_FONTS),
        "default": "arial" if "arial" in AVAILABLE_FONTS else list(AVAILABLE_FONTS.keys())[0] if AVAILABLE_FONTS else None,
        "custom_fonts_support": True,
        "upload_endpoint": "POST /api/pdf/upload-font"
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def pdf_health():
    """Health check for PDF service"""
    return {
        "service": "PDF Processing",
        "status": "operational",
        "async_mode": "TRUE_ASYNC",
        "thread_workers": 30,
        "parallel_batch_processing": True,
        "session_storage": "supabase_database",
        "file_storage": "supabase_storage",
        "grid_size": pdf_processor.GRID_SIZE,
        "dpi": pdf_processor.DPI
    }


# ============================================================================
# CLEANUP ON SHUTDOWN
# ============================================================================

def cleanup_executor():
    """Cleanup executor on shutdown"""
    print("🛑 Shutting down async executor...")
    executor.shutdown(wait=True)
    print("✅ Executor shut down cleanly")


import atexit
atexit.register(cleanup_executor)