"""
Template Models
Pydantic models for template API requests/responses
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime


# ============================================================================
# REQUEST MODELS
# ============================================================================

class TemplateConversionRequest(BaseModel):
    fields: Dict[str, list]

class CreateTemplateRequest(BaseModel):
    """Request to create a new custom template (multipart form data)"""
    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    description: Optional[str] = Field(None, max_length=1000, description="Template description")
    field_mappings: str = Field(..., description="JSON string of field mappings")
    template_kind: Literal["standard", "repeated"] = Field(
        default="standard",
        description="Template kind: standard or repeated"
    )
    repeat_config: Optional[str] = Field(
        default=None,
        description="JSON string repeat config (only for repeated templates)"
    )
    @model_validator(mode="after")
    def _validate_repeat_config(self):
        if self.template_kind != "repeated":
            # keep it clean; routes/services can ignore too
            self.repeat_config = None
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "My Repeated I-485",
                "description": "Repeating employment history pages",
                "field_mappings": "{\"employer_name\": {\"page\": 1, \"x\": 25, \"y\": 30}}",
                "template_kind": "repeated",
                "repeat_config": "{\"mode\":\"pages\",\"base_page\":1,\"repeat_pages\":[1,2,3]}"
            }
        }


class UpdateTemplateRequest(BaseModel):
    """Request to update existing template"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    pdf_url: Optional[str] = None
    category: Optional[str] = Field(None, max_length=255)
    field_mappings: Optional[Dict[str, Any]] = None
    remove_fields: Optional[List[str]] = None

    template_kind: Optional[Literal["standard", "repeated"]] = None
    repeat_config: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_repeat_config(self):
        # if someone explicitly sets template_kind to standard, wipe repeat_config
        if self.template_kind and self.template_kind != "repeated":
            self.repeat_config = None
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Repeated Template",
                "template_kind": "repeated",
                "repeat_config": {
                    "mode": "pages",
                    "base_page": 2,
                    "repeat_pages": [2, 3, 4]
                }
            }
        }



class CreateOfficialTemplateRequest(BaseModel):
    """Request to create official template (admin only)"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    pdf_url: str = Field(...)
    field_mappings: Dict[str, Any] = Field(...)
    official_form_id: str = Field(..., min_length=1, max_length=50, description="Form ID (e.g., 'i-485')")
    category: str = Field(default="immigration", description="Template category")
    price: float = Field(default=0.00, ge=0, description="Price in dollars")
    template_kind: Literal["standard", "repeated"] = Field(default="standard")
    repeat_config: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_repeat_config(self):
        if self.template_kind != "repeated":
            self.repeat_config = None
        return self
    
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "USCIS I-485 Employment History",
                "description": "Official repeated section for employment history",
                "pdf_url": "https://uscis.gov/i-485.pdf",
                "field_mappings": {
                    "employer_name": {"page": 1, "x": 25, "y": 30}
                },
                "official_form_id": "i-485-employment",
                "category": "immigration",
                "price": 0.00,
                "template_kind": "repeated",
                "repeat_config": {
                    "mode": "pages",
                    "base_page": 1,
                    "repeat_pages": [1, 2, 3]
                }
            }
        }



# ============================================================================
# RESPONSE MODELS
# ============================================================================

class TemplateResponse(BaseModel):
    """Single template response"""
    id: str
    user_id: str
    name: str
    description: Optional[str]
    pdf_url: str
    field_mappings: Dict[str, Any]
    field_order: Optional[List[str]] = None
    template_kind: Literal["standard", "repeated"] = "standard"
    repeat_config: Optional[Dict[str, Any]] = None
    is_official: bool = False
    official_form_id: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    downloads: Optional[int] = None
    rating: Optional[float] = None
    created_at: str
    updated_at: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc-123-def-456",
                "user_id": "user-789",
                "name": "Repeated Employment History",
                "description": "Repeats same fields across multiple pages",
                "pdf_url": "https://uscis.gov/i-485.pdf",
                "field_mappings": {
                    "employer_name": {"page": 1, "x": 25, "y": 30}
                },
                "field_order": ["employer_name"],
                "template_kind": "repeated",
                "repeat_config": {
                    "mode": "pages",
                    "base_page": 1,
                    "repeat_pages": [1, 2, 3]
                },
                "is_official": False,
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:00:00Z"
            }
        }



class TemplateListResponse(BaseModel):
    """List of templates response"""
    templates: List[TemplateResponse]
    total: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "templates": [
                    {
                        "id": "abc-123",
                        "name": "I-485 Template",
                        "is_official": True,
                        "category": "immigration"
                    }
                ],
                "total": 1
            }
        }


class AllTemplatesResponse(BaseModel):
    # data
    official: List[TemplateResponse]
    custom: List[TemplateResponse]

    # totals
    total_official: int = Field(..., description="Total active official templates")
    total_custom: int = Field(..., description="Total active custom templates for the user")

    # official paging meta
    page_official: int
    page_size_official: int
    total_pages_official: int
    has_prev_official: bool
    has_next_official: bool

    # custom paging meta
    page_custom: int
    page_size_custom: int
    total_pages_custom: int
    has_prev_custom: bool
    has_next_custom: bool

    class Config:
        json_schema_extra = {
            "example": {
                "official": [],
                "custom": [],
                "total_official": 120,
                "total_custom": 37,
                "page_official": 1,
                "page_size_official": 24,
                "total_pages_official": 5,
                "has_prev_official": False,
                "has_next_official": True,
                "page_custom": 1,
                "page_size_custom": 24,
                "total_pages_custom": 2,
                "has_prev_custom": False,
                "has_next_custom": True,
            }
        }


class TemplateCategoryResponse(BaseModel):
    """Template category with count"""
    category: str
    count: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "category": "immigration",
                "count": 15
            }
        }


class TemplateCreatedResponse(BaseModel):
    """Response after creating template"""
    template_id: str
    message: str
    stripe_price_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "abc-123-def-456",
                "message": "Template created successfully"
            }
        }


class TemplateDeletedResponse(BaseModel):
    """Response after deleting template"""
    message: str
    template_id: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Template deleted successfully",
                "template_id": "abc-123"
            }
        }


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Template not found",
                "detail": "Template with ID abc-123 does not exist"
            }
        }