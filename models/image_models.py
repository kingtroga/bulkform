"""
Image Models
Pydantic models for image upload and management
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ImageUploadResponse(BaseModel):
    """Response after image upload"""
    image_id: str = Field(..., description="UUID of uploaded image")
    image_name: str = Field(..., description="User-friendly name")
    file_name: str = Field(..., description="Original filename")
    storage_path: str = Field(..., description="Path in storage")
    storage_url: str = Field(..., description="Signed URL (expires in 1 hour)")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="Image MIME type")
    width: Optional[int] = Field(None, description="Image width in pixels")
    height: Optional[int] = Field(None, description="Image height in pixels")
    created_at: datetime


class ImageResponse(BaseModel):
    """Single image details"""
    id: str
    user_id: str
    image_name: str
    file_name: str
    storage_path: str
    file_size: int
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ImageListResponse(BaseModel):
    """List of images"""
    images: List[ImageResponse]
    total: int


class ImageDeletedResponse(BaseModel):
    """Response after deleting image"""
    message: str
    image_id: str


class ImageDownloadResponse(BaseModel):
    """Image download URL"""
    image_id: str
    image_name: str
    storage_url: str = Field(..., description="Signed URL valid for 1 hour")
    expires_in: int = Field(default=3600, description="Seconds until URL expires")