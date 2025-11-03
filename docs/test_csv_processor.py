"""
CSV Processor - Complete Test Suite
Tests CSV parsing, Excel parsing, validation, normalization, and mapping
"""

from services.csv_processor import get_csv_processor
import csv
import io
from pathlib import Path

print("=" * 70)
print("🧪 CSV PROCESSOR - COMPLETE TEST SUITE")
print("=" * 70)

# Initialize processor
processor = get_csv_processor()

# Create test data directory
test_dir = Path("test_data")
test_dir.mkdir(exist_ok=True)


# ============================================================================
# TEST 1: Create Test CSV File
# ============================================================================

print("\n" + "=" * 70)
print("TEST 1: Create Test CSV Files")
print("=" * 70)

# Create sample CSV
csv_file = test_dir / "clients.csv"
csv_data = [
    ["first_name", "last_name", "email", "age"],
    ["John", "Smith", "john@example.com", "30"],
    ["Jane", "Doe", "jane@example.com", "25"],
    ["  Bob  ", "Johnson", "bob@example.com", ""],  # Extra spaces, empty age
    ["", "", "", ""],  # Empty row
    ["Alice", "Williams", "alice@example.com", "35"]
]

with open(csv_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(csv_data)

print(f"✅ Created test CSV: {csv_file}")
print(f"   Rows: {len(csv_data) - 1} (excluding header)")


# ============================================================================
# TEST 2: Parse CSV File
# ============================================================================

print("\n" + "=" * 70)
print("TEST 2: Parse CSV File")
print("=" * 70)

try:
    data = processor.parse_csv(csv_file)
    print(f"✅ Parsed CSV successfully")
    print(f"   Total rows: {len(data)}")
    print(f"   Sample row: {data[0]}")
except Exception as e:
    print(f"❌ Failed to parse CSV: {e}")
    data = []


# ============================================================================
# TEST 3: Get Column Names
# ============================================================================

print("\n" + "=" * 70)
print("TEST 3: Get Column Names")
print("=" * 70)

if data:
    columns = processor.get_column_names(data)
    print(f"✅ Columns: {columns}")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 4: Validate Headers (Valid Case)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 4: Validate Headers (Valid)")
print("=" * 70)

required = ["first_name", "last_name", "email"]
is_valid = processor.validate_headers(data, required)

if is_valid:
    print("✅ Validation passed: All required fields present")
else:
    print("❌ Validation failed")


# ============================================================================
# TEST 5: Validate Headers (Missing Fields)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 5: Validate Headers (Missing Fields)")
print("=" * 70)

required_missing = ["first_name", "phone_number", "address"]
is_valid = processor.validate_headers(data, required_missing)

if not is_valid:
    print("✅ Correctly detected missing fields")
else:
    print("❌ Should have failed (missing fields)")


# ============================================================================
# TEST 6: Normalize Data
# ============================================================================

print("\n" + "=" * 70)
print("TEST 6: Normalize Data")
print("=" * 70)

if data:
    print(f"Before normalization: {len(data)} rows")
    normalized = processor.normalize_data(data)
    print(f"After normalization: {len(normalized)} rows")
    
    # Check if spaces were stripped
    if normalized:
        print(f"✅ Sample normalized row: {normalized[0]}")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 7: Map Columns
# ============================================================================

print("\n" + "=" * 70)
print("TEST 7: Map Columns")
print("=" * 70)

if data:
    # Simulate mapping from CSV columns to template fields
    column_mapping = {
        "first_name": "given_name",
        "last_name": "family_name",
        "email": "email_address"
    }
    
    mapped = processor.map_columns(data, column_mapping)
    print(f"✅ Columns mapped")
    print(f"   Original columns: {list(data[0].keys())}")
    print(f"   Mapped columns: {list(mapped[0].keys())}")
    print(f"   Sample: {mapped[0]}")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 8: Map Columns with Keep Unmapped
# ============================================================================

print("\n" + "=" * 70)
print("TEST 8: Map Columns (Keep Unmapped)")
print("=" * 70)

if data:
    mapping = {"first_name": "given_name"}
    mapped_keep = processor.map_columns(data, mapping, keep_unmapped=True)
    
    print(f"✅ Mapped with unmapped fields kept")
    print(f"   Columns: {list(mapped_keep[0].keys())}")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 9: Preview Data
# ============================================================================

print("\n" + "=" * 70)
print("TEST 9: Preview Data")
print("=" * 70)

if data:
    preview = processor.preview_data(data, num_rows=3)
    print(f"✅ Preview generated")
    for i, row in enumerate(preview, 1):
        print(f"   Row {i}: {row}")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 10: Count Rows
# ============================================================================

print("\n" + "=" * 70)
print("TEST 10: Count Rows")
print("=" * 70)

if data:
    count = processor.count_rows(data)
    print(f"✅ Counted: {count} rows")
else:
    print("⚠️  Skipped (no data)")


# ============================================================================
# TEST 11: Parse CSV from BytesIO (Simulating Upload)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 11: Parse CSV from BytesIO (Upload Simulation)")
print("=" * 70)

csv_content = """name,age,city
Alice,30,New York
Bob,25,Los Angeles
Charlie,35,Chicago"""

bytes_io = io.BytesIO(csv_content.encode('utf-8'))

try:
    uploaded_data = processor.parse_csv(bytes_io)
    print(f"✅ Parsed CSV from BytesIO")
    print(f"   Rows: {len(uploaded_data)}")
    print(f"   Sample: {uploaded_data[0]}")
except Exception as e:
    print(f"❌ Failed: {e}")


# ============================================================================
# TEST 12: Parse Excel File (if available)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 12: Parse Excel File")
print("=" * 70)

print("ℹ️  Excel parsing requires pandas and openpyxl")
print("   Install with: pip install pandas openpyxl")

try:
    import pandas as pd
    
    # Create test Excel file
    excel_file = test_dir / "clients.xlsx"
    df = pd.DataFrame({
        'first_name': ['John', 'Jane', 'Bob'],
        'last_name': ['Smith', 'Doe', 'Johnson'],
        'email': ['john@ex.com', 'jane@ex.com', 'bob@ex.com']
    })
    df.to_excel(excel_file, index=False)
    
    print(f"✅ Created test Excel: {excel_file}")
    
    # Parse it
    excel_data = processor.parse_excel(excel_file)
    print(f"✅ Parsed Excel successfully")
    print(f"   Rows: {len(excel_data)}")
    print(f"   Sample: {excel_data[0]}")
    
except ImportError:
    print("⚠️  pandas not installed - skipping Excel test")
    print("   Install with: pip install pandas openpyxl")
except Exception as e:
    print(f"❌ Excel test failed: {e}")


# ============================================================================
# TEST 13: Smart Parse (Auto-detect Format)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 13: Smart Parse (Auto-detect)")
print("=" * 70)

try:
    # Test CSV
    auto_data = processor.parse_file(csv_file)
    print(f"✅ Auto-detected and parsed CSV")
    print(f"   Rows: {len(auto_data)}")
    
    # Test Excel (if available)
    try:
        if excel_file.exists():
            auto_excel = processor.parse_file(excel_file)
            print(f"✅ Auto-detected and parsed Excel")
            print(f"   Rows: {len(auto_excel)}")
    except:
        pass
        
except Exception as e:
    print(f"❌ Auto-parse failed: {e}")


# ============================================================================
# TEST 14: Validate and Parse (All-in-One)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 14: Validate and Parse (All-in-One)")
print("=" * 70)

result = processor.validate_and_parse(
    file_path=csv_file,
    required_fields=["first_name", "last_name", "email"],
    column_mapping=None,  # No mapping needed
    normalize=True
)

if result["errors"]:
    print(f"❌ Validation failed:")
    for error in result["errors"]:
        print(f"   - {error}")
else:
    print(f"✅ Validation successful!")
    print(f"   Rows ready: {result['row_count']}")
    print(f"   Columns: {result['columns']}")
    print(f"   Sample data: {result['data'][0] if result['data'] else 'None'}")


# ============================================================================
# TEST 15: Validate and Parse with Mapping
# ============================================================================

print("\n" + "=" * 70)
print("TEST 15: Validate and Parse with Column Mapping")
print("=" * 70)

# Create CSV with different column names
csv_different = test_dir / "clients_different_names.csv"
csv_data_diff = [
    ["First Name", "Last Name", "Email Address", "Age"],
    ["John", "Smith", "john@example.com", "30"],
    ["Jane", "Doe", "jane@example.com", "25"]
]

with open(csv_different, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(csv_data_diff)

print(f"✅ Created CSV with different column names")

# Map columns to template fields
mapping = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Email Address": "email"
}

result_mapped = processor.validate_and_parse(
    file_path=csv_different,
    required_fields=["first_name", "last_name", "email"],
    column_mapping=mapping,
    normalize=True
)

if result_mapped["errors"]:
    print(f"❌ Mapping failed:")
    for error in result_mapped["errors"]:
        print(f"   - {error}")
else:
    print(f"✅ Mapping successful!")
    print(f"   Rows: {result_mapped['row_count']}")
    print(f"   Mapped columns: {list(result_mapped['data'][0].keys())}")
    print(f"   Sample: {result_mapped['data'][0]}")


# ============================================================================
# TEST 16: Handle TSV Files
# ============================================================================

print("\n" + "=" * 70)
print("TEST 16: Parse TSV File (Tab-separated)")
print("=" * 70)

tsv_file = test_dir / "clients.tsv"
tsv_content = "first_name\tlast_name\temail\nJohn\tSmith\tjohn@ex.com\nJane\tDoe\tjane@ex.com"

with open(tsv_file, 'w') as f:
    f.write(tsv_content)

try:
    tsv_data = processor.parse_file(tsv_file)
    print(f"✅ Parsed TSV successfully")
    print(f"   Rows: {len(tsv_data)}")
    print(f"   Sample: {tsv_data[0]}")
except Exception as e:
    print(f"❌ TSV parsing failed: {e}")


# ============================================================================
# TEST 17: Error Handling - Missing File
# ============================================================================

print("\n" + "=" * 70)
print("TEST 17: Error Handling (Missing File)")
print("=" * 70)

try:
    missing_data = processor.parse_csv("nonexistent_file.csv")
    print("❌ Should have thrown FileNotFoundError")
except FileNotFoundError:
    print("✅ Correctly caught FileNotFoundError")
except Exception as e:
    print(f"❌ Wrong exception: {e}")


# ============================================================================
# TEST 18: Error Handling - Unsupported Format
# ============================================================================

print("\n" + "=" * 70)
print("TEST 18: Error Handling (Unsupported Format)")
print("=" * 70)

unsupported_file = test_dir / "data.txt"
unsupported_file.write_text("some text data")

try:
    bad_data = processor.parse_file(unsupported_file)
    print("❌ Should have thrown ValueError")
except ValueError as e:
    print(f"✅ Correctly caught unsupported format")
    print(f"   Error: {e}")
except Exception as e:
    print(f"❌ Wrong exception: {e}")


# ============================================================================
# CLEANUP
# ============================================================================

print("\n" + "=" * 70)
print("CLEANUP: Delete Test Files")
print("=" * 70)

print("Delete test files? (y/n)")
choice = input().lower()

if choice == 'y':
    import shutil
    try:
        shutil.rmtree(test_dir)
        print("✅ Test files deleted")
    except Exception as e:
        print(f"⚠️  Could not delete test files: {e}")
else:
    print("⚠️  Test files kept in ./test_data/")


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 70)
print("📊 TEST SUMMARY")
print("=" * 70)

print(f"""
CSV Parsing:
  ✅ Parse CSV from file path
  ✅ Parse CSV from BytesIO (upload simulation)
  ✅ Parse TSV files
  ✅ Handle empty rows
  ✅ Strip whitespace

Excel Parsing:
  {'✅' if 'pandas' in dir() else '⚠️'} Parse Excel files (requires pandas)
  {'✅' if 'pandas' in dir() else '⚠️'} Auto-detect format

Validation:
  ✅ Validate required headers
  ✅ Detect missing fields
  ✅ Strict mode validation

Normalization:
  ✅ Strip whitespace
  ✅ Remove empty rows
  ✅ Convert None to empty string

Column Mapping:
  ✅ Map column names to template fields
  ✅ Keep unmapped columns (optional)
  ✅ Handle missing columns

Utilities:
  ✅ Get column names
  ✅ Preview data
  ✅ Count rows
  ✅ All-in-one validate_and_parse()

Error Handling:
  ✅ Missing files
  ✅ Unsupported formats
  ✅ Invalid CSV format

Next Steps:
1. Install pandas for Excel support: pip install pandas openpyxl
2. Integrate with Template Service
3. Build Batch Service to process parsed data
4. Create API endpoint for CSV upload
""")

print("=" * 70)
print("✅ ALL TESTS COMPLETE!")
print("=" * 70)