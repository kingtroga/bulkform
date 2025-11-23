"""
Preset Models
Pydantic models for preset requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class CreatePresetRequest(BaseModel):
    """Request model for creating a preset"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Preset name"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of what this preset contains"
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Form field data (key-value pairs)"
    )
    template_id: Optional[str] = Field(
        None,
        description="Optional UUID of associated template"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My Personal Info",
                "description": "Personal details for tax forms",
                "data": {
                    "first_name": "John",
                    "last_name": "Doe",
                    "address": "123 Main St",
                    "city": "Toronto",
                    "postal_code": "M5H 2N2"
                },
                "template_id": "41eb78c1-23a2-4f6d-8aed-0ca8d5cfe410"
            }
        }
    }


class UpdatePresetRequest(BaseModel):
    """Request model for updating a preset (partial update)"""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Updated preset name"
    )
    description: Optional[str] = Field(
        None,
        description="Updated description"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Updated form field data (replaces existing)"
    )
    template_id: Optional[str] = Field(
        None,
        description="Updated template ID association"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Updated Personal Info",
                "data": {
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "city": "Vancouver"
                }
            }
        }
    }


class PresetResponse(BaseModel):
    """Response model for a single preset"""
    id: str = Field(..., description="Preset UUID")
    user_id: str = Field(..., description="Owner's user ID")
    name: str = Field(..., description="Preset name")
    description: Optional[str] = Field(None, description="Preset description")
    data: Dict[str, Any] = Field(..., description="Form field data")
    template_id: Optional[str] = Field(None, description="Associated template ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "a6c3a93a-b1a4-4592-ac53-dba3cf88ae20",
                "name": "My Personal Info",
                "description": "Personal details for tax forms",
                "data": {
                    "first_name": "John",
                    "last_name": "Doe",
                    "address": "123 Main St",
                    "city": "Toronto"
                },
                "template_id": "41eb78c1-23a2-4f6d-8aed-0ca8d5cfe410",
                "created_at": "2025-11-23T10:00:00Z",
                "updated_at": "2025-11-23T10:00:00Z"
            }
        }
    }


class PresetListResponse(BaseModel):
    """Response model for list of presets"""
    presets: list[PresetResponse] = Field(..., description="List of presets")
    total: int = Field(..., description="Total number of presets returned")

    model_config = {
        "json_schema_extra": {
            "example": {
                "presets": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "user_id": "a6c3a93a-b1a4-4592-ac53-dba3cf88ae20",
                        "name": "My Personal Info",
                        "description": "Personal details",
                        "data": {"first_name": "John", "last_name": "Doe"},
                        "template_id": None,
                        "created_at": "2025-11-23T10:00:00Z",
                        "updated_at": "2025-11-23T10:00:00Z"
                    }
                ],
                "total": 1
            }
        }
    }


class PresetCreatedResponse(BaseModel):
    """Response after successfully creating a preset"""
    preset_id: str = Field(..., description="Created preset UUID")
    message: str = Field(..., description="Success message")

    model_config = {
        "json_schema_extra": {
            "example": {
                "preset_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "Preset created successfully"
            }
        }
    }


class PresetDeletedResponse(BaseModel):
    """Response after successfully deleting a preset"""
    message: str = Field(..., description="Success message")
    preset_id: str = Field(..., description="Deleted preset UUID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Preset deleted successfully",
                "preset_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }