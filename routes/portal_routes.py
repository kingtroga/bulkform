"""
Portal Routes
Public intake portal endpoints, form submission handling,
and spreadsheet data feed exports (CSV / Excel).
"""

import os
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import Response

from services.auth import get_current_user
from limiter import limiter
from services.portal_service import get_portal_service
from models.portal_models import (
    PortalCreateRequest,
    PortalUpdateRequest,
    PortalResponse,
    PortalListResponse,
    PublicPortalResponse,
    PublicSubmissionResponse,
    SubmissionListResponse,
    SubmissionListItem,
)

router = APIRouter(prefix="/api", tags=["Portals & Intake Forms"])


# ============================================================================
# PUBLIC ENDPOINTS (No Authentication Required)
# ============================================================================

@router.get("/public/portals/{slug}", response_model=PublicPortalResponse)
async def get_public_portal(slug: str):
    """
    Get public intake portal metadata and template field configurations.
    Allows anonymous applicant browsers to render the form dynamically.
    """
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_slug(slug)
    if not portal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portal '{slug}' was not found or is currently inactive."
        )

    template = portal.get("template") or {}
    field_mappings = template.get("field_mappings") or {}
    field_order = template.get("field_order") or list(field_mappings.keys())

    # Detect image fields
    image_fields = [
        f for f, cfg in field_mappings.items()
        if isinstance(cfg, dict) and cfg.get("type") in ["image", "signature", "stamp"]
    ]

    return PublicPortalResponse(
        id=portal["id"],
        name=portal["name"],
        slug=portal["slug"],
        description=portal.get("description"),
        template_id=portal["template_id"],
        field_mappings=field_mappings,
        field_order=field_order,
        has_image_fields=bool(image_fields),
        image_fields=image_fields,
    )


@router.post("/public/portals/{slug}/submit", response_model=PublicSubmissionResponse)
@limiter.limit("30/minute")
async def submit_public_portal_form(request: Request, slug: str):
    """
    Submit form data and generate the filled PDF without authentication.
    Supports both multipart/form-data (with file uploads) and JSON payloads (with base64 signatures).
    """
    portal_service = get_portal_service()
    content_type = request.headers.get("content-type", "")

    form_data: Dict[str, Any] = {}
    uploaded_files: Dict[str, tuple] = {}

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            for key, value in form.items():
                if hasattr(value, "filename") and value.filename:
                    # Uploaded file
                    file_bytes = await value.read()
                    uploaded_files[key] = (value.filename, file_bytes)
                else:
                    # Form text field
                    form_data[key] = value

            # Also check if a dedicated "data" JSON field was sent in the form
            if "data" in form_data and isinstance(form_data["data"], str):
                try:
                    nested_data = json.loads(form_data["data"])
                    if isinstance(nested_data, dict):
                        form_data.update(nested_data)
                except Exception:
                    pass

        elif "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                # Handle either direct dict or {"data": {...}}
                form_data = body.get("data") if isinstance(body.get("data"), dict) else body
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Request must be application/json or multipart/form-data."
            )

        client_ip = request.client.host if request.client else "unknown"

        result = portal_service.process_public_submission(
            slug=slug,
            form_data=form_data,
            uploaded_files=uploaded_files,
            ip_address=client_ip,
        )

        return PublicSubmissionResponse(
            status="success",
            message=result["message"],
            submission_id=result["submission_id"],
            pdf_url=result["pdf_url"],
            download_url=result["pdf_url"],
            created_at=result["created_at"],
        )

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        print(f"❌ Portal submission error on slug '{slug}': {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate application PDF: {str(e)}"
        )


@router.get("/public/portals/{slug}/live-feed.csv")
async def public_portal_live_csv(
    slug: str,
    token: str = Query(..., description="Access token for the portal")
):
    """
    Live CSV feed for automatic syncing into Google Sheets using =IMPORTDATA("url").
    Validates the portal's access token to protect client data.
    """
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_slug(slug)
    if not portal or portal.get("access_token") != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal or access token.")

    csv_data = portal_service.export_csv_data(portal["id"])
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'inline; filename="{slug}_submissions.csv"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    )


# ============================================================================
# AUTHENTICATED PORTAL MANAGEMENT (For Portal Owners / AA Rescue)
# ============================================================================

@router.post("/portals", response_model=PortalResponse, status_code=status.HTTP_201_CREATED)
async def create_portal(
    payload: PortalCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new public form portal linked to a template"""
    portal_service = get_portal_service()
    try:
        portal = portal_service.create_portal(
            user_id=current_user["id"],
            template_id=payload.template_id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            email_settings=payload.email_settings,
            sheet_settings=payload.sheet_settings,
        )

        base_backend = os.getenv("BACKEND_URL", "https://api.bulkform.app")
        live_feed_url = f"{base_backend}/api/public/portals/{portal['slug']}/live-feed.csv?token={portal['access_token']}"

        return PortalResponse(
            id=portal["id"],
            user_id=portal["user_id"],
            template_id=portal["template_id"],
            name=portal["name"],
            slug=portal["slug"],
            description=portal.get("description"),
            is_active=portal.get("is_active", True),
            email_settings=portal.get("email_settings") or {},
            sheet_settings=portal.get("sheet_settings") or {},
            access_token=portal["access_token"],
            total_submissions=portal.get("total_submissions", 0),
            live_feed_url=live_feed_url,
            created_at=portal.get("created_at"),
            updated_at=portal.get("updated_at"),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/portals", response_model=PortalListResponse)
async def list_user_portals(current_user: dict = Depends(get_current_user)):
    """List all form portals owned by the authenticated user"""
    portal_service = get_portal_service()
    portals = portal_service.list_user_portals(current_user["id"])
    base_backend = os.getenv("BACKEND_URL", "https://api.bulkform.app")

    formatted = []
    for p in portals:
        template_name = p.get("pdf_templates", {}).get("name") if isinstance(p.get("pdf_templates"), dict) else None
        live_feed_url = f"{base_backend}/api/public/portals/{p['slug']}/live-feed.csv?token={p['access_token']}"
        formatted.append(
            PortalResponse(
                id=p["id"],
                user_id=p["user_id"],
                template_id=p["template_id"],
                template_name=template_name,
                name=p["name"],
                slug=p["slug"],
                description=p.get("description"),
                is_active=p.get("is_active", True),
                email_settings=p.get("email_settings") or {},
                sheet_settings=p.get("sheet_settings") or {},
                access_token=p["access_token"],
                total_submissions=p.get("total_submissions", 0),
                live_feed_url=live_feed_url,
                created_at=p.get("created_at"),
                updated_at=p.get("updated_at"),
            )
        )

    return PortalListResponse(portals=formatted, total=len(formatted))


@router.get("/portals/{portal_id}", response_model=PortalResponse)
async def get_portal_details(
    portal_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get portal details by ID"""
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_id(portal_id, current_user["id"])
    if not portal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal not found.")

    base_backend = os.getenv("BACKEND_URL", "https://api.bulkform.app")
    live_feed_url = f"{base_backend}/api/public/portals/{portal['slug']}/live-feed.csv?token={portal['access_token']}"

    template_name = portal.get("pdf_templates", {}).get("name") if isinstance(portal.get("pdf_templates"), dict) else None

    return PortalResponse(
        id=portal["id"],
        user_id=portal["user_id"],
        template_id=portal["template_id"],
        template_name=template_name,
        name=portal["name"],
        slug=portal["slug"],
        description=portal.get("description"),
        is_active=portal.get("is_active", True),
        email_settings=portal.get("email_settings") or {},
        sheet_settings=portal.get("sheet_settings") or {},
        access_token=portal["access_token"],
        total_submissions=portal.get("total_submissions", 0),
        live_feed_url=live_feed_url,
        created_at=portal.get("created_at"),
        updated_at=portal.get("updated_at"),
    )


@router.put("/portals/{portal_id}", response_model=PortalResponse)
async def update_portal(
    portal_id: str,
    payload: PortalUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update settings (name, description, email notifications, sheets settings, active status)"""
    portal_service = get_portal_service()
    portal = portal_service.update_portal(portal_id, current_user["id"], payload.dict(exclude_unset=True))
    if not portal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal not found.")

    base_backend = os.getenv("BACKEND_URL", "https://api.bulkform.app")
    live_feed_url = f"{base_backend}/api/public/portals/{portal['slug']}/live-feed.csv?token={portal['access_token']}"

    return PortalResponse(
        id=portal["id"],
        user_id=portal["user_id"],
        template_id=portal["template_id"],
        name=portal["name"],
        slug=portal["slug"],
        description=portal.get("description"),
        is_active=portal.get("is_active", True),
        email_settings=portal.get("email_settings") or {},
        sheet_settings=portal.get("sheet_settings") or {},
        access_token=portal["access_token"],
        total_submissions=portal.get("total_submissions", 0),
        live_feed_url=live_feed_url,
        created_at=portal.get("created_at"),
        updated_at=portal.get("updated_at"),
    )


@router.get("/portals/{portal_id}/submissions", response_model=SubmissionListResponse)
async def get_portal_submissions(
    portal_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve applicant submissions for a portal"""
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_id(portal_id, current_user["id"])
    if not portal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal not found.")

    submissions, total = portal_service.get_submissions(portal_id, limit, offset)
    items = [
        SubmissionListItem(
            id=s["id"],
            portal_id=s["portal_id"],
            applicant_name=s.get("applicant_name"),
            applicant_email=s.get("applicant_email"),
            submitted_data=s.get("submitted_data") or {},
            pdf_url=s["pdf_url"],
            created_at=s["created_at"],
        )
        for s in submissions
    ]

    return SubmissionListResponse(portal_id=portal_id, submissions=items, total=total)


@router.get("/portals/{portal_id}/export/csv")
async def export_portal_csv(
    portal_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download full submission records as a CSV spreadsheet"""
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_id(portal_id, current_user["id"])
    if not portal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal not found.")

    csv_data = portal_service.export_csv_data(portal_id)
    filename = f"{portal['slug']}_submissions.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/portals/{portal_id}/export/xlsx")
async def export_portal_excel(
    portal_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download full submission records as an Excel (.xlsx) workbook"""
    portal_service = get_portal_service()
    portal = portal_service.get_portal_by_id(portal_id, current_user["id"])
    if not portal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal not found.")

    excel_bytes = portal_service.export_excel_data(portal_id)
    filename = f"{portal['slug']}_submissions.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
