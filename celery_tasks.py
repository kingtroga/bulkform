"""
Celery Tasks - PARALLEL PDF PROCESSING
Each PDF is processed independently in parallel by different workers

SPEED: 100 PDFs in ~2-5 minutes with 10 workers (vs 43 mins sequential)
"""

from celery_config import celery_app
from typing import Dict, List
import time

# Import your existing services
from services.batch_service import get_batch_service
from services.template_service import get_template_service
from services.pdf_processor import PDFProcessor
from services.image_service import get_image_service
from batch_processing import fill_single_pdf_sync
from batch_download import create_batch_zip
import asyncio


@celery_app.task(name='celery_tasks.process_single_pdf', bind=True)
def process_single_pdf_task(
    self,
    batch_id: str,
    item_id: str,
    item_index: int,
    client_data: Dict,
    template_id: str,
    user_id: str
):
    """
    Process a SINGLE PDF in parallel
    
    This runs independently on different workers
    100 items = 100 parallel tasks across your workers
    
    Args:
        self: Celery task instance (for retries)
        batch_id: Batch UUID
        item_id: Item UUID
        item_index: Item number (0-99 for 100 items)
        client_data: Client form data
        template_id: Template UUID
        user_id: User UUID
        
    Returns:
        Dict with storage_url and storage_path
    """
    task_start = time.time()
    print(f"\n🚀 [Worker {self.request.id[:8]}] Processing item {item_index}")
    
    try:
        batch_service = get_batch_service()
        template_service = get_template_service()
        
        # Mark as processing
        batch_service.update_batch_item(item_id, "processing")
        
        # Get template
        template = template_service.get_template(template_id, user_id)
        if not template:
            raise Exception(f"Template not found: {template_id}")
        
        # Fill PDF (this is the heavy work)
        pdf_start = time.time()
        result = fill_single_pdf_sync(
            template=template,
            client_data=client_data,
            user_id=user_id,
            batch_id=batch_id,
            item_index=item_index
        )
        pdf_time = time.time() - pdf_start
        
        # Mark as completed
        batch_service.update_batch_item(
            item_id,
            "completed",
            pdf_url=result['storage_url'],
            storage_path=result['storage_path']
        )
        
        # Increment counters
        batch_service.increment_batch_counters(batch_id, completed=1)
        
        task_time = time.time() - task_start
        print(f"✅ [Worker {self.request.id[:8]}] Item {item_index} done in {task_time:.1f}s (PDF: {pdf_time:.1f}s)")
        
        return {
            'item_id': item_id,
            'item_index': item_index,
            'storage_url': result['storage_url'],
            'storage_path': result['storage_path'],
            'processing_time': task_time
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [Worker {self.request.id[:8]}] Item {item_index} failed: {error_msg}")
        
        # Mark as failed
        batch_service = get_batch_service()
        batch_service.update_batch_item(
            item_id,
            "failed",
            error_message=error_msg
        )
        batch_service.increment_batch_counters(batch_id, failed=1)
        
        # Retry logic (Celery auto-retries)
        raise self.retry(exc=e, countdown=5, max_retries=2)


@celery_app.task(name='celery_tasks.finalize_batch')
def finalize_batch_task(batch_id: str, user_id: str):
    """
    Finalize batch after all items processed
    
    Called by a Celery chord/chain after all PDFs done
    Checks final status and marks batch complete
    """
    print(f"\n🏁 Finalizing batch: {batch_id}")
    
    try:
        batch_service = get_batch_service()
        
        # Check if all items done
        remaining = batch_service.get_batch_items(batch_id, status="pending")
        processing = batch_service.get_batch_items(batch_id, status="processing")
        
        if len(remaining) == 0 and len(processing) == 0:
            # All done!
            batch_service.update_batch_status(batch_id, "completed")
            print(f"✅ Batch {batch_id} completed!")
        else:
            print(f"⚠️  Batch {batch_id} still has {len(remaining)} pending, {len(processing)} processing")
    
    except Exception as e:
        print(f"❌ Failed to finalize batch: {str(e)}")


@celery_app.task(name='celery_tasks.create_batch_zip_task')
def create_batch_zip_task(
    batch_id: str,
    batch_name: str,
    user_id: str
):
    """
    Create zip file asynchronously
    
    This is also slow, so we offload it to Celery
    User gets instant response, zip created in background
    """
    print(f"\n📦 Creating zip for batch: {batch_id}")
    
    try:
        batch_service = get_batch_service()
        
        # Get completed items
        completed_items = batch_service.get_batch_items(batch_id, status="completed")
        
        if not completed_items:
            print(f"⚠️  No completed items to zip")
            return None
        
        # Build pdf_items list
        pdf_items = [
            {
                "item_index": item["item_index"],
                "pdf_url": item.get("pdf_url"),
                "storage_path": item.get("storage_path"),
                "client_data": item["client_data"]
            }
            for item in completed_items
        ]
        
        # Create zip (async function, so we need event loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        zip_url = loop.run_until_complete(
            create_batch_zip(
                batch_id=batch_id,
                batch_name=batch_name,
                pdf_items=pdf_items,
                user_id=user_id
            )
        )
        
        loop.close()
        
        # Update batch with zip URL
        batch_service.update_batch_status(batch_id, "completed", download_url=zip_url)
        
        print(f"✅ Zip created: {zip_url[:80]}...")
        return zip_url
    
    except Exception as e:
        print(f"❌ Zip creation failed: {str(e)}")
        raise


# ============================================================================
# HELPER FUNCTION - Trigger parallel processing
# ============================================================================

def trigger_parallel_batch(batch_id: str, user_id: str, template_id: str):
    """
    Trigger parallel processing of entire batch
    
    Instead of processing items sequentially, this sends ALL items
    to Celery queue immediately. Workers process them in parallel.
    
    100 items → 100 Celery tasks → Processed by 10 workers in parallel
    = ~10x faster (or more with more workers!)
    
    Args:
        batch_id: Batch UUID
        user_id: User UUID
        template_id: Template UUID
    """
    print(f"\n⚡ PARALLEL PROCESSING START: {batch_id}")
    start_time = time.time()
    
    batch_service = get_batch_service()
    
    # Get ALL pending items
    items = batch_service.get_batch_items(batch_id, status="pending")
    
    if not items:
        print(f"⚠️  No items to process")
        return
    
    print(f"📊 Queuing {len(items)} tasks for parallel processing...")
    
    # Update batch status
    batch_service.update_batch_status(batch_id, "processing")
    
    # Create task group (all tasks run in parallel!)
    from celery import group, chord
    
    # Build parallel task group
    task_group = group(
        process_single_pdf_task.s(
            batch_id=batch_id,
            item_id=item['id'],
            item_index=item['item_index'],
            client_data=item['client_data'],
            template_id=template_id,
            user_id=user_id
        )
        for item in items
    )
    
    # Execute with callback when all done
    callback = finalize_batch_task.s(batch_id, user_id)
    job = chord(task_group)(callback)
    
    queue_time = time.time() - start_time
    
    print(f"✅ {len(items)} tasks queued in {queue_time:.2f}s")
    print(f"🔥 Workers will process in parallel!")
    print(f"⏱️  Expected time with 10 workers: ~{len(items) / 10 * 3:.0f}s ({len(items) / 10 * 3 / 60:.1f} min)")
    
    return job.id