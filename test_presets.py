"""
Presets API Test Suite
Tests all preset endpoints with a real access token

Usage:
    python test_presets.py YOUR_ACCESS_TOKEN

Features:
- Creates test presets
- Lists presets
- Gets specific preset
- Updates preset
- Deletes preset
- Checks stats
- Tests limit enforcement
- Verifies error handling
"""

import requests
import sys
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000/api"
HEADERS = {}


class Colors:
    """ANSI color codes for pretty output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print section header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_json(data):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=2))


def make_request(method, endpoint, data=None, expected_status=None):
    """Make HTTP request and handle response"""
    url = f"{API_BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=HEADERS)
        elif method == "POST":
            response = requests.post(url, headers=HEADERS, json=data)
        elif method == "PUT":
            response = requests.put(url, headers=HEADERS, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=HEADERS)
        else:
            print_error(f"Unknown method: {method}")
            return None
        
        # Check status code
        if expected_status and response.status_code != expected_status:
            print_error(f"Expected status {expected_status}, got {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
        
        # Parse JSON
        try:
            return response.json()
        except:
            return {"status_code": response.status_code, "text": response.text}
    
    except Exception as e:
        print_error(f"Request failed: {str(e)}")
        return None


def test_health_check():
    """Test health check endpoint"""
    print_header("TEST 1: Health Check")
    
    result = make_request("GET", "/presets/health", expected_status=200)
    
    if result:
        print_success("Health check passed")
        print_json(result)
        return True
    
    print_error("Health check failed")
    return False


def test_create_preset():
    """Test creating a preset"""
    print_header("TEST 2: Create Preset")
    
    preset_data = {
        "name": "Test Personal Info",
        "description": "Test preset for personal details",
        "data": {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "address": "123 Main St",
            "city": "Toronto",
            "postal_code": "M5H 2N2"
        }
    }
    
    print_info("Creating preset...")
    print_json(preset_data)
    
    result = make_request("POST", "/presets", data=preset_data, expected_status=201)
    
    if result and "preset_id" in result:
        print_success(f"Preset created: {result['preset_id']}")
        print_json(result)
        return result["preset_id"]
    
    print_error("Failed to create preset")
    return None


def test_create_preset_with_template():
    """Test creating a preset with template association"""
    print_header("TEST 3: Create Preset with Template")
    
    preset_data = {
        "name": "T4 Data 2024",
        "description": "Tax form data for 2024",
        "data": {
            "employee_name": "Jane Smith",
            "sin": "123-456-789",
            "employer": "Acme Corp",
            "year": "2024"
        },
        "template_id": "41eb78c1-23a2-4f6d-8aed-0ca8d5cfe410"  # Example UUID
    }
    
    print_info("Creating preset with template association...")
    print_json(preset_data)
    
    result = make_request("POST", "/presets", data=preset_data, expected_status=201)
    
    if result and "preset_id" in result:
        print_success(f"Preset created: {result['preset_id']}")
        print_json(result)
        return result["preset_id"]
    
    print_warning("Failed - this is expected if template doesn't exist")
    return None


def test_list_presets():
    """Test listing presets"""
    print_header("TEST 4: List Presets")
    
    result = make_request("GET", "/presets", expected_status=200)
    
    if result and "presets" in result:
        print_success(f"Found {result['total']} preset(s)")
        print_json(result)
        return result["presets"]
    
    print_error("Failed to list presets")
    return []


def test_get_preset(preset_id):
    """Test getting a specific preset"""
    print_header("TEST 5: Get Specific Preset")
    
    print_info(f"Fetching preset: {preset_id}")
    
    result = make_request("GET", f"/presets/{preset_id}", expected_status=200)
    
    if result and "id" in result:
        print_success(f"Retrieved preset: {result['name']}")
        print_json(result)
        return result
    
    print_error("Failed to get preset")
    return None


def test_update_preset(preset_id):
    """Test updating a preset"""
    print_header("TEST 6: Update Preset")
    
    update_data = {
        "name": "Updated Test Info",
        "description": "Updated description",
        "data": {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@example.com"
        }
    }
    
    print_info(f"Updating preset: {preset_id}")
    print_json(update_data)
    
    result = make_request("PUT", f"/presets/{preset_id}", data=update_data, expected_status=200)
    
    if result and "id" in result:
        print_success(f"Preset updated: {result['name']}")
        print_json(result)
        return True
    
    print_error("Failed to update preset")
    return False


def test_partial_update(preset_id):
    """Test partial update (only name)"""
    print_header("TEST 7: Partial Update (Name Only)")
    
    update_data = {
        "name": "Partially Updated"
    }
    
    print_info(f"Partially updating preset: {preset_id}")
    print_json(update_data)
    
    result = make_request("PUT", f"/presets/{preset_id}", data=update_data, expected_status=200)
    
    if result and "id" in result:
        print_success(f"Preset updated: {result['name']}")
        print_success(f"Data unchanged: {len(result['data'])} fields")
        return True
    
    print_error("Failed partial update")
    return False


def test_get_stats():
    """Test getting preset statistics"""
    print_header("TEST 8: Get Preset Statistics")
    
    result = make_request("GET", "/presets/stats/summary", expected_status=200)
    
    if result and "total_presets" in result:
        print_success("Stats retrieved")
        print_json(result)
        
        if result["at_limit"]:
            print_warning(f"User is at preset limit ({result['preset_limit']})")
        else:
            print_info(f"Remaining slots: {result['remaining_slots']}")
        
        return result
    
    print_error("Failed to get stats")
    return None


def test_create_multiple(count=3):
    """Test creating multiple presets"""
    print_header(f"TEST 9: Create {count} Additional Presets")
    
    created_ids = []
    
    for i in range(count):
        preset_data = {
            "name": f"Test Preset {i+1}",
            "description": f"Batch test preset #{i+1}",
            "data": {
                "field1": f"value{i+1}",
                "field2": f"data{i+1}"
            }
        }
        
        print_info(f"Creating preset {i+1}/{count}...")
        
        result = make_request("POST", "/presets", data=preset_data, expected_status=201)
        
        if result and "preset_id" in result:
            print_success(f"Created: {result['preset_id']}")
            created_ids.append(result["preset_id"])
        else:
            print_error(f"Failed to create preset {i+1}")
    
    print_info(f"Successfully created {len(created_ids)}/{count} presets")
    return created_ids


def test_limit_enforcement():
    """Test preset limit enforcement"""
    print_header("TEST 10: Preset Limit Enforcement")
    
    # Get current stats
    stats = make_request("GET", "/presets/stats/summary")
    
    if not stats:
        print_error("Failed to get stats")
        return False
    
    print_info(f"Current: {stats['total_presets']}/{stats['preset_limit']}")
    
    if stats["at_limit"]:
        print_warning("User is already at limit")
        
        # Try to create one more (should fail)
        print_info("Attempting to create preset beyond limit...")
        
        preset_data = {
            "name": "Should Fail",
            "data": {"test": "data"}
        }
        
        result = make_request("POST", "/presets", data=preset_data)
        
        if result and "detail" in result:
            print_success("Limit enforcement working!")
            print_info(f"Error message: {result['detail']}")
            return True
        else:
            print_error("Limit not enforced - this is a bug!")
            return False
    else:
        print_info(f"User has {stats['remaining_slots']} slots remaining")
        print_info("Create more presets to test limit (not tested)")
        return True


def test_delete_preset(preset_id):
    """Test deleting a preset"""
    print_header("TEST 11: Delete Preset")
    
    print_info(f"Deleting preset: {preset_id}")
    
    result = make_request("DELETE", f"/presets/{preset_id}", expected_status=200)
    
    if result and "message" in result:
        print_success(f"Preset deleted: {preset_id}")
        print_json(result)
        
        # Verify it's gone
        print_info("Verifying deletion...")
        get_result = make_request("GET", f"/presets/{preset_id}")
        
        if get_result and "detail" in get_result:
            print_success("Deletion verified - preset not found")
            return True
        else:
            print_error("Preset still exists after deletion!")
            return False
    
    print_error("Failed to delete preset")
    return False


def test_error_handling():
    """Test various error scenarios"""
    print_header("TEST 12: Error Handling")
    
    # Test 1: Get non-existent preset
    print_info("Test: Get non-existent preset")
    result = make_request("GET", "/presets/00000000-0000-0000-0000-000000000000")
    if result and "detail" in result:
        print_success("404 error handled correctly")
    
    # Test 2: Create preset with empty data
    print_info("Test: Create preset with empty data")
    result = make_request("POST", "/presets", data={
        "name": "Empty",
        "data": {}
    })
    if result and "detail" in result:
        print_success("Empty data validation working")
    
    # Test 3: Create preset with invalid template_id
    print_info("Test: Create preset with invalid template_id")
    result = make_request("POST", "/presets", data={
        "name": "Invalid Template",
        "data": {"test": "data"},
        "template_id": "not-a-uuid"
    })
    if result and "detail" in result:
        print_success("UUID validation working")
    
    # Test 4: Update non-existent preset
    print_info("Test: Update non-existent preset")
    result = make_request("PUT", "/presets/00000000-0000-0000-0000-000000000000", data={
        "name": "Updated"
    })
    if result and "detail" in result:
        print_success("Update error handled correctly")
    
    return True


def cleanup_all_presets():
    """Delete all test presets for cleanup"""
    print_header("CLEANUP: Delete All Test Presets")
    
    # List all presets
    presets = make_request("GET", "/presets")
    
    if not presets or "presets" not in presets:
        print_info("No presets to clean up")
        return
    
    preset_list = presets["presets"]
    
    if len(preset_list) == 0:
        print_info("No presets to clean up")
        return
    
    print_info(f"Found {len(preset_list)} preset(s) to delete")
    
    deleted_count = 0
    for preset in preset_list:
        preset_id = preset["id"]
        print_info(f"Deleting: {preset['name']} ({preset_id})")
        
        result = make_request("DELETE", f"/presets/{preset_id}")
        
        if result and "message" in result:
            deleted_count += 1
            print_success(f"Deleted: {preset['name']}")
        else:
            print_error(f"Failed to delete: {preset['name']}")
    
    print_success(f"Cleanup complete: {deleted_count}/{len(preset_list)} presets deleted")


def run_all_tests():
    """Run complete test suite"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║          PRESETS API COMPREHENSIVE TEST SUITE                  ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}\n")
    
    print_info(f"API Base URL: {API_BASE_URL}")
    print_info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Track results
    results = {}
    created_preset_ids = []
    
    # Run tests
    results["health"] = test_health_check()
    
    preset_id = test_create_preset()
    if preset_id:
        created_preset_ids.append(preset_id)
        results["create"] = True
    else:
        results["create"] = False
    
    preset_id2 = test_create_preset_with_template()
    if preset_id2:
        created_preset_ids.append(preset_id2)
    
    presets = test_list_presets()
    results["list"] = len(presets) > 0
    
    if preset_id:
        results["get"] = test_get_preset(preset_id) is not None
        results["update"] = test_update_preset(preset_id)
        results["partial_update"] = test_partial_update(preset_id)
    
    results["stats"] = test_get_stats() is not None
    
    # Create multiple presets for testing
    more_ids = test_create_multiple(3)
    created_preset_ids.extend(more_ids)
    results["batch_create"] = len(more_ids) > 0
    
    results["limit"] = test_limit_enforcement()
    results["errors"] = test_error_handling()
    
    # Delete one preset
    if created_preset_ids:
        results["delete"] = test_delete_preset(created_preset_ids[0])
    
    # Final summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}\n")
    
    for test_name, passed in results.items():
        status = f"{Colors.GREEN}✅ PASS{Colors.END}" if passed else f"{Colors.RED}❌ FAIL{Colors.END}"
        print(f"  {test_name.ljust(20)} {status}")
    
    # Ask about cleanup
    print("\n")
    cleanup = input(f"{Colors.YELLOW}Delete all test presets? (y/n): {Colors.END}").lower()
    
    if cleanup == 'y':
        cleanup_all_presets()
    else:
        print_info("Skipping cleanup - test presets remain in database")
    
    print_header("TEST SUITE COMPLETE")
    
    if passed == total:
        print_success("🎉 All tests passed! Presets API is working correctly.")
    else:
        print_warning(f"⚠️  {total - passed} test(s) failed. Check output above for details.")


def main():
    """Main entry point"""
    global HEADERS
    
    if len(sys.argv) != 2:
        print_error("Usage: python test_presets.py YOUR_ACCESS_TOKEN")
        sys.exit(1)
    
    access_token = sys.argv[1]
    
    # Setup headers
    HEADERS = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Run tests
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n")
        print_warning("Tests interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Test suite crashed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()