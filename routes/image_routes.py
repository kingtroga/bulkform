"""
Image Routes
API endpoints for image upload and management
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from models.image_models import (
    ImageUploadResponse, ImageResponse, ImageListResponse,
    ImageDeletedResponse, ImageDownloadResponse
)
from services.image_service import get_image_service
from services.auth import get_current_user

router = APIRouter(prefix="/api/images", tags=["Images"])
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/upload", response_model=ImageUploadResponse, status_code=201)
async def upload_image(
    image_name: str = Form(...), file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload image - returns image_id for use in CSV"""
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    file_data = await file.read()
    if len(file_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail=f"Max size: 5MB")
    
    service = get_image_service()
    result = service.upload_image(current_user['id'], file_data, file.filename,
                                   image_name, file.content_type)
    return ImageUploadResponse(**result)


@router.get("", response_model=ImageListResponse)
async def list_images(
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """List user's images"""
    service = get_image_service()
    images = service.list_images(current_user['id'], limit, offset)
    return ImageListResponse(images=[ImageResponse(**img) for img in images], total=len(images))


@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(image_id: str, current_user: dict = Depends(get_current_user)):
    """Get image by ID or name"""
    service = get_image_service()
    image = service.get_image(image_id, current_user['id'])
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return ImageResponse(**image)


@router.delete("/{image_id}", response_model=ImageDeletedResponse)
async def delete_image(image_id: str, current_user: dict = Depends(get_current_user)):
    """Delete image"""
    service = get_image_service()
    if not service.delete_image(image_id, current_user['id']):
        raise HTTPException(status_code=404, detail="Image not found")
    return ImageDeletedResponse(message="Image deleted successfully", image_id=image_id)