"""
Batch Processing Models
Pydantic models for batch PDF generation API
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================================
# REQUEST MODELS
# ============================================================================

class CreateBatchRequest(BaseModel):
    """Request to create batch from JSON data"""
    template_id: str = Field(..., description="UUID of template to use")
    batch_name: str = Field(..., min_length=1, max_length=200, description="Name for this batch")
    items: List[Dict[str, Any]] = Field(..., min_items=1, max_items=1000, description="Client data (max 1000 items)")
    
    @validator('template_id')
    def validate_uuid(cls, v):
        """Validate template_id is a valid UUID"""
        import uuid
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError("template_id must be a valid UUID")
    
    class Config:
        schema_extra = {
            "example": {
                "template_id": "123e4567-e89b-12d3-a456-426614174000",
                "batch_name": "October 2025 Green Cards",
                "items": [
                    {"first_name": "John", "last_name": "Smith"},
                    {"first_name": "Jane", "last_name": "Doe"}
                ]
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class BatchCreatedResponse(BaseModel):
    """Response after batch creation"""
    batch_id: str = Field(..., description="UUID of created batch")
    batch_name: str = Field(..., description="Name of batch")
    total_items: int = Field(..., description="Number of items in batch")
    status: str = Field(..., description="Initial status (pending)")
    options: Dict = {}
    message: str = Field(..., description="Success message with next steps")
    
    class Config:
        schema_extra = {
            "example": {
                "batch_id": "abc-123-def-456",
                "batch_name": "October 2025 Green Cards",
                "total_items": 50,
                "status": "pending",
                "message": "Batch created with 50 items. Use POST /batch/abc-123-def-456/process to start."
            }
        }


class BatchResponse(BaseModel):
    """Single batch details"""
    id: str
    user_id: str
    template_id: str
    batch_name: str
    total_items: int
    completed: int
    failed: int
    status: str
    download_url: Optional[str] = None
    error_log: Optional[List[Dict]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "id": "abc-123",
                "user_id": "user-456",
                "template_id": "template-789",
                "batch_name": "October Green Cards",
                "total_items": 50,
                "completed": 45,
                "failed": 2,
                "status": "processing",
                "download_url": None,
                "error_log": None,
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:15:00Z"
            }
        }


class BatchListResponse(BaseModel):
    """List of batches"""
    batches: List[BatchResponse]
    total: int
    
    class Config:
        schema_extra = {
            "example": {
                "batches": [],
                "total": 5
            }
        }


class BatchProgressResponse(BaseModel):
    """Batch processing progress"""
    batch_id: str
    batch_name: str
    total: int
    completed: int
    failed: int
    pending: int
    status: str
    progress_percentage: float
    estimated_time_remaining: str
    download_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "batch_id": "abc-123",
                "batch_name": "October Green Cards",
                "total": 50,
                "completed": 45,
                "failed": 2,
                "pending": 3,
                "status": "processing",
                "progress_percentage": 94.0,
                "estimated_time_remaining": "2 minutes",
                "download_url": None,
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:15:00Z"
            }
        }


class ProcessBatchResponse(BaseModel):
    """Response when starting batch processing"""
    message: str
    batch_id: str
    total_items: int
    status: str
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Batch processing started",
                "batch_id": "abc-123",
                "total_items": 50,
                "status": "processing"
            }
        }


class BatchItemResponse(BaseModel):
    """Single batch item details"""
    id: str
    batch_id: str
    item_index: int
    client_data: Dict[str, Any]
    status: str
    pdf_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        schema_extra = {
            "example": {
                "id": "item-123",
                "batch_id": "batch-456",
                "item_index": 0,
                "client_data": {"first_name": "John", "last_name": "Smith"},
                "status": "completed",
                "pdf_url": "https://storage.example.com/user/batch/output.pdf",
                "error_message": None,
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:05:00Z"
            }
        }


class PDFUrlInfo(BaseModel):
    """Single PDF download info"""
    item_index: int
    url: str
    client_data: Dict[str, Any]
    
    class Config:
        schema_extra = {
            "example": {
                "item_index": 0,
                "url": "https://storage.example.com/user/batch/output.pdf",
                "client_data": {"first_name": "John", "last_name": "Smith"}
            }
        }


class BatchDownloadResponse(BaseModel):
    """Batch download URLs"""
    batch_id: str
    batch_name: str
    total_pdfs: int
    completed: int
    failed: int
    pdf_urls: List[PDFUrlInfo]
    zip_available: bool = False
    zip_url: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "batch_id": "abc-123",
                "batch_name": "October Green Cards",
                "total_pdfs": 50,
                "completed": 48,
                "failed": 2,
                "pdf_urls": [
                    {
                        "item_index": 0,
                        "url": "https://storage.example.com/...",
                        "client_data": {"first_name": "John"}
                    }
                ],
                "zip_available": False,
                "zip_url": None
            }
        }


class BatchDeletedResponse(BaseModel):
    """Response after deleting batch"""
    message: str
    batch_id: str
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Batch deleted successfully",
                "batch_id": "abc-123"
            }
        }


# ============================================================================
# INTERNAL MODELS (for type hints)
# ============================================================================

class BatchJobInternal(BaseModel):
    """Internal representation of batch job"""
    id: str
    user_id: str
    template_id: str
    batch_name: str
    total_items: int
    completed: int = 0
    failed: int = 0
    status: str = "pending"
    download_url: Optional[str] = None
    error_log: Optional[List[Dict]] = None
    
    class Config:
        orm_mode = True


class BatchItemInternal(BaseModel):
    """Internal representation of batch item"""
    id: str
    batch_id: str
    item_index: int
    client_data: Dict[str, Any]
    status: str = "pending"
    pdf_url: Optional[str] = None
    error_message: Optional[str] = None
    
    class Config:
        orm_mode = True

class SingleFillRequest(BaseModel):
    """Single-fill using the batch pipeline with exactly one item"""
    template_id: str = Field(..., description="UUID of template to use")
    batch_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Optional name for this single-fill batch"
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Single client data row (same as one item in batch.items)"
    )
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Batch-level options (default_font, default_size, image defaults, etc.)"
    )

    class Config:
        schema_extra = {
            "example": {
                "template_id": "8089713c-1115-4dab-bf01-c652b2f8d7ad",
                "batch_name": "Single Fill - Test1",
                "data": {
                    "field_1": "John Doe",
                    "field_2": "123 Main Street",
                    "field_3": "Houston, TX 77001",
                    "field_4": "2025-11-21"
                },
                "options": {
                    "default_font": "arial",
                    "default_size": 30,
                    "default_align": "center"
                }
            }
        }
