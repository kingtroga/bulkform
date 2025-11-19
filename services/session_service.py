"""
Session Service - Database-backed PDF session management
Survives server restarts! 🔥
"""
from services.supabase_client import get_supabase
from typing import Dict, Optional, List
from datetime import datetime

from services.session_cache import (
    cache_user_sessions,
    cache_session_count,
    invalidate_user_sessions,
)


class SessionService:
    """Manages PDF processing sessions in Supabase database"""
    
    def __init__(self):
        self.supabase = get_supabase()
    
    def create_session(
        self, 
        session_id: str, 
        user_id: str, 
        filename: str, 
        num_pages: int
    ) -> Dict:
        """
        Create a new PDF session in database
        
        Args:
            session_id: Unique session identifier
            user_id: User who owns this session
            filename: Original PDF filename
            num_pages: Number of pages in PDF
            
        Returns:
            Session data from database
        """
        result = self.supabase.table("pdf_sessions").insert({
            "session_id": session_id,
            "user_id": user_id,
            "filename": filename,
            "num_pages": num_pages,
            "status": "processing"
        }).execute()

        data = result.data[0] if result.data else None

        if data:
            invalidate_user_sessions(user_id)
        
        return data
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get active session by session_id"""
        try:
            result = self.supabase.table("pdf_sessions").select("*").eq(
                "session_id", session_id
            ).eq("is_active", True).single().execute()
            
            return result.data if result.data else None
        except Exception:
            return None
    
    def verify_session_ownership(self, session_id: str, user_id: str) -> bool:
        """Check if user owns this session"""
        session = self.get_session(session_id)
        return session and session["user_id"] == user_id
    
    def update_session_status(
        self, 
        session_id: str, 
        status: str,
        storage_path: Optional[str] = None
    ) -> Dict:
        """
        Update session status and storage path
        
        Args:
            session_id: Session to update
            status: New status (processing, completed, failed)
            storage_path: Path in Supabase storage (optional)
        """
        update_data = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        if storage_path:
            update_data["storage_path"] = storage_path
        
        result = self.supabase.table("pdf_sessions").update(
            update_data
        ).eq("session_id", session_id).execute()
        
        return result.data[0] if result.data else None
    
    @cache_user_sessions(ttl=300)
    def get_user_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get all active sessions for a user (newest first)"""
        result = self.supabase.table("pdf_sessions").select("*").eq(
            "user_id", user_id
        ).eq("is_active", True).order("created_at", desc=True).limit(limit).offset(offset).execute()
        
        return result.data if result.data else []
    
    def delete_session(self, session_id: str) -> bool:
        """Soft delete session (set is_active to False)"""
        session = self.get_session(session_id)

        result = self.supabase.table("pdf_sessions").update({
            "is_active": False,
            "updated_at": datetime.now().isoformat()
        }).eq("session_id", session_id).execute()

        success = bool(result.data)

        if success and session and session.get("user_id"):
            invalidate_user_sessions(session["user_id"])
        
        return success
    
    def cleanup_old_sessions(self, days_old: int = 7):
        """
        Cleanup sessions older than X days
        (Run this periodically with a cron job)
        """
        from datetime import timedelta
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        result = self.supabase.table("pdf_sessions").delete().lt(
            "created_at", cutoff_date
        ).execute()
        
        return len(result.data) if result.data else 0
    
    @cache_session_count(ttl=300)
    def count_user_sessions(self, user_id: str) -> int:
        result = self.supabase.table(
            "pdf_sessions"
            ).select(
                "session_id", count="exact"
                ).eq(
                    "user_id", user_id
                ).eq(
                    "is_active", True
                ).execute() 
        return result.count or 0
