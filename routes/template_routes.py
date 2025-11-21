"""
Template Routes
API endpoints for managing PDF form templates

Endpoints:
- POST   /api/templates              - Create custom template (with file upload!)
- GET    /api/templates              - List user's custom templates
- GET    /api/templates/all          - List all (official + custom)
- GET    /api/templates/{id}         - Get specific template
- PUT    /api/templates/{id}         - Update template
- DELETE /api/templates/{id}         - Delete template
- GET    /api/templates/official     - List official templates
- GET    /api/templates/official/{form_id} - Get official by form ID
- POST   /api/templates/official     - Create official (admin only)
- GET    /api/templates/categories   - List categories with counts
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Form, File, UploadFile
from typing import Optional, Dict, Any
import os
from models.template_models import (
    CreateTemplateRequest,
    UpdateTemplateRequest,
    CreateOfficialTemplateRequest,
    TemplateResponse,
    TemplateListResponse,
    AllTemplatesResponse,
    TemplateCategoryResponse,
    TemplateCreatedResponse,
    TemplateDeletedResponse,
    TemplateConversionRequest
)
from services.template_service import get_template_service
from services.auth import get_current_user
from services.pdf_processor import PDFProcessor # Assuming PDFProcessor is available
from utils.utils import run_async 
from starlette.responses import FileResponse # <-- NEW: For serving the image file
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(prefix="/api/templates", tags=["Templates"])

# Initialize service
template_service = get_template_service()

# Initialize PDF Processor outside endpoints
pdf_processor = PDFProcessor()

def generate_template_preview_sync(template_id: str, pdf_url: str, temp_dir: str) -> str:
    """
    Blocking function executed in a separate thread.
    1. Downloads the PDF from Supabase Storage.
    2. Converts the first page to a PNG thumbnail.
    3. Returns the path to the generated image.
    """
    # 📝 Note: temp_dir is the full desired folder path (e.g., 'temp_pdf_uploads/template_previews/{id}')
    # The session_id used by pdf_to_images must represent the sub-folder name.
    
    # Extract the necessary sub-folder name from the full temp_dir path
    # Example: If temp_dir is 'temp_pdf_uploads/template_previews/b1f6...', 
    # the target_session_id is 'template_previews/b1f6...'
    target_session_id = f"template_previews/{template_id}"
    
    local_pdf_path = f"{temp_dir}/{template_id}_original.pdf"
    preview_path = f"{temp_dir}/page_1.png"

    try:
        # Create the temp directory structure needed for download and final output
        os.makedirs(temp_dir, exist_ok=True) 

        # 1. Download PDF from storage (blocking I/O)
        pdf_processor.download_pdf_from_storage(
            pdf_url,
            local_pdf_path
        )

        # 2. Convert first page to image (FIXED: Removed 'output_dir', Adjusted session_id)
        # pdf_to_images creates its output folder based on session_id: 
        # {self.TEMP_FOLDER}/{session_id}
        pdf_processor.pdf_to_images(
            pdf_path=local_pdf_path,
            session_id=target_session_id, # <--- PASS THE CORRECT SUB-FOLDER STRUCTURE
            page_numbers=[1],
            # ❌ REMOVED: output_dir=temp_dir, 
            # 📝 Rationale: This keyword is not supported and is now handled by session_id/self.TEMP_FOLDER logic.
        )
        
        # 3. Check if the file was created.
        if not os.path.exists(preview_path):
            raise FileNotFoundError("PDF conversion failed to produce page 1 preview.")

        return preview_path
    
    finally:
        # Simple cleanup
        if os.path.exists(local_pdf_path):
            os.remove(local_pdf_path)


# ============================================================================
# PREVIEW ENDPOINT (FOR TEMPLATE CARDS)
# ============================================================================

@router.get("/preview/{template_id}/page/1")
async def preview_template_page_one(
    template_id: str
):
    """
    Generates and returns the thumbnail (PNG) of the first page of a template.
    
    ✅ Public endpoint (Template previews are public)
    
    - Caches the generated image to ensure fast subsequent access.
    """
    temp_dir = f"{pdf_processor.TEMP_FOLDER}/template_previews/{template_id}"
    preview_path = f"{temp_dir}/page_1.png"
    
    # 1. Check Cache
    if os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/png")

    try:
        # 2. Get PDF URL from the template (must handle public access)
        pdf_url = template_service.get_template_pdf_url(template_id)
        if not pdf_url:
            raise HTTPException(status_code=404, detail="Template or PDF URL not found")
        
        # 3. Generate preview asynchronously
        await run_async(
            generate_template_preview_sync,
            template_id,
            pdf_url,
            temp_dir
        )
        
        # 4. Serve the generated image
        if not os.path.exists(preview_path):
            raise Exception("Preview file was not successfully created.")

        return FileResponse(preview_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        # Log the error, but return a clean 500 error for the user
        print(f"❌ Preview generation failed for {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to generate template preview. Try again later."
        )

# ============================================================================
# CUSTOM TEMPLATE ENDPOINTS
# ============================================================================

@router.post("", response_model=TemplateCreatedResponse, status_code=201)
async def create_template(
    name: str = Form(..., description="Template name"),
    field_mappings: str = Form(..., description="JSON string of field mappings"),
    file: UploadFile = File(..., description="PDF template file"),
    description: Optional[str] = Form(None, description="Template description"),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new custom template
    
    🔒 Requires authentication
    
    **Upload PDF + field mappings in one request!**
    
    - **file**: PDF file to use as template (required)
    - **name**: Template name (required)
    - **field_mappings**: JSON string of field coordinates (required)
    - **description**: Optional description
    
    **Example field_mappings:**
    ```json
    {
        "first_name": {"page": 1, "x": 25, "y": 30, "size": 12, "font": "arial"},
        "last_name": {"page": 1, "x": 25, "y": 35, "size": 12, "font": "arial"}
    }
    ```
    
    Returns the created template ID
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")
        
        # Parse field_mappings JSON
        import json
        try:
            field_mappings_dict = json.loads(field_mappings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid field_mappings JSON format"
            )
        
        # Validate field mappings
        if not template_service.validate_field_mappings(field_mappings_dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid field mappings. Check structure and required fields."
            )
        
        # Upload PDF to Supabase Storage
        from services.pdf_processor import PDFProcessor
        import uuid
        
        pdf_processor = PDFProcessor()
        user_id = current_user['id']
        template_id = str(uuid.uuid4())
        
        # Read file content
        file_content = await file.read()
        
        # Save to temp location
        import os
        temp_path = f"/tmp/template_{template_id}.pdf"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        # Upload to Supabase Storage: templates/{user_id}/{template_id}.pdf
        storage_path = f"templates/{user_id}/{template_id}.pdf"
        
        try:
            pdf_processor.supabase.storage.from_(
                pdf_processor.STORAGE_BUCKET
            ).upload(
                storage_path,
                file_content,
                file_options={"content-type": "application/pdf"}
            )
        except Exception as e:
            # If upload fails, clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise Exception(f"Failed to upload PDF to storage: {str(e)}")
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # Create template record with storage_path
        template_id = template_service.create_template(
            user_id=user_id,
            name=name,
            pdf_url=storage_path,  # Store storage path
            field_mappings=field_mappings_dict,
            description=description

        )
        
        return TemplateCreatedResponse(
            template_id=template_id,
            message="Template created successfully"
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    limit: int = Query(default=100, ge=1, le=500, description="Max templates to return"),
    offset: int = Query(default=0, ge=0, description="Number to skip"),
    current_user: dict = Depends(get_current_user)
):
    """
    List user's custom templates
    
    🔒 Requires authentication
    
    Returns only templates created by the current user
    """
    try:
        templates = template_service.list_templates(
            user_id=current_user['id'],
            limit=limit,
            offset=offset
        )
        
        # Convert to response models
        template_responses = [
            TemplateResponse(**template) for template in templates
        ]
        
        return TemplateListResponse(
            templates=template_responses,
            total=len(template_responses)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.get("/all", response_model=AllTemplatesResponse)
async def list_all_templates(
    current_user: dict = Depends(get_current_user),
    # Official pagination + optional filter
    page_official: int = 1,
    page_size_official: int = 24,
    category: Optional[str] = None,
    # Custom pagination
    page_custom: int = 1,
    page_size_custom: int = 24,
):
    """
    Paginated list of:
      - official (public, active)
      - user's custom (private, active)
    """
    try:
        # Official
        official_items, official_total = template_service.list_official_templates_paged(
            page=page_official,
            page_size=page_size_official,
            category=category,
        )
        # Custom
        custom_items, custom_total = template_service.list_templates_paged(
            user_id=current_user["id"],
            page=page_custom,
            page_size=page_size_custom,
        )

        official = [TemplateResponse(**t) for t in official_items]
        custom   = [TemplateResponse(**t) for t in custom_items]

        # meta
        total_pages_official = (official_total + page_size_official - 1) // page_size_official if page_size_official else 0
        total_pages_custom   = (custom_total   + page_size_custom   - 1) // page_size_custom if page_size_custom else 0

        has_prev_official = page_official > 1
        has_next_official = page_official < max(1, total_pages_official)

        has_prev_custom = page_custom > 1
        has_next_custom = page_custom < max(1, total_pages_custom)

        return AllTemplatesResponse(
            # data
            official=official,
            custom=custom,
            # totals
            total_official=official_total,
            total_custom=custom_total,
            # official meta
            page_official=page_official,
            page_size_official=page_size_official,
            total_pages_official=total_pages_official,
            has_prev_official=has_prev_official,
            has_next_official=has_next_official,
            # custom meta
            page_custom=page_custom,
            page_size_custom=page_size_custom,
            total_pages_custom=total_pages_custom,
            has_prev_custom=has_prev_custom,
            has_next_custom=has_next_custom,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.get("/search")
async def search_templates(
    query: str = Query(..., min_length=1, description="Search query"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search templates by name (case-insensitive, partial match)
    
    🔒 Requires authentication
    
    Searches in user's custom templates
    """
    try:
        # Use Supabase ilike for case-insensitive partial search
        result = (
                template_service.supabase
                .table("pdf_templates")
                .select("*")
                .or_(
                    # match official templates by name OR user's own templates by name
                    f"and(is_official.eq.true,name.ilike.*{query}*),and(user_id.eq.{current_user['id']},name.ilike.*{query}*)"
                )
                .execute()
            )
        
        templates = result.data if result.data else []
        
        if not templates:
            return {
                "templates": [],
                "total": 0,
                "message": "No templates found"
            }
        
        return {
            "templates": [TemplateResponse(**t) for t in templates],
            "total": len(templates)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/stats")
async def get_user_template_stats(current_user: dict = Depends(get_current_user)):
    """
    Get user's template statistics
    
    🔒 Requires authentication
    """
    try:
        total_custom = template_service.count_user_templates(current_user['id'])
        official_templates = template_service.list_official_templates()
        
        return {
            "user_id": current_user['id'],
            "custom_templates": total_custom,
            "official_templates_available": len(official_templates),
            "total_accessible": total_custom + len(official_templates)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def template_health():
    """Health check for template service"""
    return {
        "service": "Templates",
        "status": "operational",
        "features": {
            "custom_templates": True,
            "official_templates": True,
            "admin_creation": True,
            "search": True,
            "categories": True
        }
    }


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get specific template by ID
    
    🔒 Requires authentication
    
    Returns template if:
    - It's an official template (public), OR
    - It belongs to the current user
    """
    try:
        template = template_service.get_template(template_id, current_user['id'])
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template not found or unauthorized"
            )
        
        return TemplateResponse(**template)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update existing template (partial):
    - name, description, pdf_url, category
    - field_mappings (merge/upsert)
    - remove_fields (delete specific mappings)
    """
    print(f"[UPDATE_TEMPLATE] user={current_user.get('id')} template_id={template_id} payload={request.dict(exclude_unset=True)}")

    try:
        # 0) Load & guard
        existing = template_service.get_template(template_id, current_user["id"])
        if not existing:
            print(f"[UPDATE_TEMPLATE] Template not found or unauthorized for user={current_user.get('id')}")
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")

        if existing.get("is_official") and existing.get("user_id") != current_user["id"]:
            print(f"[UPDATE_TEMPLATE] Forbidden edit attempt on official template={template_id} by user={current_user.get('id')}")
            raise HTTPException(status_code=403, detail="Official templates cannot be edited")

        updates: Dict[str, Any] = {}

        # 1) Basic fields
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.pdf_url is not None:
            updates["pdf_url"] = request.pdf_url
        if request.category is not None:
            cat = (request.category or "").strip() or None
            updates["category"] = cat
        print(f"[UPDATE_TEMPLATE] Basic updates collected: {updates}")

        # 2) Field mappings merge/delete
        if request.field_mappings is not None or (request.remove_fields and len(request.remove_fields) > 0):
            existing_mappings = dict(existing.get("field_mappings", {}))
            print(f"[UPDATE_TEMPLATE] Existing mappings count={len(existing_mappings)}")

            # deletions
            for k in (request.remove_fields or []):
                existing_mappings.pop(k, None)
                print(f"[UPDATE_TEMPLATE] Removed mapping key={k}")

            # upserts
            for k, v in (request.field_mappings or {}).items():
                existing_mappings[k] = v
                print(f"[UPDATE_TEMPLATE] Upserted mapping key={k}")

            if not template_service.validate_field_mappings(existing_mappings):
                print(f"[UPDATE_TEMPLATE] Invalid field mappings detected for template={template_id}")
                raise HTTPException(status_code=400, detail="Invalid field mappings")

            updates["field_mappings"] = existing_mappings

        if not updates:
            print(f"[UPDATE_TEMPLATE] No valid fields to update for template={template_id}")
            raise HTTPException(status_code=400, detail="No fields to update")

        # 3) Persist
        print(f"[UPDATE_TEMPLATE] Applying updates: {list(updates.keys())}")
        updated_ok = template_service.update_template(
            template_id=template_id,
            user_id=current_user["id"],
            updates=updates
        )

        if not updated_ok:
            print(f"[UPDATE_TEMPLATE] update_template() returned False for template={template_id}")
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")

        updated = template_service.get_template(template_id, current_user["id"])
        print(f"[UPDATE_TEMPLATE] Update successful template={template_id}")
        return TemplateResponse(**updated)

    except HTTPException as he:
        print(f"[UPDATE_TEMPLATE] HTTPException status={he.status_code} detail={he.detail}")
        raise
    except Exception as e:
        print(f"[UPDATE_TEMPLATE] Unexpected failure: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/{template_id}", response_model=TemplateDeletedResponse)
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Soft-delete a template by setting active = false.
    🔒 Requires authentication.
    Only the owner can delete. Official templates are protected.
    Idempotent: deleting an already-inactive template still returns 200.
    """
    try:
        # Fetch template meta we need in one query
        row = (
            template_service.supabase.table("pdf_templates")
            .select("id,user_id,is_official,active")
            .eq("id", template_id)
            .single()
            .execute()
        ).data

        if not row:
            raise HTTPException(status_code=404, detail="Template not found")

        if row["is_official"]:
            raise HTTPException(
                status_code=403,
                detail="Official templates cannot be deleted by regular users"
            )

        if row["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not the owner")

        # Soft delete via service (sets active = false)
        success = template_service.soft_delete_template(
            template_id=template_id,
            user_id=current_user["id"]
        )

        if not success:
            # If update matched zero rows, treat as not found/unauthorized
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")
        
        return TemplateDeletedResponse(
            message="Template deleted successfully",
            template_id=template_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")



# ============================================================================
# OFFICIAL TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/official/list", response_model=TemplateListResponse)
async def list_official_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(default=100, ge=1, le=500)
):
    """
    List official BulkForm templates
    
    ✅ Public endpoint (no auth required)
    
    Official templates are pre-made forms like I-485, I-765, etc.
    """
    try:
        templates = template_service.list_official_templates(
            category=category,
            limit=limit
        )
        
        template_responses = [TemplateResponse(**t) for t in templates]
        
        return TemplateListResponse(
            templates=template_responses,
            total=len(template_responses)
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list official templates: {str(e)}")


@router.get("/official/{form_id}", response_model=TemplateResponse)
async def get_official_template_by_form_id(form_id: str):
    """
    Get official template by form ID
    
    ✅ Public endpoint (no auth required)
    
    Example form IDs: i-485, i-765, i-131, etc.
    """
    try:
        template = template_service.get_official_template_by_form_id(form_id)
        
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Official template '{form_id}' not found"
            )
        
        return TemplateResponse(**template)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.post("/official", response_model=TemplateCreatedResponse, status_code=201)
async def create_official_template(
    name: str = Form(..., description="Template name"),
    field_mappings: str = Form(..., description="JSON string of field mappings"),
    file: UploadFile = File(..., description="PDF template file"),
    official_form_id: str = Form(..., description="Form ID (e.g., 'i-485')"),
    category: str = Form(default="immigration", description="Template category"),
    price: float = Form(default=0.00, description="Price in dollars"),
    description: Optional[str] = Form(None, description="Template description"),
    current_user: dict = Depends(get_current_user)
):
    """
    Create official template
    
    🔒 ADMIN ONLY
    
    **Upload PDF + metadata for official template!**
    
    - **file**: PDF file (required)
    - **name**: Template name (required)
    - **official_form_id**: Form ID like 'i-485', 'i-765' (required)
    - **field_mappings**: JSON string of field coordinates (required)
    - **category**: Category (default: "immigration")
    - **price**: Price in dollars (default: 0.00)
    - **description**: Optional description
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")
        
        # Parse field_mappings JSON
        import json
        try:
            field_mappings_dict = json.loads(field_mappings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid field_mappings JSON format"
            )
        
        # Validate field mappings
        if not template_service.validate_field_mappings(field_mappings_dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid field mappings. Check structure and required fields."
            )
        
        # Upload PDF to Supabase Storage
        from services.pdf_processor import PDFProcessor
        import uuid
        
        pdf_processor = PDFProcessor()
        user_id = current_user['id']
        template_id = str(uuid.uuid4())
        
        # Read file content
        file_content = await file.read()
        
        # Save to temp location
        import os
        temp_path = f"/tmp/official_template_{template_id}.pdf"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        # Upload to Supabase Storage: official_templates/{official_form_id}/{template_id}.pdf
        storage_path = f"official_templates/{official_form_id}/{template_id}.pdf"
        
        try:
            pdf_processor.supabase.storage.from_(
                pdf_processor.STORAGE_BUCKET
            ).upload(
                storage_path,
                file_content,
                file_options={"content-type": "application/pdf"}
            )
        except Exception as e:
            # If upload fails, clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise Exception(f"Failed to upload PDF to storage: {str(e)}")
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # Create official template (will check admin status internally)
        template_id = template_service.create_official_template(
            user_id=user_id,
            name=name,
            pdf_url=storage_path,  # Store storage path
            field_mappings=field_mappings_dict,
            official_form_id=official_form_id,
            category=category,
            description=description,
            price=price
        )
        
        return TemplateCreatedResponse(
            template_id=template_id,
            message="Official template created successfully"
        )
    
    except ValueError as e:
        # Admin check failed
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create official template: {str(e)}")

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/categories/list")
async def get_template_categories():
    """
    Get all template categories with counts
    
    ✅ Public endpoint
    
    Returns categories like "immigration", "tax", "hr" with template counts
    """
    try:
        categories = template_service.get_template_categories()
        
        return {
            "categories": categories,
            "total": len(categories)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get categories: {str(e)}")

@router.post("/convert-format")
async def convert_template_format(
    data: TemplateConversionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Convert user fields to template format"""
    field_mappings = {}
    
    for page_num, fields in data.fields.items():
        for field in fields:
            # Skip fields with no name
            if not field.get('name') or not field['name'].strip():
                continue
            
            # Sanitize base name
            import re
            base_name = re.sub(r'[^a-zA-Z0-9_]', '_', field['name'].strip()).lower()
            
            field_name = base_name
            index = 1
            
            # Handle duplicates
            while field_name in field_mappings:
                index += 1
                field_name = f"{base_name}_{index}"
            
            # Base structure
            mapping = {
                "page": int(page_num),
                "x": field['gridX'],
                "y": field['gridY'],
                "type": field['type']
            }
            
            if field['type'] == 'text':
                mapping.update({
                    "size": field['size'],
                    "font": field['font'],
                    "align": field['align']
                })
            elif field['type'] == 'image':
                mapping.update({
                    "width": field.get('width', 200),
                    "height": field.get('height', 60)
                })
            
            field_mappings[field_name] = mapping
    
    return field_mappings