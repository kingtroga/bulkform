"""
pdf_routes.py — UPDATED (minimal necessary changes)

Goals:
- Stop 502/timeouts on /upload by offloading heavy PDF->images + grid extraction to Celery
- Make ALL routes resilient after Celery cleanup by restoring session files from Supabase storage
- Support polling: /session/{session_id} + /grid/{session_id} (and optional encrypted grid)
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from models.pdf_models import (
    GridResponse, FillTextRequest, FillTextResponse,
    CoordConversionRequest, AddImageResponse, GeneratePDFResponse,
    SessionInfo, UserSessionsResponse, EncryptedGridResponse,
    EncryptedFillTextRequest, BatchFillTextRequest, EncryptedBatchFillTextRequest,
    BatchFillTextResponse
)

from utils.encryption import encrypt_grid_data, decrypt_data
from services.pdf_processor import PDFProcessor
from services.session_service import SessionService
from services.auth import get_current_user

import os
import uuid
import asyncio
import tempfile
from typing import Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# ✅ Celery task (YOU MUST implement/adjust this signature in celery_tasks.py)
# Recommended signature:
# process_upload_session_task(session_id: str, user_id: str, original_storage_path: str)
from celery_tasks import process_upload_session_task

router = APIRouter(prefix="/api/pdf", tags=["PDF Processing"])

pdf_processor = PDFProcessor()
session_service = SessionService()

# Thread pool for small blocking ops (DB calls, file ops, storage calls)
executor = ThreadPoolExecutor(max_workers=30, thread_name_prefix="bulkform")


async def run_async(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, partial(func, *args, **kwargs))


# ------------------------------------------------------------------------------
# DB helper (because SessionService.update_session_status only updates status/storage_path)
# ------------------------------------------------------------------------------
def _update_session_fields_sync(session_id: str, fields: dict):
    fields = dict(fields or {})
    fields["updated_at"] = datetime.now().isoformat()
    res = (
        session_service.supabase
        .table("pdf_sessions")
        .update(fields)
        .eq("session_id", session_id)
        .execute()
    )
    return res.data[0] if res.data else None


async def update_session_fields(session_id: str, fields: dict):
    return await run_async(_update_session_fields_sync, session_id, fields)


# ------------------------------------------------------------------------------
# Restore helper — fixes the “only restore when completed” bug
# ------------------------------------------------------------------------------
async def ensure_session_local(session: dict, session_id: str, user_id: str):
    """
    Guarantees TEMP_FOLDER/session_id exists locally with:
    - original.pdf
    - page_1.png .. page_n.png (regenerated during restore)

    This makes preview/fill/add-image work even after Celery cleaned local files.
    """
    session_temp_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}"
    if os.path.exists(session_temp_path):
        return

    # Use stored original path if present, else fallback
    original_storage_path = session.get("original_storage_path") or f"{user_id}/{session_id}/original.pdf"

    await run_async(
        pdf_processor.restore_session_from_storage,
        session_id,
        user_id,
        original_storage_path
    )


# ==============================================================================
# UPLOAD (Celery)
# ==============================================================================

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Uploads original PDF (fast), stores it in Supabase Storage,
    creates DB session, then queues Celery for heavy processing (pdf->images + grid).
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    session_id = str(uuid.uuid4())
    user_id = current_user["id"]

    # Read upload
    contents = await file.read()
    file_size = len(contents)

    # Save locally (temp) just to upload to storage
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        local_pdf_path = tmp.name

    try:
        # ✅ Upload original to storage (fast IO). Celery will download/convert later.
        storage_path = await run_async(
            pdf_processor.upload_original_pdf,
            local_pdf_path,
            user_id,
            session_id
        )

        # Create session row (SessionService sets status='processing' by default)
        session_service.create_session(
            session_id=session_id,
            user_id=user_id,
            filename=file.filename,
            num_pages=0
        )

        # ✅ Patch fields for async flow
        await update_session_fields(session_id, {
            "status": "queued",
            "original_storage_path": storage_path,
            "original_filename": file.filename,
            "file_size_bytes": file_size,
            "progress": 0,
            "error_message": None,
            "dpi": None,
            "grid_size": None,
            "pages": None,
        })

        # ✅ Queue Celery (do NOT pass local path; workers may be on another machine)
        process_upload_session_task.apply_async(
            args=[session_id, user_id, storage_path],
            queue="pdf_processing"
        )

        return {
            "session_id": session_id,
            "status": "queued",
            "message": "Upload received. Processing started.",
            "original_storage_path": storage_path
        }

    except Exception as e:
        # best-effort session creation might have happened; mark failed if exists
        try:
            await update_session_fields(session_id, {
                "status": "failed",
                "error_message": str(e),
                "progress": 0
            })
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    finally:
        try:
            os.unlink(local_pdf_path)
        except Exception:
            pass


@router.post("/upload-encrypted")
async def upload_pdf_encrypted(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Minimal change:
    - behaves like /upload (Celery)
    - client should poll /session then call /grid-encrypted/{session_id}
    """
    return await upload_pdf(file=file, current_user=current_user)


# ==============================================================================
# POLLING / GRID
# ==============================================================================

@router.get("/session/{session_id}")
async def get_session_status(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    return {
        "session_id": session_id,
        "status": session.get("status"),
        "progress": session.get("progress", 0),
        "num_pages": session.get("num_pages", 0),
        "dpi": session.get("dpi"),
        "grid_size": session.get("grid_size"),
        "pages": session.get("pages"),
        "error_message": session.get("error_message"),
        "original_storage_path": session.get("original_storage_path"),
        "storage_path": session.get("storage_path"),
        "filename": session.get("filename"),
    }


@router.get("/grid/{session_id}", response_model=GridResponse)
async def get_grid(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if session.get("status") != "ready":
        raise HTTPException(status_code=409, detail=f"Session not ready (status={session.get('status')})")

    pages = session.get("pages") or []
    dpi = session.get("dpi") or pdf_processor.DPI

    return GridResponse(
        total_pages=session.get("num_pages", 0),
        pages=pages,
        dpi=dpi,
        session_id=session_id
    )


@router.get("/grid-encrypted/{session_id}", response_model=EncryptedGridResponse)
async def get_grid_encrypted(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if session.get("status") != "ready":
        raise HTTPException(status_code=409, detail=f"Session not ready (status={session.get('status')})")

    payload = {
        "pages": session.get("pages") or [],
        "dpi": session.get("dpi") or pdf_processor.DPI,
        "grid_size": session.get("grid_size") or getattr(pdf_processor, "GRID_SIZE", 150),
    }

    encrypted = await run_async(encrypt_grid_data, payload)

    return EncryptedGridResponse(
        encrypted_data=encrypted,
        total_pages=session.get("num_pages", 0),
        session_id=session_id,
        dpi=payload["dpi"]
    )


# ==============================================================================
# FILL TEXT
# ==============================================================================

@router.post("/fill-text", response_model=FillTextResponse)
async def fill_text(
    session_id: str,
    request: FillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        await ensure_session_local(session, session_id, current_user["id"])

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
        msg = str(e)
        if "No such file or directory" in msg:
            raise HTTPException(status_code=400, detail="File or page doesn't exist. Check session and page number.")
        raise HTTPException(status_code=500, detail=f"Fill text failed: {msg}")


@router.post("/fill-text-encrypted", response_model=FillTextResponse)
async def fill_text_encrypted(
    request: EncryptedFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        decrypted = await run_async(decrypt_data, request.encrypted_data)

        session_id = request.session_id
        page_number = decrypted["page_number"]
        text_data = decrypted["text_data"]

        session = session_service.get_session(session_id)
        if not session or session["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Unauthorized")

        await ensure_session_local(session, session_id, current_user["id"])

        await run_async(
            pdf_processor.write_text_on_page,
            session_id,
            page_number,
            text_data
        )

        return FillTextResponse(page_number=page_number, items_added=len(text_data))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid encrypted data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fill text failed: {str(e)}")


# ==============================================================================
# IMAGE OPS
# ==============================================================================

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
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if image_file.content_type not in ["image/png", "image/jpeg", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Only PNG and JPG allowed")

    try:
        await ensure_session_local(session, session_id, current_user["id"])

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

        return AddImageResponse(page_number=page_number, images_added=1)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Add {subfolder} failed: {str(e)}")


# ==============================================================================
# GENERATE FINAL PDF
# ==============================================================================

@router.post("/generate", response_model=GeneratePDFResponse)
async def generate_pdf(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        user_id = current_user["id"]
        num_pages = session.get("num_pages") or 0
        if num_pages <= 0:
            raise HTTPException(status_code=409, detail="Session not ready (num_pages not set yet).")

        # Ensure local files exist (restore if Celery cleaned up)
        await ensure_session_local(session, session_id, user_id)

        # Create PDF + upload
        result = await run_async(
            pdf_processor.create_pdf_with_upload,
            session_id,
            user_id,
            num_pages
        )

        await run_async(
            session_service.update_session_status,
            session_id,
            "completed",
            result["storage_path"]
        )

        # Cleanup local folders (safe after upload)
        await run_async(pdf_processor.cleanup_folders, session_id)

        return GeneratePDFResponse(
            pdf_url=result["storage_url"],
            storage_path=result["storage_path"],
            total_pages=num_pages
        )

    except HTTPException:
        raise
    except Exception as e:
        try:
            await update_session_fields(session_id, {"status": "failed", "error_message": str(e)})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ==============================================================================
# GET ORIGINAL PDF FOR TEMPLATE CREATION
# ==============================================================================

@router.get("/get-original/{session_id}")
async def get_original_pdf(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    user_id = current_user["id"]
    local_pdf_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}/original.pdf"
    original_storage_path = session.get("original_storage_path") or f"{user_id}/{session_id}/original.pdf"

    try:
        if os.path.exists(local_pdf_path):
            return FileResponse(local_pdf_path, media_type="application/pdf", filename=session["filename"])

        # download original
        await run_async(
            pdf_processor.download_file_from_storage,
            original_storage_path,
            local_pdf_path
        )

        return FileResponse(local_pdf_path, media_type="application/pdf", filename=session["filename"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve original PDF: {str(e)}")


# ==============================================================================
# BATCH FILL (unchanged logic but uses ensure_session_local)
# ==============================================================================

@router.post("/fill-text-batch", response_model=BatchFillTextResponse)
async def fill_text_batch(
    session_id: str,
    request: BatchFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        await ensure_session_local(session, session_id, current_user["id"])

        tasks = []
        page_numbers = []

        for page_request in request.pages:
            text_data = [item.dict() for item in page_request.text_data]
            tasks.append(run_async(pdf_processor.write_text_on_page, session_id, page_request.page_number, text_data))
            page_numbers.append(page_request.page_number)

        await asyncio.gather(*tasks)

        total_items_added = sum(len(p.text_data) for p in request.pages)

        return BatchFillTextResponse(
            session_id=session_id,
            total_pages_filled=len(page_numbers),
            total_items_added=total_items_added,
            pages_processed=page_numbers
        )

    except Exception as e:
        msg = str(e)
        if "No such file or directory" in msg:
            raise HTTPException(status_code=400, detail="File or page doesn't exist")
        raise HTTPException(status_code=500, detail=f"Batch fill failed: {msg}")


@router.post("/fill-text-batch-encrypted", response_model=BatchFillTextResponse)
async def fill_text_batch_encrypted(
    request: EncryptedBatchFillTextRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        decrypted = await run_async(decrypt_data, request.encrypted_data)
        session_id = request.session_id
        pages_data = decrypted["pages"]

        session = session_service.get_session(session_id)
        if not session or session["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Unauthorized")

        await ensure_session_local(session, session_id, current_user["id"])

        tasks = []
        page_numbers = []

        for page_data in pages_data:
            page_number = page_data["page_number"]
            text_data = page_data["text_data"]
            tasks.append(run_async(pdf_processor.write_text_on_page, session_id, page_number, text_data))
            page_numbers.append(page_number)

        await asyncio.gather(*tasks)

        total_items_added = sum(len(p["text_data"]) for p in pages_data)

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


# ==============================================================================
# PREVIEW
# ==============================================================================

@router.get("/preview/{session_id}/page/{page_number}")
async def preview_page(session_id: str, page_number: int, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        await ensure_session_local(session, session_id, current_user["id"])

        filled_path = f"{pdf_processor.OUTPUT_FOLDER}/{session_id}/page_{page_number}_filled.png"
        original_path = f"{pdf_processor.TEMP_FOLDER}/{session_id}/page_{page_number}.png"

        if os.path.exists(filled_path):
            return FileResponse(filled_path, media_type="image/png")
        if os.path.exists(original_path):
            return FileResponse(original_path, media_type="image/png")

        raise HTTPException(status_code=404, detail="Page not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.get("/preview/{session_id}/all-pages")
async def preview_all_pages(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    num_pages = session.get("num_pages") or 0
    return {
        "session_id": session_id,
        "total_pages": num_pages,
        "preview_urls": [f"/api/pdf/preview/{session_id}/page/{i}" for i in range(1, num_pages + 1)]
    }


@router.get("/gridded/{session_id}/page/{page_number}")
async def get_gridded_page(session_id: str, page_number: int, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        await ensure_session_local(session, session_id, current_user["id"])

        gridded_path = await run_async(pdf_processor.apply_grid_to_page, session_id, page_number)
        return FileResponse(gridded_path, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid generation failed: {str(e)}")


# ==============================================================================
# SESSION LIST / DELETE / HISTORY / DOWNLOAD / STATS (unchanged)
# ==============================================================================

@router.get("/my-sessions", response_model=UserSessionsResponse)
async def get_my_sessions(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id = current_user["id"]

    total_sessions = await run_async(session_service.count_user_sessions, user_id)
    sessions = await run_async(session_service.get_user_sessions, user_id, limit, offset)

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
        total_sessions=total_sessions,
        limit=limit,
        offset=offset,
        sessions=session_infos,
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    if not session_service.verify_session_ownership(session_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="Unauthorized")

    await run_async(pdf_processor.cleanup_folders, session_id)
    await run_async(session_service.delete_session, session_id)

    return {"message": "Session deleted successfully", "session_id": session_id}


@router.get("/history", response_model=UserSessionsResponse)
async def get_pdf_history(
    limit: int = 50,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if limit > 100:
        limit = 100

    def _get_history():
        query = session_service.supabase.table("pdf_sessions").select("*").eq("user_id", current_user["id"])
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
            updated_at=s["updated_at"],
        )
        for s in sessions
    ]

    return UserSessionsResponse(
        user_id=current_user["id"],
        total_sessions=len(session_infos),
        sessions=session_infos
    )


@router.get("/download/{session_id}")
async def download_pdf(session_id: str, current_user: dict = Depends(get_current_user)):
    session = session_service.get_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not session.get("storage_path"):
        raise HTTPException(status_code=404, detail=f"Completed PDF not found (status={session.get('status')}).")

    try:
        def _create_signed_url():
            r = pdf_processor.supabase.storage.from_(pdf_processor.STORAGE_BUCKET).create_signed_url(
                session["storage_path"], 3600
            )
            return r["signedURL"]

        def _update_download_count():
            session_service.supabase.table("pdf_sessions").update({
                "download_count": (session.get("download_count") or 0) + 1,
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
        raise HTTPException(status_code=500, detail=f"Failed to generate download link: {str(e)}")


@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    all_sessions = await run_async(session_service.get_user_sessions, user_id, 1000, 0)

    total_pdfs = len(all_sessions)
    completed = len([s for s in all_sessions if s["status"] == "completed"])
    processing = len([s for s in all_sessions if s["status"] in ("processing", "queued", "ready")])
    failed = len([s for s in all_sessions if s["status"] == "failed"])

    from datetime import timezone
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    this_month = 0
    for s in all_sessions:
        try:
            created_at_str = s["created_at"]
            if isinstance(created_at_str, str) and created_at_str.endswith("Z"):
                created_at_str = created_at_str[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at_str) if isinstance(created_at_str, str) else created_at_str
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at >= month_start:
                this_month += 1
        except Exception:
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


# ==============================================================================
# MISC
# ==============================================================================

@router.get("/health")
async def pdf_health():
    return {
        "service": "PDF Processing",
        "status": "operational",
        "async_mode": "celery_upload + restore_on_demand",
        "thread_workers": 30,
        "session_storage": "supabase_database",
        "file_storage": "supabase_storage",
        "grid_size": getattr(pdf_processor, "GRID_SIZE", 150),
        "dpi": getattr(pdf_processor, "DPI", None),
    }


@router.post("/convert-coords")
async def convert_coordinates(data: CoordConversionRequest, current_user: dict = Depends(get_current_user)):
    GRID_SIZE = 150
    grid_x = round((data.pixel_x / data.page_width) * GRID_SIZE)
    grid_y = round((data.pixel_y / data.page_height) * GRID_SIZE)
    return {"gridX": grid_x, "gridY": grid_y}


def cleanup_executor():
    try:
        executor.shutdown(wait=True)
    except Exception:
        pass


import atexit
atexit.register(cleanup_executor)
