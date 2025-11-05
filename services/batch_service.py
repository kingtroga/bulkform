"""
Batch Service
Manages batch PDF generation jobs from CSV/Excel data

Workflow:
1. User uploads CSV with client data
2. Selects template (I-485, etc.)
3. Batch Service creates batch job + items
4. Processes each item (fill PDF for each row)
5. Tracks progress (completed/failed counts)
6. Returns download URLs

Example:
    # Create batch from CSV data
    batch_id = batch_service.create_batch(
        user_id="user-123",
        template_id="template-456",
        items=[
            {"first_name": "John", "last_name": "Smith"},
            {"first_name": "Jane", "last_name": "Doe"}
        ]
    )
    
    # Process batch (fills PDFs)
    result = batch_service.process_batch(batch_id)
    
    # Check progress
    progress = batch_service.get_batch_progress(batch_id)
    # Returns: {"total": 2, "completed": 2, "failed": 0, "status": "completed"}
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from services.supabase_client import get_supabase


class BatchService:
    """Service for managing batch PDF generation jobs"""
    
    def __init__(self):
        """Initialize batch service with Supabase client"""
        self.supabase = get_supabase()
        self.batch_table = "batch_jobs"
        self.items_table = "batch_items"
        print("✅ Batch Service initialized")
    
    
    def create_batch(
        self,
        user_id: str,
        template_id: str,
        items: List[Dict[str, Any]],
        batch_name: Optional[str] = None
    ) -> str:
        """
        Create a new batch job
        
        Args:
            user_id: UUID of user creating batch
            template_id: UUID of template to use
            items: List of data dicts (one per PDF to generate)
                Example: [
                    {"first_name": "John", "last_name": "Smith"},
                    {"first_name": "Jane", "last_name": "Doe"}
                ]
            batch_name: Optional name for batch
            
        Returns:
            UUID string of created batch job
            
        Example:
            batch_id = batch_service.create_batch(
                user_id="abc-123",
                template_id="def-456",
                items=[...],
                batch_name="October 2025 Green Cards"
            )
        """
        try:
            # Validate inputs
            if not items:
                raise ValueError("Items list cannot be empty")
            
            if not user_id or not template_id:
                raise ValueError("user_id and template_id are required")
            
            # Create batch job
            batch_id = str(uuid.uuid4())
            
            batch_data = {
                "id": batch_id,
                "user_id": user_id,
                "template_id": template_id,
                "batch_name": batch_name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "total_items": len(items),
                "completed": 0,
                "failed": 0,
                "status": "pending"
            }
            
            result = self.supabase.table(self.batch_table).insert(batch_data).execute()
            
            if not result.data:
                raise Exception("Failed to create batch job")
            
            # Create batch items
            batch_items = [
                {
                    "batch_id": batch_id,
                    "item_index": idx,
                    "client_data": item,
                    "status": "pending"
                }
                for idx, item in enumerate(items)
            ]
            
            items_result = self.supabase.table(self.items_table).insert(batch_items).execute()
            
            if not items_result.data:
                # Rollback batch job if items fail
                self.supabase.table(self.batch_table).delete().eq("id", batch_id).execute()
                raise Exception("Failed to create batch items")
            
            print(f"✅ Batch created: {batch_id} ({len(items)} items)")
            
            return batch_id
        
        except Exception as e:
            print(f"❌ Failed to create batch: {str(e)}")
            raise Exception(f"Batch creation failed: {str(e)}")
    
    
    def get_batch(
        self,
        batch_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get batch job details
        
        Args:
            batch_id: UUID of batch
            user_id: UUID of user (for ownership verification)
            
        Returns:
            Batch dict if found, None otherwise
            
        Example return:
            {
                "id": "batch-123",
                "user_id": "user-456",
                "template_id": "template-789",
                "batch_name": "October Green Cards",
                "total_items": 50,
                "completed": 45,
                "failed": 2,
                "status": "processing",
                "created_at": "2025-11-03T10:00:00Z"
            }
        """
        try:
            result = self.supabase.table(self.batch_table).select("*").eq(
                "id", batch_id
            ).eq(
                "user_id", user_id
            ).execute()
            
            if not result.data:
                print(f"⚠️  Batch not found or unauthorized: {batch_id}")
                return None
            
            batch = result.data[0]
            print(f"✅ Batch retrieved: {batch['batch_name']}")
            
            return batch
        
        except Exception as e:
            print(f"❌ Failed to get batch: {str(e)}")
            return None
    
    
    def list_batches(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List user's batch jobs
        
        Args:
            user_id: UUID of user
            status: Filter by status (optional)
            limit: Max batches to return (default 50)
            offset: Number to skip (for pagination)
            
        Returns:
            List of batch dicts, newest first
        """
        try:
            query = self.supabase.table(self.batch_table).select("*").eq(
                "user_id", user_id
            )
            
            if status:
                query = query.eq("status", status)
            
            result = query.order(
                "created_at", desc=True
            ).limit(limit).offset(offset).execute()
            
            batches = result.data if result.data else []
            
            print(f"✅ Retrieved {len(batches)} batches for user")
            
            return batches
        
        except Exception as e:
            print(f"❌ Failed to list batches: {str(e)}")
            return []
    
    
    def update_batch_status(
        self,
        batch_id: str,
        status: str,
        download_url: Optional[str] = None,
        error_log: Optional[List[Dict]] = None
    ) -> bool:
        """
        Update batch job status
        
        Args:
            batch_id: UUID of batch
            status: New status ('pending', 'processing', 'completed', 'failed')
            download_url: Optional download URL for completed batch
            error_log: Optional list of errors
            
        Returns:
            True if successful, False otherwise
        """
        try:
            updates = {"status": status}
            
            if download_url:
                updates["download_url"] = download_url
            
            if error_log:
                updates["error_log"] = error_log
            
            result = self.supabase.table(self.batch_table).update(updates).eq(
                "id", batch_id
            ).execute()
            
            if not result.data:
                print(f"❌ Failed to update batch status")
                return False
            
            print(f"✅ Batch status updated: {batch_id} → {status}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to update batch status: {str(e)}")
            return False
    
    
    def get_batch_items(
        self,
        batch_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all items in a batch
        
        Args:
            batch_id: UUID of batch
            status: Filter by status (optional)
            
        Returns:
            List of batch item dicts
        """
        try:
            query = self.supabase.table(self.items_table).select("*").eq(
                "batch_id", batch_id
            )
            
            if status:
                query = query.eq("status", status)
            
            result = query.order("item_index").execute()
            
            items = result.data if result.data else []
            
            print(f"✅ Retrieved {len(items)} items from batch {batch_id}")
            
            return items
        
        except Exception as e:
            print(f"❌ Failed to get batch items: {str(e)}")
            return []
    
    
    def update_batch_item(
        self,
        item_id: str,
        status: str,
        pdf_url: Optional[str] = None,
        storage_path: Optional[str] = None,  # ← ADD THIS
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update single batch item status
        
        Args:
            item_id: UUID of batch item
            status: New status
            pdf_url: Download URL (expires in 1 hour)
            storage_path: Storage path (permanent) ← NEW!
            error_message: Error message if failed
        """
        try:
            updates = {"status": status}
            
            if pdf_url:
                updates["pdf_url"] = pdf_url
            
            if storage_path:  # ← ADD THIS
                updates["storage_path"] = storage_path
            
            if error_message:
                updates["error_message"] = error_message
            
            result = self.supabase.table(self.items_table).update(updates).eq(
                "id", item_id
            ).execute()
            
            if not result.data:
                return False
            
            print(f"✅ Batch item updated: {item_id} → {status}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to update batch item: {str(e)}")
            return False
    
    
    def increment_batch_counters(
        self,
        batch_id: str,
        completed: int = 0,
        failed: int = 0
    ) -> bool:
        """
        Increment completed/failed counters
        
        Args:
            batch_id: UUID of batch
            completed: Number to add to completed count
            failed: Number to add to failed count
            
        Returns:
            True if successful
        """
        try:
            # Get current counts
            batch = self.supabase.table(self.batch_table).select(
                "completed, failed, total_items"
            ).eq("id", batch_id).execute()
            
            if not batch.data:
                return False
            
            current = batch.data[0]
            new_completed = current["completed"] + completed
            new_failed = current["failed"] + failed
            
            # Update counts
            updates = {
                "completed": new_completed,
                "failed": new_failed
            }
            
            # Auto-update status if all done
            if new_completed + new_failed >= current["total_items"]:
                if new_failed == 0:
                    updates["status"] = "completed"
                else:
                    updates["status"] = "completed_with_errors"
            
            result = self.supabase.table(self.batch_table).update(updates).eq(
                "id", batch_id
            ).execute()
            
            return bool(result.data)
        
        except Exception as e:
            print(f"❌ Failed to increment counters: {str(e)}")
            return False
    
    
    def get_batch_progress(
        self,
        batch_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get batch processing progress
        
        Args:
            batch_id: UUID of batch
            user_id: UUID of user (for ownership check)
            
        Returns:
            Progress dict with stats
            
        Example return:
            {
                "batch_id": "abc-123",
                "total": 50,
                "completed": 45,
                "failed": 2,
                "pending": 3,
                "status": "processing",
                "progress_percentage": 94.0,
                "estimated_time_remaining": "2 minutes"
            }
        """
        try:
            batch = self.get_batch(batch_id, user_id)
            
            if not batch:
                return {"error": "Batch not found"}
            
            total = batch["total_items"]
            completed = batch["completed"]
            failed = batch["failed"]
            pending = total - completed - failed
            
            progress_pct = round((completed + failed) / total * 100, 1) if total > 0 else 0
            
            # Simple time estimation (assume 2 seconds per item)
            if pending > 0 and progress_pct > 0:
                avg_time_per_item = 2  # seconds
                est_seconds = pending * avg_time_per_item
                est_minutes = round(est_seconds / 60, 1)
                est_time = f"{est_minutes} minutes" if est_minutes >= 1 else f"{est_seconds} seconds"
            else:
                est_time = "Complete!"
            
            return {
                "batch_id": batch_id,
                "batch_name": batch["batch_name"],
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "status": batch["status"],
                "progress_percentage": progress_pct,
                "estimated_time_remaining": est_time,
                "download_url": batch.get("download_url"),
                "created_at": batch["created_at"],
                "updated_at": batch["updated_at"]
            }
        
        except Exception as e:
            print(f"❌ Failed to get progress: {str(e)}")
            return {"error": str(e)}
    
    
    def delete_batch(
        self,
        batch_id: str,
        user_id: str
    ) -> bool:
        """
        Delete a batch job (cascades to items)
        
        Args:
            batch_id: UUID of batch
            user_id: UUID of user (for ownership check)
            
        Returns:
            True if successful
        """
        try:
            # Verify ownership
            batch = self.get_batch(batch_id, user_id)
            if not batch:
                print(f"⚠️  Cannot delete - batch not found or unauthorized")
                return False
            
            # Delete batch (items cascade via ON DELETE CASCADE)
            result = self.supabase.table(self.batch_table).delete().eq(
                "id", batch_id
            ).eq(
                "user_id", user_id
            ).execute()
            
            print(f"✅ Batch deleted: {batch_id}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to delete batch: {str(e)}")
            return False
    
    
    def count_user_batches(
        self,
        user_id: str,
        status: Optional[str] = None
    ) -> int:
        """
        Count user's batches
        
        Args:
            user_id: UUID of user
            status: Optional status filter
            
        Returns:
            Number of batches
        """
        try:
            query = self.supabase.table(self.batch_table).select(
                "id", count="exact"
            ).eq("user_id", user_id)
            
            if status:
                query = query.eq("status", status)
            
            result = query.execute()
            
            return result.count if result.count else 0
        
        except Exception as e:
            print(f"❌ Failed to count batches: {str(e)}")
            return 0
    
    
    def get_failed_items(
        self,
        batch_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all failed items in a batch
        
        Args:
            batch_id: UUID of batch
            
        Returns:
            List of failed items with error messages
        """
        return self.get_batch_items(batch_id, status="failed")
    
    
    def retry_failed_items(
        self,
        batch_id: str,
        user_id: str
    ) -> bool:
        """
        Reset failed items to pending for retry
        
        Args:
            batch_id: UUID of batch
            user_id: UUID of user
            
        Returns:
            True if successful
        """
        try:
            # Verify ownership
            batch = self.get_batch(batch_id, user_id)
            if not batch:
                return False
            
            # Get failed items
            failed_items = self.get_failed_items(batch_id)
            
            if not failed_items:
                print(f"⚠️  No failed items to retry")
                return True
            
            # Reset to pending
            for item in failed_items:
                self.update_batch_item(
                    item["id"],
                    status="pending",
                    error_message=None
                )
            
            # Update batch counters
            self.supabase.table(self.batch_table).update({
                "failed": 0,
                "status": "pending"
            }).eq("id", batch_id).execute()
            
            print(f"✅ Retry queued for {len(failed_items)} failed items")
            return True
        
        except Exception as e:
            print(f"❌ Failed to retry items: {str(e)}")
            return False


# ============================================================================
# CONVENIENCE FUNCTION - Easy import
# ============================================================================

def get_batch_service() -> BatchService:
    """Get batch service instance"""
    return BatchService()