"""
Presets Routes
API endpoints for managing saved form data presets

Presets allow users to save frequently-used form data for quick reuse.
Example use cases:
- "My Personal Info" (name, address, DOB)
- "Company Details 2024" (business info)
- "Jane - T4 Data" (annual tax form data)

Limits:
- Free tier: 5 presets
- Paid tier (Starter/Pro): 100 presets

Endpoints:
- POST   /api/presets              - Create preset
- GET    /api/presets              - List user's presets
- GET    /api/presets/{id}         - Get specific preset
- PUT    /api/presets/{id}         - Update preset
- DELETE /api/presets/{id}         - Delete preset
- GET    /api/presets/stats        - User's preset statistics
- GET    /api/presets/health       - Health check
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from models.preset_models import (
    CreatePresetRequest,
    UpdatePresetRequest,
    PresetResponse,
    PresetListResponse,
    PresetCreatedResponse,
    PresetDeletedResponse,
)
from services.preset_service import get_preset_service
from services.auth import get_current_user
from services.supabase_client import get_supabase

router = APIRouter(prefix="/api/presets", tags=["Presets"])

preset_service = get_preset_service()
supabase = get_supabase()


# ============================================================================
# HELPER: GET USER'S SUBSCRIPTION TIER
# ============================================================================

def get_user_subscription_tier(user_id: str) -> str:
    """Get user's subscription tier from profiles table"""
    try:
        result = supabase.table("profiles").select("subscription_tier").eq(
            "id", user_id
        ).single().execute()
        
        if result.data:
            return result.data.get("subscription_tier", "free")
        return "free"
    except Exception:
        return "free"

# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def preset_health():
    """Health check for preset service"""
    return {
        "service": "Presets",
        "status": "operational",
        "limits": {
            "free_tier": 5,
            "paid_tier": 100
        },
        "features": {
            "create": True,
            "list": True,
            "update": True,
            "delete": True,
            "soft_delete": True,
            "template_association": True
        }
    }

# ============================================================================
# CREATE PRESET
# ============================================================================

@router.post("", response_model=PresetCreatedResponse, status_code=201)
async def create_preset(
    request: CreatePresetRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create new preset
    
    🔒 Requires authentication
    
    **Limits:**
    - Free tier: 5 presets max
    - Paid tier (Starter/Pro): 100 presets max
    
    **Request body:**
    ```json
    {
        "name": "My Personal Info",
        "description": "Personal details for tax forms",
        "data": {
            "first_name": "John",
            "last_name": "Doe",
            "address": "123 Main St",
            "city": "Toronto"
        },
        "template_id": "optional-template-uuid"
    }
    ```
    
    Returns the created preset ID
    """
    try:
        user_id = current_user['id']
        
        # Check subscription tier
        subscription_tier = get_user_subscription_tier(user_id)
        
        # Check if user has hit their limit
        if not preset_service.check_preset_limit(user_id, subscription_tier):
            limit = 100 if subscription_tier in ["starter", "pro"] else 5
            raise HTTPException(
                status_code=403,
                detail=f"Preset limit reached. {'Free users' if subscription_tier == 'free' else 'Your plan'} can create up to {limit} presets. Please delete unused presets or upgrade your plan."
            )
        
        # Validate template_id if provided
        if request.template_id:
            try:
                import uuid
                uuid.UUID(request.template_id)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="template_id must be a valid UUID"
                )
        
        # Validate data is not empty
        if not request.data or len(request.data) == 0:
            raise HTTPException(
                status_code=400,
                detail="Preset data cannot be empty"
            )
        
        # Create preset
        preset_id = preset_service.create_preset(
            user_id=user_id,
            name=request.name,
            data=request.data,
            description=request.description,
            template_id=request.template_id
        )
        
        return PresetCreatedResponse(
            preset_id=preset_id,
            message="Preset created successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to create preset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create preset: {str(e)}"
        )


# ============================================================================
# LIST PRESETS
# ============================================================================

@router.get("", response_model=PresetListResponse)
async def list_presets(
    template_id: Optional[str] = Query(
        None,
        description="Filter by template ID"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Max presets to return"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number to skip"
    ),
    current_user: dict = Depends(get_current_user)
):
    """
    List user's presets (paginated)
    
    🔒 Requires authentication
    
    **Query Parameters:**
    - **template_id**: Optional UUID to filter by specific template
    - **limit**: Number of presets to return (default: 100, max: 500)
    - **offset**: Number to skip for pagination (default: 0)
    
    Returns presets sorted by creation date (newest first)
    """
    try:
        presets = preset_service.list_presets(
            user_id=current_user['id'],
            template_id=template_id,
            limit=limit,
            offset=offset
        )
        
        preset_responses = [PresetResponse(**preset) for preset in presets]
        
        return PresetListResponse(
            presets=preset_responses,
            total=len(preset_responses)
        )
    
    except Exception as e:
        print(f"❌ Failed to list presets: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list presets: {str(e)}"
        )


# ============================================================================
# GET PRESET
# ============================================================================

@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get specific preset by ID
    
    🔒 Requires authentication
    
    Returns preset if it belongs to current user
    """
    try:
        preset = preset_service.get_preset(preset_id, current_user['id'])
        
        if not preset:
            raise HTTPException(
                status_code=404,
                detail="Preset not found or unauthorized"
            )
        
        return PresetResponse(**preset)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get preset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get preset: {str(e)}"
        )


# ============================================================================
# UPDATE PRESET
# ============================================================================

@router.put("/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: str,
    request: UpdatePresetRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update existing preset (partial update)
    
    🔒 Requires authentication
    
    **What can be updated:**
    - name
    - description
    - data (replaces existing data)
    - template_id
    
    **Request body (all fields optional):**
    ```json
    {
        "name": "Updated Name",
        "description": "Updated description",
        "data": {
            "first_name": "Jane",
            "last_name": "Smith"
        }
    }
    ```
    
    Only provided fields will be updated
    """
    try:
        # Check if preset exists and belongs to user
        existing = preset_service.get_preset(preset_id, current_user['id'])
        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Preset not found or unauthorized"
            )
        
        # Build updates dict
        updates = {}
        
        if request.name is not None:
            updates["name"] = request.name
        
        if request.description is not None:
            updates["description"] = request.description
        
        if request.data is not None:
            if len(request.data) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Preset data cannot be empty"
                )
            updates["data"] = request.data
        
        if request.template_id is not None:
            # Validate UUID
            try:
                import uuid
                uuid.UUID(request.template_id)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="template_id must be a valid UUID"
                )
            updates["template_id"] = request.template_id
        
        if not updates:
            raise HTTPException(
                status_code=400,
                detail="No fields to update"
            )
        
        # Update preset
        success = preset_service.update_preset(
            preset_id=preset_id,
            user_id=current_user['id'],
            updates=updates
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Preset not found or unauthorized"
            )
        
        # Return updated preset
        updated = preset_service.get_preset(preset_id, current_user['id'])
        return PresetResponse(**updated)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to update preset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update preset: {str(e)}"
        )


# ============================================================================
# DELETE PRESET
# ============================================================================

@router.delete("/{preset_id}", response_model=PresetDeletedResponse)
async def delete_preset(
    preset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete preset (soft delete)
    
    🔒 Requires authentication
    
    Preset is marked as inactive, not permanently deleted.
    This allows for potential recovery if needed.
    """
    try:
        success = preset_service.delete_preset(preset_id, current_user['id'])
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Preset not found or unauthorized"
            )
        
        return PresetDeletedResponse(
            message="Preset deleted successfully",
            preset_id=preset_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to delete preset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete preset: {str(e)}"
        )


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats/summary")
async def get_preset_stats(current_user: dict = Depends(get_current_user)):
    """
    Get user's preset statistics
    
    🔒 Requires authentication
    
    Returns:
    - Total presets created
    - Subscription tier
    - Preset limit
    - Remaining slots
    """
    try:
        user_id = current_user['id']
        subscription_tier = get_user_subscription_tier(user_id)
        
        total_presets = preset_service.count_user_presets(user_id)
        
        limit = 100 if subscription_tier in ["starter", "pro"] else 5
        remaining = max(0, limit - total_presets)
        
        return {
            "user_id": user_id,
            "subscription_tier": subscription_tier,
            "total_presets": total_presets,
            "preset_limit": limit,
            "remaining_slots": remaining,
            "at_limit": total_presets >= limit
        }
    
    except Exception as e:
        print(f"❌ Failed to get preset stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get preset stats: {str(e)}"
        )


