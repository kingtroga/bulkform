"""
Template Routes
API endpoints for managing PDF form templates
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Form, File, UploadFile
from typing import Optional, Dict, Any
import os
import shutil
import stripe
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
from services.pdf_processor import PDFProcessor
from utils.utils import run_async 
from starlette.responses import FileResponse
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
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
    target_session_id = f"template_previews/{template_id}"
    
    local_pdf_path = f"{temp_dir}/{template_id}_original.pdf"
    preview_path = f"{temp_dir}/page_1.png"

    try:
        os.makedirs(temp_dir, exist_ok=True) 

        pdf_processor.download_pdf_from_storage(
            pdf_url,
            local_pdf_path
        )

        pdf_processor.pdf_to_images(
            pdf_path=local_pdf_path,
            session_id=target_session_id,
            page_numbers=[1],
        )
        
        if not os.path.exists(preview_path):
            raise FileNotFoundError("PDF conversion failed to produce page 1 preview.")

        return preview_path
    
    finally:
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
    
    if os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/png")

    try:
        pdf_url = template_service.get_template_pdf_url(template_id)
        if not pdf_url:
            raise HTTPException(status_code=404, detail="Template or PDF URL not found")
        
        await run_async(
            generate_template_preview_sync,
            template_id,
            pdf_url,
            temp_dir
        )
        
        if not os.path.exists(preview_path):
            raise Exception("Preview file was not successfully created.")

        return FileResponse(preview_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Preview generation failed for {template_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to generate template preview. Try again later."
        )
    
@router.post("/{template_id}/preview-field")
async def preview_template_field(
    template_id: str,
    field_name: str = Form(...),
    field_type: str = Form(...),
    # Text-specific
    field_value: str = Form(None),
    # Image-specific
    image_name: str = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Preview a single field from a template using the template's stored settings
    
    🔒 Requires authentication
    
    **USE CASE:** User filling out template wants to see how their input will look
    
    **Workflow:**
    1. Get template from database
    2. Get field configuration (coordinates, font, size, etc.)
    3. Download template PDF from storage
    4. Render field on the appropriate page
    5. Return preview image
    
    **Parameters:**
    - template_id: Template UUID
    - field_name: Name of the field (e.g., "first_name")
    - field_type: "text" or "image"
    - field_value: Text to preview (for text fields)
    - image_name: Image name to use (for image fields)
    
    **Returns:** PNG image of the page with field rendered
    """
    try:
        # Get template
        template = template_service.get_template(template_id, current_user['id'])
        if not template:
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")
        
        # Get field configuration
        field_mappings = template.get('field_mappings', {})
        if field_name not in field_mappings:
            raise HTTPException(status_code=400, detail=f"Field '{field_name}' not found in template")
        
        field_config = field_mappings[field_name]
        
        # Validate field type matches
        if field_config.get('type') != field_type:
            raise HTTPException(
                status_code=400, 
                detail=f"Field type mismatch: expected {field_config.get('type')}, got {field_type}"
            )
        
        # Create temporary preview session
        import uuid
        preview_session_id = f"preview_{template_id}_{field_name}_{uuid.uuid4().hex[:8]}"
        preview_temp_path = f"{pdf_processor.TEMP_FOLDER}/{preview_session_id}"
        os.makedirs(preview_temp_path, exist_ok=True)
        
        try:
            # Download template PDF
            pdf_storage_path = template['pdf_url']
            local_pdf_path = f"{preview_temp_path}/template.pdf"
            
            await run_async(
                pdf_processor.download_file_from_storage,
                pdf_storage_path,
                local_pdf_path
            )
            
            # Convert to images
            num_pages = await run_async(
                pdf_processor.pdf_to_images,
                local_pdf_path,
                preview_session_id
            )
            
            page_number = field_config['page']
            
            if page_number > num_pages:
                raise HTTPException(
                    status_code=400,
                    detail=f"Page {page_number} does not exist (template has {num_pages} pages)"
                )
            
            # Get the page image
            page_path = f"{preview_temp_path}/page_{page_number}.png"
            if not os.path.exists(page_path):
                raise HTTPException(status_code=500, detail="Failed to generate page image")
            
            # Create preview copy
            preview_path = f"{preview_temp_path}/preview_page_{page_number}.png"
            await run_async(shutil.copy, page_path, preview_path)
            
            # Render field based on type
            if field_type == 'text':
                if not field_value:
                    raise HTTPException(status_code=400, detail="field_value required for text preview")
                
                # Prepare text data
                text_items = [{
                    'x': field_config['x'],
                    'y': field_config['y'],
                    'text': field_value,
                    'size': field_config.get('size', 12),
                    'align': field_config.get('align', 'center'),
                    'font': field_config.get('font', 'arial')
                }]
                
                # Render text on preview
                await run_async(
                    pdf_processor.write_text_on_image_preview,
                    preview_path,
                    text_items
                )
                
            elif field_type == 'image':
                if not image_name:
                    raise HTTPException(status_code=400, detail="image_name required for image preview")
                
                # Get user's uploaded image
                image_result = (
                    template_service.supabase
                    .table("user_images")
                    .select("*")
                    .eq("user_id", current_user['id'])
                    .eq("image_name", image_name)
                    .single()
                    .execute()
                )
                
                if not image_result.data:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Image '{image_name}' not found. Please upload it first."
                    )
                
                # Download user's image
                image_storage_path = image_result.data['storage_path']
                temp_image_path = f"{preview_temp_path}/temp_image.png"
                
                await run_async(
                    pdf_processor.download_file_from_storage,
                    image_storage_path,
                    temp_image_path
                )
                
                # Prepare image data
                image_items = [{
                    'x': field_config['x'],
                    'y': field_config['y'],
                    'image_path': temp_image_path
                }]
                
                # Add optional dimensions from template
                if 'width' in field_config:
                    image_items[0]['width'] = field_config['width']
                if 'height' in field_config:
                    image_items[0]['height'] = field_config['height']
                
                # Render image on preview
                await run_async(
                    pdf_processor.add_images_to_preview,
                    preview_path,
                    image_items
                )
            
            # Cleanup function
            def cleanup_preview():
                if os.path.exists(preview_temp_path):
                    try:
                        shutil.rmtree(preview_temp_path)
                    except:
                        pass
            
            # Return preview with background cleanup
            from starlette.background import BackgroundTask
            return FileResponse(
                preview_path,
                media_type="image/png",
                background=BackgroundTask(cleanup_preview)
            )
            
        except HTTPException:
            # Cleanup on HTTP errors
            if os.path.exists(preview_temp_path):
                shutil.rmtree(preview_temp_path)
            raise
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Template preview failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)}")

# ============================================================================
# CUSTOM TEMPLATE ENDPOINTS
# ============================================================================

@router.post("", response_model=TemplateCreatedResponse, status_code=201)
async def create_template(
    name: str = Form(..., description="Template name"),
    field_mappings: str = Form(..., description="JSON string of field mappings"),
    file: UploadFile = File(..., description="PDF template file"),
    description: Optional[str] = Form(None, description="Template description"),
    template_kind: str = Form("standard", description="standard | repeated"),
    repeat_config: Optional[str] = Form(None, description="JSON string repeat config"),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new custom template

    🔒 Requires authentication

    Upload PDF + field mappings in one request.

    Supports:
    - template_kind = "standard"
    - template_kind = "repeated" (requires repeat_config JSON string)
    """
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")

        import json
        import uuid

        # Parse field_mappings JSON
        try:
            field_mappings_dict = json.loads(field_mappings)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_mappings JSON format")

        if not template_service.validate_field_mappings(field_mappings_dict):
            raise HTTPException(status_code=400, detail="Invalid field mappings. Check structure and required fields.")

        # Parse repeat_config JSON (only if repeated)
        repeat_config_dict = None
        if template_kind == "repeated":
            if not repeat_config:
                raise HTTPException(
                    status_code=400,
                    detail="repeat_config is required when template_kind='repeated'"
                )
            try:
                repeat_config_dict = json.loads(repeat_config)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid repeat_config JSON format")
        else:
            repeat_config_dict = None

        user_id = current_user["id"]
        template_id = str(uuid.uuid4())

        # Read uploaded file
        file_content = await file.read()

        # Upload to Supabase Storage
        storage_path = f"templates/{user_id}/{template_id}.pdf"
        try:
            pdf_processor.supabase.storage.from_(pdf_processor.STORAGE_BUCKET).upload(
                storage_path,
                file_content,
                file_options={"content-type": "application/pdf"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload PDF to storage: {str(e)}")

        # Create DB record
        created_template_id = template_service.create_template(
            user_id=user_id,
            name=name,
            pdf_url=storage_path,
            field_mappings=field_mappings_dict,
            description=description,
            template_kind=template_kind,
            repeat_config=repeat_config_dict,
        )

        return TemplateCreatedResponse(
            template_id=created_template_id,
            message="Template created successfully"
        )

    except HTTPException:
        raise
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
    page_official: int = 1,
    page_size_official: int = 24,
    category: Optional[str] = None,
    page_custom: int = 1,
    page_size_custom: int = 24,
):
    """
    Paginated list of:
      - official (public, active)
      - user's custom (private, active)
    """
    try:
        official_items, official_total = template_service.list_official_templates_paged(
            page=page_official,
            page_size=page_size_official,
            category=category,
        )
        
        custom_items, custom_total = template_service.list_templates_paged(
            user_id=current_user["id"],
            page=page_custom,
            page_size=page_size_custom,
        )

        official = [TemplateResponse(**t) for t in official_items]
        custom   = [TemplateResponse(**t) for t in custom_items]

        total_pages_official = (official_total + page_size_official - 1) // page_size_official if page_size_official else 0
        total_pages_custom   = (custom_total   + page_size_custom   - 1) // page_size_custom if page_size_custom else 0

        has_prev_official = page_official > 1
        has_next_official = page_official < max(1, total_pages_official)

        has_prev_custom = page_custom > 1
        has_next_custom = page_custom < max(1, total_pages_custom)

        return AllTemplatesResponse(
            official=official,
            custom=custom,
            total_official=official_total,
            total_custom=custom_total,
            page_official=page_official,
            page_size_official=page_size_official,
            total_pages_official=total_pages_official,
            has_prev_official=has_prev_official,
            has_next_official=has_next_official,
            page_custom=page_custom,
            page_size_custom=page_size_custom,
            total_pages_custom=total_pages_custom,
            has_prev_custom=has_prev_custom,
            has_next_custom=has_next_custom,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")
    
@router.get("/search-for-dropdown")
async def search_templates_for_dropdown(
    query: str = Query(default="", description="Search query"),
    limit: int = Query(default=20, ge=1, le=50, description="Max results"),
    current_user: dict = Depends(get_current_user)
):
    """
    Lightweight template search for dropdowns
    
    - Returns max 20 results (enough for a dropdown)
    - Searches both official and custom templates
    - Only returns: id, name, is_official (minimal data)
    """
    try:
        query_filter = f"%{query}%" if query else "%"
        
        # Search official templates
        official_result = (
            template_service.supabase
            .table("pdf_templates")
            .select("id, name, is_official")
            .eq("is_official", True)
            .eq("active", True)
            .ilike("name", query_filter)
            .limit(limit // 2)  # Half for official
            .execute()
        )
        
        # Search user's custom templates
        custom_result = (
            template_service.supabase
            .table("pdf_templates")
            .select("id, name, is_official")
            .eq("user_id", current_user["id"])
            .eq("is_official", False)
            .eq("active", True)
            .ilike("name", query_filter)
            .limit(limit // 2)  # Half for custom
            .execute()
        )
        
        official = official_result.data if official_result.data else []
        custom = custom_result.data if custom_result.data else []
        
        return {
            "templates": official + custom,
            "total": len(official) + len(custom),
            "showing_partial": len(official) + len(custom) >= limit
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


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
        result = (
                template_service.supabase
                .table("pdf_templates")
                .select("*")
                .or_(
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
    - template_kind, repeat_config
    - field_mappings (merge/upsert)
    - remove_fields (delete specific mappings)
    """
    print(
        f"[UPDATE_TEMPLATE] user={current_user.get('id')} template_id={template_id} "
        f"payload={request.dict(exclude_unset=True)}"
    )

    try:
        existing = template_service.get_template(template_id, current_user["id"])
        if not existing:
            print(f"[UPDATE_TEMPLATE] Template not found/unauthorized user={current_user.get('id')}")
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")

        # Prevent editing official templates unless it's yours (your service logic might already enforce this)
        if existing.get("is_official") and existing.get("user_id") != current_user["id"]:
            print(f"[UPDATE_TEMPLATE] Forbidden edit of official template={template_id}")
            raise HTTPException(status_code=403, detail="Official templates cannot be edited")

        updates: Dict[str, Any] = {}

        # Basic fields
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.pdf_url is not None:
            updates["pdf_url"] = request.pdf_url
        if request.category is not None:
            updates["category"] = (request.category or "").strip() or None

        # ✅ NEW: template_kind + repeat_config
        if request.template_kind is not None:
            updates["template_kind"] = request.template_kind
            # If switching away from repeated, wipe repeat_config
            if request.template_kind != "repeated":
                updates["repeat_config"] = None

        if request.repeat_config is not None:
            # Validator already wipes this if template_kind != repeated
            updates["repeat_config"] = request.repeat_config

        # Field mappings merge/remove
        if request.field_mappings is not None or (request.remove_fields and len(request.remove_fields) > 0):
            existing_mappings = dict(existing.get("field_mappings", {}))

            # Remove keys
            for k in (request.remove_fields or []):
                existing_mappings.pop(k, None)

            # Upsert keys
            for k, v in (request.field_mappings or {}).items():
                existing_mappings[k] = v

            if not template_service.validate_field_mappings(existing_mappings):
                raise HTTPException(status_code=400, detail="Invalid field mappings")

            updates["field_mappings"] = existing_mappings

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated_ok = template_service.update_template(
            template_id=template_id,
            user_id=current_user["id"],
            updates=updates
        )
        if not updated_ok:
            raise HTTPException(status_code=404, detail="Template not found or unauthorized")

        updated = template_service.get_template(template_id, current_user["id"])
        return TemplateResponse(**updated)

    except HTTPException:
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

        success = template_service.soft_delete_template(
            template_id=template_id,
            user_id=current_user["id"]
        )

        if not success:
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
    price: float = Form(default=0.00, description="Annual subscription price in dollars"),
    field_order: Optional[str] = Form(None, description="JSON array of field names in CSV order"),
    description: Optional[str] = Form(None, description="Template description"),

    # ✅ NEW
    template_kind: str = Form("standard", description="standard | repeated"),
    repeat_config: Optional[str] = Form(None, description="JSON string repeat config"),

    current_user: dict = Depends(get_current_user)
):
    """
    Create official template with automatic Stripe product/price creation

    🔒 ADMIN ONLY

    Supports:
    - template_kind = "standard"
    - template_kind = "repeated" (requires repeat_config JSON string)
    """
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")

        import json
        import uuid

        # Parse field_mappings
        try:
            field_mappings_dict = json.loads(field_mappings)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_mappings JSON format")

        # Parse field_order (optional)
        field_order_list = None
        if field_order:
            try:
                field_order_list = json.loads(field_order)
            except json.JSONDecodeError:
                field_order_list = None

        if not field_order_list:
            field_order_list = list(field_mappings_dict.keys())

        if not template_service.validate_field_mappings(field_mappings_dict):
            raise HTTPException(status_code=400, detail="Invalid field mappings. Check structure and required fields.")

        # ✅ Parse repeat_config (only if repeated)
        repeat_config_dict = None
        if template_kind == "repeated":
            if not repeat_config:
                raise HTTPException(
                    status_code=400,
                    detail="repeat_config is required when template_kind='repeated'"
                )
            try:
                repeat_config_dict = json.loads(repeat_config)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid repeat_config JSON format")

        user_id = current_user["id"]
        template_id = str(uuid.uuid4())

        file_content = await file.read()
        storage_path = f"official_templates/{official_form_id}/{template_id}.pdf"

        # Upload PDF
        try:
            pdf_processor.supabase.storage.from_(pdf_processor.STORAGE_BUCKET).upload(
                storage_path,
                file_content,
                file_options={"content-type": "application/pdf"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload PDF to storage: {str(e)}")

        stripe_price_id = None

        # Stripe product/price (only if paid)
        if price > 0:
            try:
                stripe_product = stripe.Product.create(
                    name=f"BulkForm {name} Template",
                    description=f"Annual subscription to {name} official template",
                    metadata={
                        "template_id": template_id,
                        "official_form_id": official_form_id,
                        "category": category
                    }
                )

                stripe_price = stripe.Price.create(
                    product=stripe_product.id,
                    unit_amount=int(price * 100),
                    currency="usd",
                    recurring={"interval": "year", "interval_count": 1},
                    metadata={
                        "template_id": template_id,
                        "official_form_id": official_form_id
                    }
                )

                stripe_price_id = stripe_price.id

            except stripe.error.StripeError as e:
                # Roll back uploaded file if Stripe fails
                try:
                    pdf_processor.supabase.storage.from_(pdf_processor.STORAGE_BUCKET).remove([storage_path])
                except Exception:
                    pass

                raise HTTPException(status_code=500, detail=f"Stripe integration failed: {str(e)}")

        # Complexity heuristic
        if price <= 10:
            complexity = "simple"
        elif price <= 20:
            complexity = "medium"
        else:
            complexity = "complex"

        # Create DB record
        created_template_id = template_service.create_official_template(
            user_id=user_id,
            name=name,
            pdf_url=storage_path,
            field_mappings=field_mappings_dict,
            field_order=field_order_list,
            official_form_id=official_form_id,
            category=category,
            description=description,
            price=price,
            stripe_price_id=stripe_price_id,
            complexity=complexity,

            # ✅ NEW
            template_kind=template_kind,
            repeat_config=repeat_config_dict,
        )

        return TemplateCreatedResponse(
            template_id=created_template_id,
            message=(
                f"Official template created successfully with Stripe product (${price}/year)"
                if price > 0 else
                "Free official template created successfully"
            ),
            stripe_price_id=stripe_price_id
        )

    except ValueError as e:
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
            if not field.get('name') or not field['name'].strip():
                continue
            
            import re
            base_name = re.sub(r'[^a-zA-Z0-9_]', '_', field['name'].strip()).lower()
            
            field_name = base_name
            index = 1
            
            while field_name in field_mappings:
                index += 1
                field_name = f"{base_name}_{index}"
            
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