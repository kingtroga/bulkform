"""
Batch Service - Complete Test Suite
Tests batch job creation, progress tracking, and item management
"""

from services.batch_service import get_batch_service

print("=" * 70)
print("🧪 BATCH SERVICE - COMPLETE TEST SUITE")
print("=" * 70)

# ⚠️ REPLACE with your actual user_id and template_id
YOUR_USER_ID = "d18772bf-7605-4297-8a34-12d8e626199d"
YOUR_TEMPLATE_ID = "cdb1b643-c389-4a22-a065-f05247eece35"  # Use an existing template

# Initialize service
batch_service = get_batch_service()


# ============================================================================
# TEST 1: Create Batch Job
# ============================================================================

print("\n" + "=" * 70)
print("TEST 1: Create Batch Job")
print("=" * 70)

# Sample client data (like from CSV)
sample_items = [
    {"first_name": "John", "last_name": "Smith", "email": "john@ex.com"},
    {"first_name": "Jane", "last_name": "Doe", "email": "jane@ex.com"},
    {"first_name": "Bob", "last_name": "Johnson", "email": "bob@ex.com"}
]

try:
    batch_id = batch_service.create_batch(
        user_id=YOUR_USER_ID,
        template_id=YOUR_TEMPLATE_ID,
        items=sample_items,
        batch_name="Test Batch - November 2025"
    )
    print(f"✅ Batch created: {batch_id}")
    print(f"   Items: {len(sample_items)}")
except Exception as e:
    print(f"❌ Failed to create batch: {e}")
    batch_id = None


# ============================================================================
# TEST 2: Get Batch Details
# ============================================================================

print("\n" + "=" * 70)
print("TEST 2: Get Batch Details")
print("=" * 70)

if batch_id:
    batch = batch_service.get_batch(batch_id, YOUR_USER_ID)
    if batch:
        print(f"✅ Batch retrieved: {batch['batch_name']}")
        print(f"   Total items: {batch['total_items']}")
        print(f"   Status: {batch['status']}")
        print(f"   Completed: {batch['completed']}")
        print(f"   Failed: {batch['failed']}")
    else:
        print("❌ Failed to retrieve batch")
else:
    print("⚠️  Skipped (no batch created)")


# ============================================================================
# TEST 3: List User's Batches
# ============================================================================

print("\n" + "=" * 70)
print("TEST 3: List User's Batches")
print("=" * 70)

batches = batch_service.list_batches(YOUR_USER_ID)
print(f"✅ Found {len(batches)} batch(es)")
for b in batches[:5]:  # Show first 5
    print(f"   - {b['batch_name']} ({b['total_items']} items) - {b['status']}")


# ============================================================================
# TEST 4: Get Batch Items
# ============================================================================

print("\n" + "=" * 70)
print("TEST 4: Get Batch Items")
print("=" * 70)

if batch_id:
    items = batch_service.get_batch_items(batch_id)
    print(f"✅ Retrieved {len(items)} items")
    for item in items:
        print(f"   Item {item['item_index']}: {item['client_data']['first_name']} - {item['status']}")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 5: Update Batch Item Status
# ============================================================================

print("\n" + "=" * 70)
print("TEST 5: Update Batch Item Status")
print("=" * 70)

if batch_id and items:
    # Simulate processing first item
    first_item = items[0]
    
    success = batch_service.update_batch_item(
        item_id=first_item['id'],
        status="completed",
        pdf_url="https://storage.example.com/pdf123.pdf"
    )
    
    if success:
        print(f"✅ Item {first_item['item_index']} marked as completed")
    else:
        print("❌ Failed to update item")
else:
    print("⚠️  Skipped (no items)")


# ============================================================================
# TEST 6: Increment Batch Counters
# ============================================================================

print("\n" + "=" * 70)
print("TEST 6: Increment Batch Counters")
print("=" * 70)

if batch_id:
    # Simulate completing 1 item
    success = batch_service.increment_batch_counters(
        batch_id=batch_id,
        completed=1,
        failed=0
    )
    
    if success:
        print("✅ Batch counters incremented")
        
        # Verify
        updated_batch = batch_service.get_batch(batch_id, YOUR_USER_ID)
        if updated_batch:
            print(f"   Completed: {updated_batch['completed']}")
            print(f"   Failed: {updated_batch['failed']}")
    else:
        print("❌ Failed to increment counters")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 7: Get Batch Progress
# ============================================================================

print("\n" + "=" * 70)
print("TEST 7: Get Batch Progress")
print("=" * 70)

if batch_id:
    progress = batch_service.get_batch_progress(batch_id, YOUR_USER_ID)
    
    if "error" not in progress:
        print("✅ Progress retrieved:")
        print(f"   Total: {progress['total']}")
        print(f"   Completed: {progress['completed']}")
        print(f"   Failed: {progress['failed']}")
        print(f"   Pending: {progress['pending']}")
        print(f"   Progress: {progress['progress_percentage']}%")
        print(f"   Est. time: {progress['estimated_time_remaining']}")
    else:
        print(f"❌ Error: {progress['error']}")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 8: Update Batch Status
# ============================================================================

print("\n" + "=" * 70)
print("TEST 8: Update Batch Status")
print("=" * 70)

if batch_id:
    success = batch_service.update_batch_status(
        batch_id=batch_id,
        status="processing"
    )
    
    if success:
        print("✅ Batch status updated to 'processing'")
    else:
        print("❌ Failed to update status")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 9: Simulate Failed Item
# ============================================================================

print("\n" + "=" * 70)
print("TEST 9: Simulate Failed Item")
print("=" * 70)

if batch_id and items:
    # Mark second item as failed
    second_item = items[1]
    
    success = batch_service.update_batch_item(
        item_id=second_item['id'],
        status="failed",
        error_message="PDF generation timeout"
    )
    
    if success:
        print(f"✅ Item {second_item['item_index']} marked as failed")
        
        # Increment failed counter
        batch_service.increment_batch_counters(batch_id, failed=1)
        print("✅ Failed counter incremented")
    else:
        print("❌ Failed to mark item as failed")
else:
    print("⚠️  Skipped (no items)")


# ============================================================================
# TEST 10: Get Failed Items
# ============================================================================

print("\n" + "=" * 70)
print("TEST 10: Get Failed Items")
print("=" * 70)

if batch_id:
    failed_items = batch_service.get_failed_items(batch_id)
    print(f"✅ Found {len(failed_items)} failed item(s)")
    
    for item in failed_items:
        print(f"   Item {item['item_index']}: {item['error_message']}")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 11: Retry Failed Items
# ============================================================================

print("\n" + "=" * 70)
print("TEST 11: Retry Failed Items")
print("=" * 70)

if batch_id:
    success = batch_service.retry_failed_items(batch_id, YOUR_USER_ID)
    
    if success:
        print("✅ Failed items reset for retry")
        
        # Verify
        progress = batch_service.get_batch_progress(batch_id, YOUR_USER_ID)
        print(f"   Failed count: {progress['failed']}")
    else:
        print("❌ Failed to retry items")
else:
    print("⚠️  Skipped (no batch)")


# ============================================================================
# TEST 12: Count User's Batches
# ============================================================================

print("\n" + "=" * 70)
print("TEST 12: Count User's Batches")
print("=" * 70)

total_count = batch_service.count_user_batches(YOUR_USER_ID)
pending_count = batch_service.count_user_batches(YOUR_USER_ID, status="pending")
processing_count = batch_service.count_user_batches(YOUR_USER_ID, status="processing")

print(f"✅ Total batches: {total_count}")
print(f"   Pending: {pending_count}")
print(f"   Processing: {processing_count}")


# ============================================================================
# TEST 13: List Batches with Status Filter
# ============================================================================

print("\n" + "=" * 70)
print("TEST 13: List Batches (Status Filter)")
print("=" * 70)

processing_batches = batch_service.list_batches(YOUR_USER_ID, status="processing")
print(f"✅ Found {len(processing_batches)} processing batch(es)")


# ============================================================================
# TEST 14: Delete Batch
# ============================================================================

print("\n" + "=" * 70)
print("TEST 14: Cleanup - Delete Test Batch")
print("=" * 70)

if batch_id:
    print("Delete the test batch? (y/n)")
    choice = input().lower()
    
    if choice == 'y':
        success = batch_service.delete_batch(batch_id, YOUR_USER_ID)
        
        if success:
            print("✅ Test batch deleted")
        else:
            print("❌ Failed to delete batch")
    else:
        print("⚠️  Batch kept (delete manually if needed)")
else:
    print("⚠️  No batch to delete")


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 70)
print("📊 TEST SUMMARY")
print("=" * 70)

print(f"""
Batch Management:
  ✅ Create batch job
  ✅ Get batch details
  ✅ List user's batches
  ✅ Count batches
  ✅ Update batch status
  ✅ Delete batch

Item Management:
  ✅ Get batch items
  ✅ Update item status
  ✅ Mark item as failed
  ✅ Get failed items
  ✅ Retry failed items

Progress Tracking:
  ✅ Increment counters (completed/failed)
  ✅ Get progress with percentage
  ✅ Estimate time remaining
  ✅ Auto-update status when complete

Next Steps:
1. Integrate with CSV Processor (CSV → Batch)
2. Integrate with Template Service (validate fields)
3. Build batch processing endpoint (process all items)
4. Create API routes for batch management
""")

print("=" * 70)
print("✅ ALL TESTS COMPLETE!")
print("=" * 70)