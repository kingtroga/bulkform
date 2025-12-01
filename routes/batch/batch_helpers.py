"""
Batch Helpers - Utility Functions and Constants
Configuration, validation, and helper functions for batch processing
"""

from fastapi import HTTPException, UploadFile
from pathlib import Path
from typing import Dict

from services.batch_service import get_batch_service
from services.csv_processor import get_csv_processor
from services.template_service import get_template_service


# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

MAX_BATCH_SIZE = 1000  # Maximum items per batch
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file size
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls', '.tsv'}


# ============================================================================
# SERVICE HELPERS
# ============================================================================

def get_services() -> Dict:
    """Get service instances (lazy initialization)"""
    return {
        'batch': get_batch_service(),
        'csv': get_csv_processor(),
        'template': get_template_service()
    }


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_file_upload(file: UploadFile) -> str:
    """
    Validate uploaded file
    
    Returns:
        File extension if valid
        
    Raises:
        HTTPException if invalid
    """
    filename = file.filename.lower()
    ext = Path(filename).suffix
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Check file size (if available)
    if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    return ext


def validate_batch_size(items: list) -> None:
    """
    Validate batch size
    
    Raises:
        HTTPException if too large
    """
    if len(items) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch too large. Maximum {MAX_BATCH_SIZE} items allowed. You have {len(items)} items."
        )
    
    if len(items) == 0:
        raise HTTPException(
            status_code=400,
            detail="Batch cannot be empty"
        )


# ============================================================================
# FILENAME HELPERS
# ============================================================================

def clean_filename(text: str) -> str:
    """Clean text for use in filename"""
    if not text:
        return ""

    # Remove or replace special characters
    cleaned = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in str(text))

    # Replace spaces with underscores
    cleaned = cleaned.replace(' ', '_')

    # Collapse multiple underscores into one
    cleaned = '_'.join(filter(None, cleaned.split('_')))

    # Trim excessively long names
    return cleaned[:50] if cleaned else ""


def generate_pdf_filename(client_data: Dict, item_index: int) -> str:
    """Generate friendly filename from client data"""
    # Try different name combinations
    if 'last_name' in client_data and 'first_name' in client_data:
        last = clean_filename(str(client_data['last_name']))
        first = clean_filename(str(client_data['first_name']))
        if last and first:
            return f"{last}_{first}.pdf"
    
    if 'full_name' in client_data:
        name = clean_filename(str(client_data['full_name']))
        if name:
            return f"{name}.pdf"
    
    if 'name' in client_data:
        name = clean_filename(str(client_data['name']))
        if name:
            return f"{name}.pdf"
    
    # Fallback to index-based name
    return f"document_{item_index + 1}.pdf"