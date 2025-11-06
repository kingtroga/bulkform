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
from typing import Optional
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
    ErrorResponse
)
from services.template_service import get_template_service
from services.auth import get_current_user

router = APIRouter(prefix="/api/templates", tags=["Templates"])

# Initialize service
template_service = get_template_service()


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
    current_user: dict = Depends(get_current_user)
):
    """
    List ALL templates (official + user's custom)
    
    🔒 Requires authentication
    
    Returns:
    - **official**: All official BulkForm templates (public)
    - **custom**: User's custom templates (private)
    """
    try:
        result = template_service.list_all_templates(
            user_id=current_user['id'],
            include_official=True
        )
        
        official_responses = [TemplateResponse(**t) for t in result['official']]
        custom_responses = [TemplateResponse(**t) for t in result['custom']]
        
        return AllTemplatesResponse(
            official=official_responses,
            custom=custom_responses,
            total_official=len(official_responses),
            total_custom=len(custom_responses)
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
    Update existing template
    
    🔒 Requires authentication
    
    Only the template owner can update it.
    Official templates cannot be updated by regular users.
    
    **Field mappings update:** Only updates the fields you provide, keeps existing ones intact.
    """
    try:
        # Build updates dict (only include provided fields)
        updates = {}
        if request.name is not None:
            updates['name'] = request.name
        if request.description is not None:
            updates['description'] = request.description
        if request.pdf_url is not None:
            updates['pdf_url'] = request.pdf_url
        if request.field_mappings is not None:
            # Get existing template
            existing = template_service.get_template(template_id, current_user['id'])
            if not existing:
                raise HTTPException(status_code=404, detail="Template not found")
            
            # Merge field mappings (update only changed fields, keep existing ones)
            existing_mappings = existing.get('field_mappings', {})
            merged_mappings = {**existing_mappings, **request.field_mappings}
            
            # Validate merged field_mappings
            if not template_service.validate_field_mappings(merged_mappings):
                raise HTTPException(status_code=400, detail="Invalid field mappings")
            
            updates['field_mappings'] = merged_mappings
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        success = template_service.update_template(
            template_id=template_id,
            user_id=current_user['id'],
            updates=updates
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Template not found or unauthorized"
            )
        
        # Return updated template
        updated = template_service.get_template(template_id, current_user['id'])
        return TemplateResponse(**updated)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/{template_id}", response_model=TemplateDeletedResponse)
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete template
    
    🔒 Requires authentication
    
    Only the template owner can delete it.
    Official templates cannot be deleted by regular users.
    """
    try:
        # Check if template is official
        template_row = (
            template_service.supabase.table("pdf_templates")
            .select("is_official")
            .eq("id", template_id)
            .single()
            .execute()
        )

        if template_row.data and template_row.data.get("is_official"):
            raise HTTPException(
                status_code=403,
                detail="Official templates cannot be deleted by regular users"
            )

        success = template_service.delete_template(
                template_id=template_id,
                user_id=current_user['id']
            )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Template not found or unauthorized"
            )

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
