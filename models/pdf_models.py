"""
Pydantic models for PDF processing
Request/Response schemas for BulkForm API
"""
from pydantic import BaseModel
from typing import List, Optional


# ============================================================================
# GRID COORDINATE MODELS
# ============================================================================

class GridCoordinates(BaseModel):
    """Grid coordinate system for a single page"""
    page_number: int
    width: int
    height: int
    grid_size: int
    cell_width: float
    cell_height: float


class GridResponse(BaseModel):
    """Response containing grid coordinates for all pages"""
    total_pages: int
    pages: List[GridCoordinates]
    dpi: int
    session_id: str  # Session ID for subsequent operations
    success: bool = True

class EncryptedGridResponse(BaseModel):
    """Encrypted grid response for security"""
    encrypted_data: str  # Encrypted grid coordinates
    total_pages: int
    session_id: str
    dpi: int
    success: bool = True

# ============================================================================
# TEXT PLACEMENT MODELS
# ============================================================================

class TextItem(BaseModel):
    """Single text item to place on PDF"""
    x: int  # Grid X coordinate
    y: int  # Grid Y coordinate
    text: str
    size: int = 20
    align: str = "top"  # top, center, bottom
    font: Optional[str] = "arial"


class FillTextRequest(BaseModel):
    """Request to fill text on a PDF page"""
    page_number: int
    text_data: List[TextItem]


class FillTextResponse(BaseModel):
    """Response after filling text"""
    page_number: int
    items_added: int
    success: bool = True
    message: str = "Text added successfully"

class EncryptedFillTextRequest(BaseModel):
    """Encrypted text fill request"""
    session_id: str
    encrypted_data: str  # Encrypted JSON containing page_number and text_data

class FillTextRequest(BaseModel):
    """Fill text request"""
    page_number: int
    text_data: List[TextItem]


# ============================================================================
# IMAGE/SIGNATURE PLACEMENT MODELS
# ============================================================================

class ImageItem(BaseModel):
    """Single image/signature to place on PDF"""
    x: int  # Grid X coordinate
    y: int  # Grid Y coordinate
    image_path: str  # Local path to image file
    width: Optional[int] = None
    height: Optional[int] = None


class AddImageRequest(BaseModel):
    """Request to add images to a PDF page"""
    page_number: int
    image_data: List[ImageItem]


class AddImageResponse(BaseModel):
    """Response after adding images"""
    page_number: int
    images_added: int
    success: bool = True
    message: str = "Images added successfully"


# ============================================================================
# PDF GENERATION MODELS
# ============================================================================

class GeneratePDFResponse(BaseModel):
    """Response after generating PDF"""
    pdf_url: str  # Supabase Storage URL
    storage_path: str  # Path in bucket
    total_pages: int
    success: bool = True
    message: str = "PDF generated and uploaded successfully"


# ============================================================================
# SESSION MODELS
# ============================================================================

class SessionInfo(BaseModel):
    """PDF session information"""
    session_id: str
    filename: str
    num_pages: int
    status: str  # processing, completed, failed
    storage_path: Optional[str] = None
    created_at: str
    updated_at: str


class UserSessionsResponse(BaseModel):
    """Response with user's sessions"""
    user_id: str
    total_sessions: int
    sessions: List[SessionInfo]