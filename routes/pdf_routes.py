"""
PDF Routes - Complete Form Filling API
🔒 Protected with JWT authentication
💾 Database-backed sessions (survives restarts!)
☁️  Supabase Storage for PDFs
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import FileResponse
from models.pdf_models import (
    GridResponse, FillTextRequest, FillTextResponse,
    AddImageRequest, AddImageResponse, GeneratePDFResponse,
    SessionInfo, UserSessionsResponse
)
from services.pdf_processor import PDFProcessor
from services.session_service import SessionService
from services.auth import get_current_user
import os
import shutil
import uuid
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/pdf", tags=["PDF Processing"])

# Initialize services
pdf_processor = PDFProcessor()
session_service = SessionService()


@router.post("/upload", response_model=GridResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload PDF and get grid coordinates for all pages
    
    🔒 PROTECTED - Requires JWT token
    💾 Session saved to database (survives server restarts!)
    
    Steps:
    1. Verify user authentication
    2. Upload PDF file
    3. Convert pages to images at 300 DPI
    4. Calculate 150x150 grid dimensions
    5. Save session to database
    6. Return coordinates + session_id
    
    Returns:
        GridResponse with session_id for subsequent operations
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    user_id = current_user['id']
    
    try:
        # Save uploaded PDF temporarily
        upload_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        os.makedirs(upload_path, exist_ok=True)
        pdf_path = f"{upload_path}/original.pdf"
        
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 🔥 ALSO upload to Supabase Storage (permanent backup)
        storage_path = pdf_processor.upload_original_pdf(pdf_path, user_id, session_id)
        
        # Convert to images and get dimensions
        num_pages = pdf_processor.pdf_to_images(pdf_path, session_id)
        page_dimensions = pdf_processor.get_all_page_dimensions(session_id, num_pages)
        
        # 🔥 Store session in DATABASE (not memory!)
        session_service.create_session(
            session_id=session_id,
            user_id=user_id,
            filename=file.filename,
            num_pages=num_pages
        )
        
        return GridResponse(
            total_pages=num_pages,
            pages=page_dimensions,
            dpi=pdf_processor.DPI,
            session_id=session_id
        )
    
    except Exception as e:
        # Cleanup on error
        pdf_processor.cleanup_folders(session_id)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/fill-text", response_model=FillTextResponse)
async def fill_text(
    session_id: str,
    request: FillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Fill text on a specific PDF page
    
    🔒 PROTECTED - Can only modify your own PDFs
    
    Args:
        session_id: Session ID from upload
        request: Text data with grid coordinates
        
    Returns:
        FillTextResponse with number of items added
    """
     # Verify ownership
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        # 🔥 CHECK IF SESSION NEEDS RESTORATION
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        
        if not os.path.exists(session_temp_path):
            # Session was cleaned up - restore from storage
            print(f"⚠️  Session {session_id} not in temp folder. Restoring from storage...")
            
            if session["status"] == "completed":
                # Restore from Supabase Storage
                pdf_processor.restore_session_from_storage(
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                
                # Update status back to processing
                session_service.update_session_status(session_id, "processing")
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found and cannot be restored (no original PDF)"
                )
        
        # Now proceed with filling text
        text_data = [item.dict() for item in request.text_data]
        pdf_processor.write_text_on_page(
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
                detail="It looks like the file or page you’re trying to modify doesn’t exist. "
                    "Please make sure the PDF session and page number are valid."
            )
        else:
            raise HTTPException(status_code=500, detail=f"Fill text failed: {error_message}")


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
    """Add signature - Auto-restores completed sessions"""
    
    # Verify ownership
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Validate file type
    if not signature_file.content_type in ["image/png", "image/jpeg", "image/jpg"]:
        raise HTTPException(
            status_code=400,
            detail="Only PNG and JPG images allowed"
        )
    
    try:
        # 🔥 CHECK IF SESSION NEEDS RESTORATION
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        
        if not os.path.exists(session_temp_path):
            print(f"⚠️  Session {session_id} not in temp folder. Restoring from storage...")
            
            if session["status"] == "completed":
                pdf_processor.restore_session_from_storage(
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
                session_service.update_session_status(session_id, "processing")
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found and cannot be restored"
                )
        
        # Save signature
        temp_signatures_folder = f"{pdf_processor.TEMP_FOLDER}/{session_id}/signatures"
        os.makedirs(temp_signatures_folder, exist_ok=True)
        
        signature_path = f"{temp_signatures_folder}/{signature_file.filename}"
        
        with open(signature_path, "wb") as buffer:
            shutil.copyfileobj(signature_file.file, buffer)
        
        # Prepare image data
        image_data = [{'x': x, 'y': y, 'image_path': signature_path}]
        
        if width and height:
            image_data[0]['width'] = width
            image_data[0]['height'] = height
        
        # Add signature
        pdf_processor.add_images_to_page(
            session_id,
            page_number,
            image_data
        )
        
        return AddImageResponse(
            page_number=page_number,
            images_added=1
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add signature failed: {str(e)}")


@router.post("/generate", response_model=GeneratePDFResponse)
async def generate_pdf(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate final filled PDF and upload to Supabase Storage
    
    🔒 PROTECTED - Can only generate your own PDFs
    ☁️  Uploads to Supabase Storage
    💾 Updates session status in database
    
    Args:
        session_id: Session ID from upload
        
    Returns:
        GeneratePDFResponse with download URL
    """
    # 🔥 Get session from DATABASE
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(
            status_code=403, 
            detail="Session not found or unauthorized"
        )
    
    try:
        user_id = current_user['id']
        num_pages = session["num_pages"]
        
        # Create PDF and upload to Supabase Storage
        result = pdf_processor.create_pdf_with_upload(
            session_id=session_id,
            user_id=user_id,
            num_pages=num_pages
        )
        
        # 🔥 Update session status in DATABASE
        session_service.update_session_status(
            session_id=session_id,
            status="completed",
            storage_path=result["storage_path"]
        )
        
        # Cleanup local files
        pdf_processor.cleanup_folders(session_id)
        
        return GeneratePDFResponse(
            pdf_url=result["storage_url"],
            storage_path=result["storage_path"],
            total_pages=num_pages
        )
    
    except Exception as e:
        # Mark as failed in database
        session_service.update_session_status(session_id, "failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get("/my-sessions", response_model=UserSessionsResponse)
async def get_my_sessions(current_user: dict = Depends(get_current_user)):
    """
    Get all PDF sessions for current user
    
    🔒 PROTECTED
    💾 Retrieves from DATABASE
    
    Returns:
        List of all user's PDF sessions (newest first)
    """
    sessions = session_service.get_user_sessions(current_user['id'])
    
    # Convert to SessionInfo models
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


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a PDF session
    
    🔒 PROTECTED - Can only delete your own sessions
    🗑️  Removes from database and cleans up files
    
    Args:
        session_id: Session to delete
        
    Returns:
        Success message
    """
    # Verify ownership
    if not session_service.verify_session_ownership(session_id, current_user['id']):
        raise HTTPException(
            status_code=403, 
            detail="Session not found or unauthorized"
        )
    
    # Cleanup local files
    pdf_processor.cleanup_folders(session_id)
    
    # Remove from database
    session_service.delete_session(session_id)
    
    return {
        "message": "Session deleted successfully",
        "session_id": session_id
    }


@router.get("/health")
async def pdf_health():
    """
    Health check for PDF service
    ✅ PUBLIC - No auth required
    """
    return {
        "service": "PDF Processing",
        "status": "operational",
        "session_storage": "supabase_database",
        "file_storage": "supabase_storage",
        "grid_size": pdf_processor.GRID_SIZE,
        "dpi": pdf_processor.DPI
    }

@router.get("/history", response_model=UserSessionsResponse)
async def get_pdf_history(
    limit: int = 50,
    status: Optional[str] = None,  # Filter by status: completed, processing, failed
    current_user: dict = Depends(get_current_user)
):
    """
    Get user's complete PDF history
    
    🔒 PROTECTED - Shows only your PDFs
    📊 Returns all PDFs you've ever filled
    
    Query params:
        - limit: Number of results (default 50, max 100)
        - status: Filter by status (completed, processing, failed)
    
    Use case:
        "Show me all the forms I filled this month"
    """
    if limit > 100:
        limit = 100
    
    # Get sessions from database
    query = session_service.supabase.table("pdf_sessions").select("*").eq(
        "user_id", current_user['id']
    )
    
    # Filter by status if provided
    if status:
        query = query.eq("status", status)
    
    # Order by newest first, limit results
    result = query.order("created_at", desc=True).limit(limit).execute()
    
    sessions = result.data if result.data else []
    
    # Convert to SessionInfo models
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
    """
    Download a previously filled PDF
    
    🔒 PROTECTED - Can only download your own PDFs
    🔐 Generates fresh signed URL (expires in 1 hour)
    📊 Tracks download count
    
    Returns:
        Fresh signed URL to download the PDF
    """
    # Verify ownership
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(
            status_code=403,
            detail="Session not found or unauthorized"
        )
    
    # Check if PDF was completed
    if session["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"PDF is not ready yet (status: {session['status']})"
        )
    
    if not session.get("storage_path"):
        raise HTTPException(
            status_code=404,
            detail="PDF file not found in storage"
        )
    
    try:
        # Generate fresh signed URL (1 hour expiry)
        signed_url_response = pdf_processor.supabase.storage.from_(
            pdf_processor.STORAGE_BUCKET
        ).create_signed_url(
            session["storage_path"],
            3600  # 1 hour
        )
        
        # Update download count
        session_service.supabase.table("pdf_sessions").update({
            "download_count": session.get("download_count", 0) + 1,
            "last_downloaded_at": datetime.now().isoformat()
        }).eq("session_id", session_id).execute()
        
        return {
            "download_url": signed_url_response['signedURL'],
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
    all_sessions = session_service.get_user_sessions(user_id, limit=1000)
    
    # Calculate stats
    total_pdfs = len(all_sessions)
    completed = len([s for s in all_sessions if s["status"] == "completed"])
    processing = len([s for s in all_sessions if s["status"] == "processing"])
    failed = len([s for s in all_sessions if s["status"] == "failed"])
    
    # Fix timezone comparison
    from datetime import datetime, timezone
    
    # Make month_start timezone-aware
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    this_month = 0
    for s in all_sessions:
        try:
            created_at_str = s["created_at"]
            
            # Handle string datetime
            if isinstance(created_at_str, str):
                # Remove 'Z' and add '+00:00' for ISO format
                if created_at_str.endswith('Z'):
                    created_at_str = created_at_str[:-1] + '+00:00'
                
                created_at = datetime.fromisoformat(created_at_str)
            else:
                created_at = created_at_str
            
            # Ensure timezone-aware
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            if created_at >= month_start:
                this_month += 1
        
        except Exception as e:
            print(f"⚠️  Error parsing date for session: {e}")
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

@router.get("/preview/{session_id}/page/{page_number}")
async def preview_page(
    session_id: str,
    page_number: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview a specific page (with or without edits)
    
    🔒 PROTECTED
    📸 Returns the page image (filled or original)
    
    Use case:
        See what your filled form looks like before generating final PDF
    """
    # Verify ownership
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        # Check if session needs restoration
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                pdf_processor.restore_session_from_storage(
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
        
        # Try filled page first, fall back to original
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
    """
    Get URLs to preview all pages
    
    🔒 PROTECTED
    📸 Returns list of preview URLs for each page
    """
    # Verify ownership
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
    """
    Get page with grid overlay
    
    🔒 PROTECTED
    📏 Shows 150x150 grid for coordinate reference
    
    Use case:
        API users can see the grid to determine coordinates
    """
    # Verify ownership
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user['id']:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    try:
        # Restore if needed
        session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
        if not os.path.exists(session_temp_path):
            if session["status"] == "completed":
                pdf_processor.restore_session_from_storage(
                    session_id,
                    current_user['id'],
                    session["storage_path"]
                )
        
        # Generate gridded image
        gridded_path = pdf_processor.apply_grid_to_page(session_id, page_number)
        
        return FileResponse(gridded_path, media_type="image/png")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid generation failed: {str(e)}")