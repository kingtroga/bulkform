"""
Portal Models
Pydantic schemas for public intake portals, submissions, and spreadsheet feeds.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
import uuid


def validate_slug_format(v: str) -> str:
    cleaned = v.strip().lower()
    if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', cleaned):
        raise ValueError("Slug must contain only lowercase alphanumeric characters and hyphens (e.g. 'aa-rescue-lagos-license')")
    return cleaned


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class PortalCreateRequest(BaseModel):
    """Schema for creating a public form portal linked to a template"""
    template_id: str = Field(..., description="UUID of template to use")
    name: str = Field(..., min_length=2, max_length=255, description="Display title for the portal")
    slug: str = Field(..., min_length=2, max_length=100, description="Unique URL slug")
    description: Optional[str] = Field(None, max_length=1000, description="Instructions or description for applicants")
    email_settings: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "send_applicant_email": False,
            "notify_owner": False,
            "owner_email": "",
            "subject": "Your Application Document"
        }
    )
    sheet_settings: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {
            "google_sheet_url": None,
            "webhook_url": None
        }
    )

    @validator('template_id')
    def validate_uuid(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError("template_id must be a valid UUID")

    @validator('slug')
    def validate_slug(cls, v):
        return validate_slug_format(v)


class PortalUpdateRequest(BaseModel):
    """Schema for updating an existing portal"""
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None
    email_settings: Optional[Dict[str, Any]] = None
    sheet_settings: Optional[Dict[str, Any]] = None


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class PublicPortalResponse(BaseModel):
    """Public portal metadata sent to anonymous applicants"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    template_id: str
    field_mappings: Dict[str, Any]
    field_order: List[str]
    has_image_fields: bool = False
    image_fields: List[str] = []


class PortalResponse(BaseModel):
    """Authenticated owner response with full portal configuration"""
    id: str
    user_id: str
    template_id: str
    template_name: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    is_active: bool
    email_settings: Dict[str, Any]
    sheet_settings: Dict[str, Any]
    access_token: str
    total_submissions: int = 0
    live_feed_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PortalListResponse(BaseModel):
    """List of portals owned by user"""
    portals: List[PortalResponse]
    total: int


class PublicSubmissionResponse(BaseModel):
    """Response returned to applicant upon successful form submission"""
    status: str = "success"
    message: str = "Your form has been processed successfully."
    submission_id: str
    pdf_url: str
    download_url: Optional[str] = None
    created_at: str


class SubmissionListItem(BaseModel):
    """Item representing one applicant submission"""
    id: str
    portal_id: str
    applicant_name: Optional[str] = None
    applicant_email: Optional[str] = None
    submitted_data: Dict[str, Any]
    pdf_url: str
    created_at: str


class SubmissionListResponse(BaseModel):
    """List of submissions for a portal"""
    portal_id: str
    submissions: List[SubmissionListItem]
    total: int
