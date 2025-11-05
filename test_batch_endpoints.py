#!/usr/bin/env python3
"""
Comprehensive Batch Endpoints Test Suite
Tests all batch processing functionality with the Guarantor Form template
"""

import requests
import json
import time
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "http://localhost:8000"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6ImNQYTZYYmhja1E4bG5GL3MiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3d0c3ppZWN3bXJpcXl5cG1pZWRwLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJhNmMzYTkzYS1iMWE0LTQ1OTItYWM1My1kYmEzY2Y4OGFlMjAiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzYyMzA1MjkxLCJpYXQiOjE3NjIzMDE2OTEsImVtYWlsIjoidHJvZ2FjbGFzc2ljbWFuQGdtYWlsLmNvbSIsInBob25lIjoiIiwiYXBwX21ldGFkYXRhIjp7InByb3ZpZGVyIjoiZW1haWwiLCJwcm92aWRlcnMiOlsiZW1haWwiLCJnb29nbGUiXX0sInVzZXJfbWV0YWRhdGEiOnsiYXZhdGFyX3VybCI6Imh0dHBzOi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9hL0FDZzhvY0xKODJzWkFJaHY3OEtZeUZER0lYOFMtN3VwS2tsZFNKY05VeE91Q1FiTzVkUFFHcVFabnc9czk2LWMiLCJlbWFpbCI6InRyb2dhY2xhc3NpY21hbkBnbWFpbC5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiZnVsbF9uYW1lIjoiVGFyaSBZZWtvcm9naGEiLCJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJuYW1lIjoiVGFyaSBZZWtvcm9naGEiLCJwaG9uZV92ZXJpZmllZCI6ZmFsc2UsInBpY3R1cmUiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NMSjgyc1pBSWh2NzhLWXlGREdJWDhTLTd1cEtrbGRTSmNOVXhPdUNRYk81ZFBRR3FRWm53PXM5Ni1jIiwicHJvdmlkZXJfaWQiOiIxMTE1NzUwNzM3NDQyMDMxNjQ0NTIiLCJzdWIiOiIxMTE1NzUwNzM3NDQyMDMxNjQ0NTIifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJvYXV0aCIsInRpbWVzdGFtcCI6MTc2MjMwMTY5MX1dLCJzZXNzaW9uX2lkIjoiYWU5YTllZTMtYmE2My00M2ZjLWFjZDMtNzFmYzRkYzJhNDg1IiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.fmP0GA7Jup1WP9tqrR84I2kfAnnNPII70WvXIJfG1o4"  # Replace with actual token

# Template ID from your example
TEMPLATE_ID = "417fecc1-2cdc-45cd-8e67-97f54a39f588"
USER_ID = "a6c3a93a-b1a4-4592-ac53-dba3cf88ae20"

# Test data file
CSV_FILE = "test_guarantors.csv"

# Headers
headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}"
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_separator(title=""):
    """Print a nice separator"""
    print("\n" + "="*80)
    if title:
        print(f"  {title}")
        print("="*80)


def print_success(message):
    """Print success message"""
    print(f"✅ {message}")


def print_error(message):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


def print_json(data, indent=2):
    """Pretty print JSON"""
    print(json.dumps(data, indent=indent))


def wait_for_completion(batch_id, max_wait=300, poll_interval=3):
    """
    Poll batch progress until completion or timeout
    
    Args:
        batch_id: Batch ID to track
        max_wait: Maximum seconds to wait (default: 5 minutes)
        poll_interval: Seconds between polls (default: 3)
    
    Returns:
        Final progress dict
    """
    print_info(f"Waiting for batch {batch_id} to complete...")
    print_info(f"Polling every {poll_interval} seconds (max {max_wait}s)")
    
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        
        if elapsed > max_wait:
            print_error(f"Timeout after {max_wait} seconds")
            return None
        
        # Get progress
        response = requests.get(
            f"{BASE_URL}/api/batch/{batch_id}/progress",
            headers=headers
        )
        
        if response.status_code != 200:
            print_error(f"Failed to get progress: {response.status_code}")
            return None
        
        progress = response.json()
        
        # Print progress
        print(f"  Progress: {progress['progress_percentage']:.1f}% "
              f"({progress['completed']}/{progress['total']} completed, "
              f"{progress['failed']} failed) - "
              f"Status: {progress['status']}")
        
        # Check if done
        if progress['status'] in ['completed', 'completed_with_errors', 'failed']:
            print_success(f"Batch completed with status: {progress['status']}")
            return progress
        
        # Wait before next poll
        time.sleep(poll_interval)


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_01_health_check():
    """Test 1: Health Check Endpoint"""
    print_separator("TEST 1: Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/api/batch/health")
        
        if response.status_code == 200:
            data = response.json()
            print_success("Health check passed!")
            print_json(data)
            
            # Verify it's the fixed version
            if data.get('version') == '2.0-fixed':
                print_success("✨ Running FIXED version of batch routes!")
            else:
                print_error("⚠️  Not running fixed version!")
            
            return True
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
    
    except Exception as e:
        print_error(f"Health check error: {str(e)}")
        return False


def test_02_create_batch_from_csv():
    """Test 2: Create Batch from CSV Upload"""
    print_separator("TEST 2: Create Batch from CSV")
    
    try:
        # Check if CSV file exists
        if not Path(CSV_FILE).exists():
            print_error(f"CSV file not found: {CSV_FILE}")
            return None
        
        print_info(f"Uploading CSV: {CSV_FILE}")
        
        # Prepare multipart form data
        with open(CSV_FILE, 'rb') as f:
            files = {
                'file': (CSV_FILE, f, 'text/csv')
            }
            data = {
                'template_id': TEMPLATE_ID,
                'batch_name': 'Test Guarantor Batch - CSV Upload'
            }
            
            response = requests.post(
                f"{BASE_URL}/api/batch/create-from-csv",
                files=files,
                data=data,
                headers=headers
            )
        
        if response.status_code == 201:
            batch_data = response.json()
            print_success("Batch created from CSV!")
            print_json(batch_data)
            return batch_data['batch_id']
        else:
            print_error(f"Failed to create batch: {response.status_code}")
            print(response.text)
            return None
    
    except Exception as e:
        print_error(f"Create batch from CSV error: {str(e)}")
        return None


def test_03_create_batch_from_json():
    """Test 3: Create Batch from JSON"""
    print_separator("TEST 3: Create Batch from JSON")
    
    try:
        # Sample data for 2 guarantors
        batch_data = {
            "template_id": TEMPLATE_ID,
            "batch_name": "Test Guarantor Batch - JSON",
            "items": [
                {
                    "full_name": "Alice Cooper",
                    "email": "alice.cooper@email.com",
                    "phone_number": "555-0201",
                    "occupation": "Accountant",
                    "relationship_to_employee": "Friend",
                    "employer_name": "Finance Solutions",
                    "employer_address": "100 Money Street Lagos",
                    "residential_address": "200 Home Road Lagos",
                    "employee_name": "Bob Cooper",
                    "guarantor_declaration_name": "Alice Cooper",
                    "date": "2025-11-04",
                    "international_passport_checkbox": "●",
                    "signature": ""
                },
                {
                    "full_name": "Robert Green",
                    "email": "robert.green@email.com",
                    "phone_number": "555-0202",
                    "occupation": "Engineer",
                    "relationship_to_employee": "Cousin",
                    "employer_name": "Build Co",
                    "employer_address": "300 Construction Ave Lagos",
                    "residential_address": "400 Estate St Lagos",
                    "employee_name": "Rachel Green",
                    "guarantor_declaration_name": "Robert Green",
                    "date": "2025-11-04",
                    "international_passport_checkbox": "●",
                    "signature": ""

                }
            ]
        }
        
        print_info("Creating batch with JSON data...")
        
        response = requests.post(
            f"{BASE_URL}/api/batch",
            json=batch_data,
            headers=headers
        )
        
        if response.status_code == 201:
            result = response.json()
            print_success("Batch created from JSON!")
            print_json(result)
            return result['batch_id']
        else:
            print_error(f"Failed to create batch: {response.status_code}")
            print(response.text)
            return None
    
    except Exception as e:
        print_error(f"Create batch from JSON error: {str(e)}")
        return None


def test_04_get_batch_details(batch_id):
    """Test 4: Get Batch Details"""
    print_separator("TEST 4: Get Batch Details")
    
    if not batch_id:
        print_error("No batch_id provided")
        return False
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/batch/{batch_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            batch = response.json()
            print_success("Batch details retrieved!")
            print_json(batch)
            return True
        else:
            print_error(f"Failed to get batch: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Get batch details error: {str(e)}")
        return False


def test_05_list_batches():
    """Test 5: List All Batches"""
    print_separator("TEST 5: List All Batches")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/batch",
            headers=headers,
            params={'limit': 10}
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Found {result['total']} batches")
            print_json(result)
            return True
        else:
            print_error(f"Failed to list batches: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"List batches error: {str(e)}")
        return False


def test_06_process_batch(batch_id):
    """Test 6: Start Batch Processing"""
    print_separator("TEST 6: Start Batch Processing")
    
    if not batch_id:
        print_error("No batch_id provided")
        return False
    
    try:
        print_info(f"Starting processing for batch: {batch_id}")
        
        response = requests.post(
            f"{BASE_URL}/api/batch/{batch_id}/process",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("Batch processing started!")
            print_json(result)
            return True
        else:
            print_error(f"Failed to start processing: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Process batch error: {str(e)}")
        return False


def test_07_track_progress(batch_id):
    """Test 7: Track Batch Progress"""
    print_separator("TEST 7: Track Batch Progress")
    
    if not batch_id:
        print_error("No batch_id provided")
        return None
    
    try:
        # Wait for completion with polling
        progress = wait_for_completion(batch_id, max_wait=300, poll_interval=3)
        
        if progress:
            print_success("Progress tracking completed!")
            print_json(progress)
            return progress
        else:
            print_error("Progress tracking failed or timed out")
            return None
    
    except Exception as e:
        print_error(f"Track progress error: {str(e)}")
        return None


def test_08_get_batch_items(batch_id):
    """Test 8: Get Batch Items"""
    print_separator("TEST 8: Get Batch Items")
    
    if not batch_id:
        print_error("No batch_id provided")
        return False
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/batch/{batch_id}/items",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Retrieved {result['total_items']} items")
            print_json(result)
            return True
        else:
            print_error(f"Failed to get items: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Get batch items error: {str(e)}")
        return False


def test_09_download_pdfs(batch_id):
    """Test 9: Get Download URLs"""
    print_separator("TEST 9: Get Download URLs")
    
    if not batch_id:
        print_error("No batch_id provided")
        return False
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/batch/{batch_id}/download",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Retrieved {len(result['pdf_urls'])} PDF URLs")
            print_json(result)
            
            # Print individual URLs
            print_info("\nPDF Download URLs:")
            for i, pdf in enumerate(result['pdf_urls'], 1):
                print(f"  {i}. {pdf['client_data']['full_name']}: {pdf['url'][:80]}...")
            
            return True
        else:
            print_error(f"Failed to get download URLs: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Download PDFs error: {str(e)}")
        return False


def test_10_batch_stats():
    """Test 10: Get Batch Statistics"""
    print_separator("TEST 10: Get Batch Statistics")
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/batch/stats/summary",
            headers=headers
        )
        
        if response.status_code == 200:
            stats = response.json()
            print_success("Batch statistics retrieved!")
            print_json(stats)
            return True
        else:
            print_error(f"Failed to get stats: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Get batch stats error: {str(e)}")
        return False


def test_11_delete_batch(batch_id):
    """Test 11: Delete Batch"""
    print_separator("TEST 11: Delete Batch")
    
    if not batch_id:
        print_error("No batch_id provided")
        return False
    
    try:
        print_info(f"Deleting batch: {batch_id}")
        
        response = requests.delete(
            f"{BASE_URL}/api/batch/{batch_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success("Batch deleted!")
            print_json(result)
            return True
        else:
            print_error(f"Failed to delete batch: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print_error(f"Delete batch error: {str(e)}")
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all batch endpoint tests"""
    print_separator("🚀 BATCH ENDPOINTS - COMPREHENSIVE TEST SUITE")
    print(f"Base URL: {BASE_URL}")
    print(f"Template ID: {TEMPLATE_ID}")
    print(f"CSV File: {CSV_FILE}")
    
    results = {
        'passed': 0,
        'failed': 0,
        'total': 11
    }
    
    batch_id_csv = None
    batch_id_json = None
    
    # Test 1: Health Check
    if test_01_health_check():
        results['passed'] += 1
    else:
        results['failed'] += 1
        print_error("Health check failed - stopping tests")
        return results
    
    # Test 2: Create batch from CSV
    batch_id_csv = test_02_create_batch_from_csv()
    if batch_id_csv:
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 3: Create batch from JSON
    batch_id_json = test_03_create_batch_from_json()
    if batch_id_json:
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Use CSV batch for remaining tests (has more items)
    test_batch_id = batch_id_csv or batch_id_json
    
    if not test_batch_id:
        print_error("No batch created - skipping remaining tests")
        results['failed'] += 8
        return results
    
    print_info(f"\nUsing batch {test_batch_id} for remaining tests...")
    
    # Test 4: Get batch details
    if test_04_get_batch_details(test_batch_id):
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 5: List batches
    if test_05_list_batches():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 6: Start processing
    if test_06_process_batch(test_batch_id):
        results['passed'] += 1
    else:
        results['failed'] += 1
        print_error("Processing failed - skipping progress tracking")
        results['failed'] += 4
        return results
    
    # Test 7: Track progress (waits for completion)
    progress = test_07_track_progress(test_batch_id)
    if progress:
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 8: Get batch items
    if test_08_get_batch_items(test_batch_id):
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 9: Download PDFs
    if test_09_download_pdfs(test_batch_id):
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 10: Get stats
    if test_10_batch_stats():
        results['passed'] += 1
    else:
        results['failed'] += 1
    
    # Test 11: Delete batch (cleanup)
    print_info("\n⚠️  Skipping delete test to preserve batch for inspection")
    print_info(f"To delete manually: DELETE {BASE_URL}/api/batch/{test_batch_id}")
    # if test_11_delete_batch(test_batch_id):
    #     results['passed'] += 1
    # else:
    #     results['failed'] += 1
    
    return results


def print_final_results(results):
    """Print final test results"""
    print_separator("📊 TEST RESULTS")
    
    print(f"\nTotal Tests:  {results['total']}")
    print(f"✅ Passed:    {results['passed']}")
    print(f"❌ Failed:    {results['failed']}")
    print(f"📈 Success:   {results['passed']/results['total']*100:.1f}%")
    
    if results['failed'] == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
    else:
        print(f"\n⚠️  {results['failed']} tests failed")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("\n🧪 Starting Batch Endpoints Test Suite...")
    print("⏰", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    results = run_all_tests()
    print_final_results(results)
    
    print("\n✅ Test suite completed!")
    print("⏰", time.strftime("%Y-%m-%d %H:%M:%S"))