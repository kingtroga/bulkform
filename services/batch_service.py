"""
Batch Service - FIXED VERSION
Manages batch PDF generation jobs from CSV/Excel data

Key Fix: Removed auto-status update from increment_batch_counters
to prevent premature "completed" status while items are still processing.
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

        # --- NEW: internal helpers ---------------------------------------------

    def _count_items(self, batch_id: str, status: Optional[str] = None) -> int:
        """
        Count items in batch, optionally by status.
        Uses Supabase exact count to avoid fetching rows.
        """
        try:
            q = (self.supabase
                 .table(self.items_table)
                 .select("id", count="exact")
                 .eq("batch_id", batch_id))
            if status:
                q = q.eq("status", status)
            res = q.execute()
            return res.count or 0
        except Exception as e:
            print(f"❌ _count_items failed: {e}")
            return 0

    def get_item_counts(self, batch_id: str) -> Dict[str, int]:
        """
        Authoritative counts from batch_items (source of truth).
        """
        total      = self._count_items(batch_id, None)       # all rows
        completed  = self._count_items(batch_id, "completed")
        failed     = self._count_items(batch_id, "failed")
        pending    = self._count_items(batch_id, "pending")
        processing = self._count_items(batch_id, "processing")
        # In case of any mismatch, recompute pending as a fallback:
        if total and (completed + failed + pending + processing) != total:
            pending = max(total - completed - failed - processing, 0)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "processing": processing,
        }

    def _reconcile_batch_counters(self, batch_id: str, counts: Dict[str, int]) -> None:
        """
        Optionally sync the batch_jobs counters to match items.
        Does NOT touch status here.
        """
        try:
            self.supabase.table(self.batch_table).update({
                "completed": counts["completed"],
                "failed": counts["failed"],
                "total_items": counts["total"],
            }).eq("id", batch_id).execute()
        except Exception as e:
            print(f"⚠️  Failed to reconcile batch counters: {e}")

    
    
    def create_batch(
        self,
        user_id: str,
        template_id: str,
        items: List[Dict[str, Any]],
        batch_name: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new batch job
        
        Args:
            user_id: UUID of user creating batch
            template_id: UUID of template to use
            items: List of data dicts (one per PDF to generate)
            batch_name: Optional name for batch
            
        Returns:
            UUID string of created batch job
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
                "status": "pending",
                "options": options or {},
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
        storage_path: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update single batch item status
        
        Args:
            item_id: UUID of batch item
            status: New status
            pdf_url: Download URL (expires in 1 hour)
            storage_path: Storage path (permanent)
            error_message: Error message if failed
        """
        try:
            updates = {"status": status}
            
            if pdf_url:
                updates["pdf_url"] = pdf_url
            
            if storage_path:
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
            
        IMPORTANT:
            Does NOT auto-update status to "completed". 
            Status should be managed by the batch processor 
            (process_batch_sync) after verifying all items are done.
            
            This prevents premature "completed" status when items
            are still being processed (status="processing").
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
            
            # Update counts only - status managed separately by process_batch_sync
            updates = {
                "completed": new_completed,
                "failed": new_failed
            }
            
            # ❌ REMOVED: Auto-status update that caused Bug #2
            # The batch processor will set status after verifying all items
            
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
        Progress computed from items (authoritative), not the batch counters.
        Keeps batch counters reconciled for UI convenience.
        """
        try:
            batch = self.get_batch(batch_id, user_id)
            if not batch:
                return {"error": "Batch not found"}

            counts = self.get_item_counts(batch_id)
            # Reconcile counters (optional but recommended for UI/queries)
            self._reconcile_batch_counters(batch_id, counts)

            total      = counts["total"]
            completed  = counts["completed"]
            failed     = counts["failed"]
            pending    = counts["pending"]
            processing = counts["processing"]

            # Derive an honest status from counts if batch.status is misleading
            derived_status = batch["status"]
            if total == 0:
                derived_status = "pending"
            elif pending == 0 and processing == 0:
                derived_status = "completed" if failed == 0 else "completed_with_errors"
            elif completed == 0 and failed == 0:
                derived_status = "pending"  # nothing started yet
            else:
                derived_status = "processing"

            progress_pct = round(((completed + failed) / total * 100), 1) if total > 0 else 0

            # Simple ETA (tweak if you keep historical durations)
            if pending > 0 and progress_pct > 0:
                avg_time_per_item = 2  # seconds (your previous heuristic)
                est_seconds = pending * avg_time_per_item
                est_time = f"{round(est_seconds/60,1)} minutes" if est_seconds >= 60 else f"{est_seconds} seconds"
            else:
                est_time = "Complete!"

            return {
                "batch_id": batch_id,
                "batch_name": batch["batch_name"],
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "status": derived_status,
                "progress_percentage": progress_pct,
                "estimated_time_remaining": est_time,
                "download_url": batch.get("download_url"),
                "created_at": batch["created_at"],
                "updated_at": batch["updated_at"],
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
            
            # Update batch counters and status
            self.supabase.table(self.batch_table).update({
                "failed": 0,
                "status": "pending"
            }).eq("id", batch_id).execute()
            
            print(f"✅ Retry queued for {len(failed_items)} failed items")
            return True
        
        except Exception as e:
            print(f"❌ Failed to retry items: {str(e)}")
            return False

    def reset_items_status(
        self,
        batch_id: str,
        user_id: str,
        from_statuses: Optional[List[str]] = None,
        to_status: str = "pending"
    ) -> bool:
        """
        Bulk reset items whose status is in `from_statuses` to `to_status`.
        Also reconciles batch counters and marks batch as 'pending'.

        Default: reset ['failed','processing','pending'] -> 'pending'
        """
        try:
            # Ownership check
            batch = self.get_batch(batch_id, user_id)
            if not batch:
                print("⚠️  reset_items_status: batch not found / unauthorized")
                return False

            if not from_statuses:
                from_statuses = ["failed", "processing", "pending"]

            # Update items
            upd = (self.supabase
                   .table(self.items_table)
                   .update({"status": to_status, "error_message": None})
                   .eq("batch_id", batch_id)
                   .in_("status", from_statuses)
                   .execute())

            # Recompute counters from items and reconcile
            counts = self.get_item_counts(batch_id)
            self._reconcile_batch_counters(batch_id, counts)

            # Put batch back to 'pending' so caller can re-queue work
            self.supabase.table(self.batch_table).update({
                "status": "pending"
            }).eq("id", batch_id).execute()

            print(f"✅ reset_items_status: moved {len(upd.data) if upd and upd.data else 'some'} items "
                  f"from {from_statuses} to '{to_status}'")
            return True

        except Exception as e:
            print(f"❌ reset_items_status failed: {e}")
            return False


# ============================================================================
# CONVENIENCE FUNCTION - Easy import
# ============================================================================

def get_batch_service() -> BatchService:
    """Get batch service instance"""
    return BatchService()