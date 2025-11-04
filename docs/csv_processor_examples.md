# 📊 CSV Processor - Usage Examples

## Quick Start

```python
from services.csv_processor import get_csv_processor

processor = get_csv_processor()
```

---

## Example 1: Basic CSV Parsing

**Scenario:** Parse a simple CSV file with client data

```python
# clients.csv:
# first_name,last_name,email,phone
# John,Smith,john@ex.com,555-0100
# Jane,Doe,jane@ex.com,555-0200

data = processor.parse_csv("clients.csv")

print(data)
# Output:
# [
#   {'first_name': 'John', 'last_name': 'Smith', 'email': 'john@ex.com', 'phone': '555-0100'},
#   {'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@ex.com', 'phone': '555-0200'}
# ]
```

---

## Example 2: Parse Uploaded CSV (API Endpoint)

**Scenario:** User uploads CSV via FastAPI endpoint

```python
from fastapi import UploadFile
import io

@app.post("/upload-csv")
async def upload_csv(file: UploadFile):
    # Read file into BytesIO
    content = await file.read()
    bytes_io = io.BytesIO(content)
    
    # Parse CSV
    data = processor.parse_csv(bytes_io)
    
    return {
        "rows_parsed": len(data),
        "preview": data[:5]  # First 5 rows
    }
```

---

## Example 3: Parse Excel File

**Scenario:** User uploads Excel file with multiple sheets

```python
# Requires: pip install pandas openpyxl

# Parse first sheet (default)
data = processor.parse_excel("clients.xlsx")

# Parse specific sheet by name
data = processor.parse_excel("clients.xlsx", sheet_name="Sheet2")

# Parse specific sheet by index
data = processor.parse_excel("clients.xlsx", sheet_name=1)
```

---

## Example 4: Auto-Detect Format (Smart Parse)

**Scenario:** Don't know if file is CSV or Excel

```python
# Automatically detects format based on extension
data = processor.parse_file("data.csv")    # Uses CSV parser
data = processor.parse_file("data.xlsx")   # Uses Excel parser
data = processor.parse_file("data.tsv")    # Uses TSV parser

# For uploaded files (BytesIO), provide extension hint
content = await file.read()
bytes_io = io.BytesIO(content)
data = processor.parse_file(bytes_io, file_extension=".csv")
```

---

## Example 5: Validate Required Fields

**Scenario:** Ensure CSV has required columns before processing

```python
data = processor.parse_csv("clients.csv")

# Check if required fields are present
required = ["first_name", "last_name", "email"]
is_valid = processor.validate_headers(data, required)

if not is_valid:
    return {"error": "Missing required columns"}

# Continue with processing...
```

---

## Example 6: Clean and Normalize Data

**Scenario:** CSV has messy data (extra spaces, empty rows)

```python
# Raw data:
# [
#   {'name': '  John  ', 'age': None},
#   {'name': '', 'age': ''},         # Empty row
#   {'name': 'Jane', 'age': '25'}
# ]

clean_data = processor.normalize_data(data)

# Result:
# [
#   {'name': 'John', 'age': ''},
#   {'name': 'Jane', 'age': '25'}
# ]
# (empty row removed, whitespace stripped, None → '')
```

---

## Example 7: Map Column Names

**Scenario:** CSV columns don't match template field names

```python
# CSV has: "First Name", "Last Name", "Email Address"
# Template expects: "first_name", "last_name", "email"

data = processor.parse_csv("clients.csv")

mapping = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Email Address": "email"
}

mapped_data = processor.map_columns(data, mapping)

# Now data has template field names!
print(mapped_data[0])
# {'first_name': 'John', 'last_name': 'Smith', 'email': 'john@ex.com'}
```

---

## Example 8: Keep Unmapped Columns

**Scenario:** Want to keep extra columns not in mapping

```python
mapping = {"First Name": "first_name"}

# Without keep_unmapped (default)
data1 = processor.map_columns(data, mapping)
# {'first_name': 'John'}  # Only mapped columns

# With keep_unmapped=True
data2 = processor.map_columns(data, mapping, keep_unmapped=True)
# {'first_name': 'John', 'Last Name': 'Smith', 'Email': 'john@ex.com'}  # All columns
```

---

## Example 9: All-in-One Processing

**Scenario:** Parse, validate, normalize, and map in one call

```python
result = processor.validate_and_parse(
    file_path="clients.csv",
    required_fields=["first_name", "last_name", "email"],
    column_mapping={
        "First Name": "first_name",
        "Last Name": "last_name",
        "Email Address": "email"
    },
    normalize=True
)

if result["errors"]:
    # Handle errors
    print(f"Errors: {result['errors']}")
else:
    # Success! Ready for batch processing
    data = result["data"]
    row_count = result["row_count"]
    
    print(f"Ready to generate {row_count} PDFs!")
    # Pass to batch service...
```

---

## Example 10: Preview Data Before Processing

**Scenario:** Show user sample data for confirmation

```python
data = processor.parse_csv("clients.csv")

# Get first 5 rows as preview
preview = processor.preview_data(data, num_rows=5)

return {
    "total_rows": len(data),
    "preview": preview,
    "message": f"Ready to process {len(data)} PDFs. Confirm?"
}
```

---

## Example 11: Complete Batch Workflow

**Scenario:** User uploads CSV → generate batch of PDFs

```python
from services.csv_processor import get_csv_processor
from services.template_service import get_template_service

@app.post("/batch/create-from-csv")
async def create_batch_from_csv(
    file: UploadFile,
    template_id: str,
    current_user: dict
):
    # Step 1: Get template to know required fields
    template_service = get_template_service()
    template = template_service.get_template(template_id, current_user['id'])
    
    if not template:
        return {"error": "Template not found"}
    
    required_fields = list(template['field_mappings'].keys())
    
    # Step 2: Parse and validate CSV
    processor = get_csv_processor()
    content = await file.read()
    bytes_io = io.BytesIO(content)
    
    result = processor.validate_and_parse(
        file_path=bytes_io,
        required_fields=required_fields,
        file_extension=".csv",
        normalize=True
    )
    
    if result["errors"]:
        return {"error": result["errors"]}
    
    # Step 3: Create batch job
    # (Next step - will implement in Batch Service)
    batch_data = result["data"]
    
    return {
        "message": f"Ready to process {result['row_count']} PDFs",
        "preview": result["data"][:3]
    }
```

---

## Example 12: Handle Different Encodings

**Scenario:** CSV file has non-UTF8 encoding

```python
# Try UTF-8 first
try:
    data = processor.parse_csv("file.csv", encoding='utf-8')
except UnicodeDecodeError:
    # Fall back to Latin-1
    data = processor.parse_csv("file.csv", encoding='latin-1')
```

---

## Example 13: Parse TSV (Tab-separated)

**Scenario:** File uses tabs instead of commas

```python
# Auto-detected if file has .tsv extension
data = processor.parse_file("data.tsv")

# Or specify delimiter manually
data = processor.parse_csv("data.txt", delimiter='\t')
```

---

## Example 14: Get Column Info

**Scenario:** Show user available columns for mapping

```python
data = processor.parse_csv("clients.csv")

# Get list of column names
columns = processor.get_column_names(data)

return {
    "available_columns": columns,
    "message": "Select which columns to map to template fields"
}
```

---

## Example 15: Error Handling

**Scenario:** Gracefully handle various errors

```python
try:
    result = processor.validate_and_parse(
        file_path=file_path,
        required_fields=required,
        normalize=True
    )
    
    if result["errors"]:
        # Validation errors
        return {
            "status": "validation_error",
            "errors": result["errors"]
        }
    
    # Success
    return {
        "status": "success",
        "data": result["data"],
        "count": result["row_count"]
    }

except FileNotFoundError:
    return {"status": "error", "message": "File not found"}

except ValueError as e:
    return {"status": "error", "message": f"Invalid format: {e}"}

except Exception as e:
    return {"status": "error", "message": f"Unexpected error: {e}"}
```

---

## Example 16: Process Large Files

**Scenario:** Handle files with thousands of rows

```python
# Parse normally (processor handles it)
data = processor.parse_csv("large_file.csv")

# Show summary instead of all data
return {
    "total_rows": len(data),
    "columns": processor.get_column_names(data),
    "preview": processor.preview_data(data, num_rows=10),
    "message": f"Ready to process {len(data)} PDFs"
}
```

---

## Example 17: Custom Normalization

**Scenario:** Need specific cleaning rules

```python
# Default normalization
data = processor.normalize_data(data)

# Custom normalization (disable some features)
data = processor.normalize_data(
    data,
    strip_whitespace=True,
    remove_empty_rows=False,  # Keep empty rows
    convert_none_to_empty=False  # Keep None values
)
```

---

## Example 18: Validate Before Upload

**Scenario:** Client-side validation hints

```python
@app.get("/batch/validation-rules")
def get_validation_rules(template_id: str):
    """
    Return required fields so frontend can validate before upload
    """
    template = template_service.get_template(template_id, user_id)
    
    return {
        "required_fields": list(template['field_mappings'].keys()),
        "supported_formats": [".csv", ".xlsx", ".xls", ".tsv"],
        "max_file_size": "10MB",
        "example_csv": {
            "headers": list(template['field_mappings'].keys()),
            "sample_row": {"first_name": "John", "last_name": "Smith"}
        }
    }
```

---

## Common Patterns

### Pattern 1: Upload → Parse → Preview → Confirm

```python
# Step 1: Upload and parse
result = processor.validate_and_parse(file, required_fields)

# Step 2: Show preview to user
preview = result["data"][:5]

# Step 3: User confirms → process batch
if user_confirms:
    create_batch_job(result["data"])
```

### Pattern 2: Template-First Workflow

```python
# Step 1: User selects template
template = get_template(template_id)

# Step 2: Show required fields
required = list(template['field_mappings'].keys())

# Step 3: User uploads CSV with those fields
# Step 4: Validate and process
```

### Pattern 3: Column Mapping UI

```python
# Step 1: Parse CSV
data = processor.parse_csv(file)
columns = processor.get_column_names(data)

# Step 2: Show mapping interface
return {
    "csv_columns": columns,
    "template_fields": template_fields,
    "auto_mapping": auto_suggest_mapping(columns, template_fields)
}

# Step 3: User confirms/adjusts mapping
# Step 4: Apply mapping and process
```

---

## Integration with Other Services

### With Template Service

```python
from services.csv_processor import get_csv_processor
from services.template_service import get_template_service

processor = get_csv_processor()
template_service = get_template_service()

# Get template
template = template_service.get_template(template_id, user_id)

# Parse CSV
data = processor.parse_csv(file)

# Validate against template fields
required = list(template['field_mappings'].keys())
is_valid = processor.validate_headers(data, required)
```

### With Batch Service (Coming Next!)

```python
from services.csv_processor import get_csv_processor
from services.batch_service import get_batch_service

processor = get_csv_processor()
batch_service = get_batch_service()

# Parse CSV
result = processor.validate_and_parse(file, required_fields)

# Create batch job
batch_id = batch_service.create_batch(
    user_id=user_id,
    template_id=template_id,
    items=result["data"]
)
```

---

## Best Practices

1. **Always validate before processing**
   ```python
   result = processor.validate_and_parse(...)
   if result["errors"]:
       return errors
   ```

2. **Normalize data by default**
   ```python
   data = processor.normalize_data(data)
   ```

3. **Show preview to user**
   ```python
   preview = processor.preview_data(data, 5)
   ```

4. **Handle encoding issues**
   ```python
   try:
       data = processor.parse_csv(file, encoding='utf-8')
   except UnicodeDecodeError:
       data = processor.parse_csv(file, encoding='latin-1')
   ```

5. **Use all-in-one method**
   ```python
   # Instead of multiple calls
   result = processor.validate_and_parse(
       file, required_fields, mapping, normalize=True
   )
   ```

---

## Next Steps

- ✅ CSV Processor complete
- ⏳ Build Batch Service (use parsed data)
- ⏳ Build PDF Service (fill PDFs with data)
- ⏳ Create API endpoints (CSV upload → batch generation)

---

**Ready to use!** 🚀