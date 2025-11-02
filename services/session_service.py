"""
Session Service - Database-backed PDF session management
Survives server restarts! 🔥
"""
from services.supabase_client import get_supabase
from typing import Dict, Optional, List
from datetime import datetime


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
        
        return result.data[0] if result.data else None
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by session_id"""
        try:
            result = self.supabase.table("pdf_sessions").select("*").eq(
                "session_id", session_id
            ).single().execute()
            
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
    
    def get_user_sessions(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get all sessions for a user (newest first)"""
        result = self.supabase.table("pdf_sessions").select("*").eq(
            "user_id", user_id
        ).order("created_at", desc=True).limit(limit).execute()
        
        return result.data if result.data else []
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session from database"""
        result = self.supabase.table("pdf_sessions").delete().eq(
            "session_id", session_id
        ).execute()
        
        return bool(result.data)
    
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