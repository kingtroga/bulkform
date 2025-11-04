"""
Image Service
Handles image upload, storage, and retrieval
"""

from typing import Optional, Dict, Any, List
import uuid
from PIL import Image
import io
from services.supabase_client import get_supabase


class ImageService:
    """Service for managing user images (signatures, stamps, photos)"""
    
    def __init__(self):
        self.supabase = get_supabase()
        self.images_table = "user_images"
        self.storage_bucket = "images"
        self.allowed_types = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        print("✅ Image Service initialized")
    
    def upload_image(self, user_id: str, file_data: bytes, file_name: str, 
                    image_name: str, mime_type: str) -> Dict[str, Any]:
        """Upload image and return metadata"""
        if mime_type not in self.allowed_types:
            raise ValueError(f"Invalid image type: {mime_type}")
        
        image_id = str(uuid.uuid4())
        img = Image.open(io.BytesIO(file_data))
        width, height = img.size
        extension = self.allowed_types[mime_type]
        storage_path = f"{user_id}/images/{image_id}{extension}"
        
        self.supabase.storage.from_(self.storage_bucket).upload(
            path=storage_path, file=file_data,
            file_options={"content-type": mime_type, "upsert": "true"}
        )
        
        signed_url_response = self.supabase.storage.from_(self.storage_bucket).create_signed_url(
            storage_path, 3600
        )
        
        image_data = {
            "id": image_id, "user_id": user_id, "image_name": image_name,
            "file_name": file_name, "storage_path": storage_path,
            "file_size": len(file_data), "mime_type": mime_type,
            "width": width, "height": height
        }
        
        result = self.supabase.table(self.images_table).insert(image_data).execute()
        print(f"✅ Image uploaded: {image_name} ({image_id})")
        
        return {
            "image_id": image_data["id"],
            "image_name": image_data["image_name"],
            "file_name": image_data["file_name"],
            "storage_path": image_data["storage_path"],
            "storage_url": signed_url_response['signedURL'],
            "file_size": image_data["file_size"],
            "mime_type": image_data["mime_type"],
            "width": image_data["width"],
            "height": image_data["height"],
            "created_at": result.data[0]["created_at"]
        }
    
    def get_image(self, image_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get image by ID or name"""
        try:
            # Try to validate as UUID first
            uuid.UUID(image_id)
            # If valid UUID, search by ID
            result = self.supabase.table(self.images_table).select("*").eq(
                "id", image_id).eq("user_id", user_id).execute()
            
            if result.data:
                return result.data[0]
        except (ValueError, AttributeError):
            # Not a valid UUID, skip ID search
            pass
        
        # Search by name
        result = self.supabase.table(self.images_table).select("*").eq(
            "image_name", image_id).eq("user_id", user_id).execute()
        
        return result.data[0] if result.data else None
    
    def download_image_bytes(self, image_id: str, user_id: str) -> Optional[bytes]:
        """Download image bytes"""
        image = self.get_image(image_id, user_id)
        if not image:
            return None
        return self.supabase.storage.from_(self.storage_bucket).download(
            image["storage_path"]
        )
    
    def list_images(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List user's images"""
        result = self.supabase.table(self.images_table).select("*").eq(
            "user_id", user_id).order("created_at", desc=True).limit(limit).offset(offset).execute()
        return result.data if result.data else []
    
    def delete_image(self, image_id: str, user_id: str) -> bool:
        """Delete image"""
        image = self.get_image(image_id, user_id)
        if not image:
            return False
        
        self.supabase.storage.from_(self.storage_bucket).remove([image["storage_path"]])
        self.supabase.table(self.images_table).delete().eq("id", image["id"]).eq(
            "user_id", user_id).execute()
        print(f"✅ Image deleted: {image_id}")
        return True


def get_image_service() -> ImageService:
    """Get image service instance"""
    return ImageService()