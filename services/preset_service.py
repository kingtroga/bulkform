"""
Preset Service
Business logic for managing form data presets
"""

from typing import Optional, Dict, Any, List
from services.supabase_client import get_supabase

# Preset limits by subscription tier
MAX_PRESETS_FREE = 5
MAX_PRESETS_PAID = 100


class PresetService:
    """Service for managing user presets"""
    
    def __init__(self):
        self.supabase = get_supabase()
    
    def count_user_presets(self, user_id: str) -> int:
        """
        Count active presets for a user
        
        Args:
            user_id: User UUID
            
        Returns:
            Number of active presets
        """
        try:
            result = (
                self.supabase.table("presets")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("active", True)
                .execute()
            )
            return result.count if result.count else 0
        except Exception as e:
            print(f"❌ Error counting presets: {str(e)}")
            return 0
    
    def check_preset_limit(
        self,
        user_id: str,
        subscription_tier: str = "free"
    ) -> bool:
        """
        Check if user can create more presets
        
        Args:
            user_id: User UUID
            subscription_tier: 'free', 'starter', or 'pro'
            
        Returns:
            True if user can create more presets, False if at limit
        """
        count = self.count_user_presets(user_id)
        
        if subscription_tier in ["starter", "pro"]:
            limit = MAX_PRESETS_PAID
        else:
            limit = MAX_PRESETS_FREE
        
        return count < limit
    
    def create_preset(
        self,
        user_id: str,
        name: str,
        data: Dict[str, Any],
        description: Optional[str] = None,
        template_id: Optional[str] = None
    ) -> str:
        """
        Create a new preset
        
        Args:
            user_id: User UUID
            name: Preset name
            data: Form field data (key-value pairs)
            description: Optional description
            template_id: Optional template UUID association
            
        Returns:
            Created preset UUID
        """
        preset = {
            "user_id": user_id,
            "name": name,
            "description": description,
            "data": data,
            "template_id": template_id,
            "active": True
        }
        
        result = self.supabase.table("presets").insert(preset).execute()
        return result.data[0]["id"]
    
    def list_presets(
        self,
        user_id: str,
        template_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List user's active presets
        
        Args:
            user_id: User UUID
            template_id: Optional filter by template
            limit: Max results
            offset: Skip N results
            
        Returns:
            List of preset dicts (newest first)
        """
        query = (
            self.supabase.table("presets")
            .select("*")
            .eq("user_id", user_id)
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(limit)
            .offset(offset)
        )
        
        if template_id:
            query = query.eq("template_id", template_id)
        
        result = query.execute()
        return result.data if result.data else []
    
    def get_preset(
        self,
        preset_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific preset by ID
        
        Args:
            preset_id: Preset UUID
            user_id: User UUID (for authorization)
            
        Returns:
            Preset dict or None if not found/unauthorized
        """
        try:
            result = (
                self.supabase.table("presets")
                .select("*")
                .eq("id", preset_id)
                .eq("user_id", user_id)
                .eq("active", True)
                .single()
                .execute()
            )
            
            return result.data if result.data else None
        except Exception as e:
            print(f"❌ Error getting preset: {str(e)}")
            return None
    
    def update_preset(
        self,
        preset_id: str,
        user_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update a preset
        
        Args:
            preset_id: Preset UUID
            user_id: User UUID (for authorization)
            updates: Dict of fields to update
            
        Returns:
            True if updated, False if not found/unauthorized
        """
        # Always update the updated_at timestamp
        updates["updated_at"] = "NOW()"
        
        result = (
            self.supabase.table("presets")
            .update(updates)
            .eq("id", preset_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        return len(result.data) > 0 if result.data else False
    
    def delete_preset(
        self,
        preset_id: str,
        user_id: str
    ) -> bool:
        """
        Soft delete a preset (mark as inactive)
        
        Args:
            preset_id: Preset UUID
            user_id: User UUID (for authorization)
            
        Returns:
            True if deleted, False if not found/unauthorized
        """
        result = (
            self.supabase.table("presets")
            .update({"active": False, "updated_at": "NOW()"})
            .eq("id", preset_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        return len(result.data) > 0 if result.data else False


# Singleton instance
_preset_service: Optional[PresetService] = None


def get_preset_service() -> PresetService:
    """Get or create PresetService singleton"""
    global _preset_service
    if _preset_service is None:
        _preset_service = PresetService()
    return _preset_service