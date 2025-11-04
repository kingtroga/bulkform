"""
CSV Processor Service
Handles parsing and processing of CSV/Excel files for batch PDF generation

Use cases:
1. User uploads CSV with client data (name, address, DOB, etc.)
2. System maps CSV columns to PDF template fields
3. Batch generates PDFs for each row

Example workflow:
    csv_file = "clients.csv"  # Has columns: first_name, last_name, address
    template_fields = ["first_name", "last_name", "address", "city"]
    
    processor = CSVProcessor()
    data = processor.parse_csv(csv_file)
    # Returns: [
    #   {"first_name": "John", "last_name": "Smith", "address": "123 Main St"},
    #   {"first_name": "Jane", "last_name": "Doe", "address": "456 Oak Ave"}
    # ]
"""

import csv
import pandas as pd
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import io


class CSVProcessor:
    """Service for processing CSV and Excel files for batch PDF generation"""
    
    def __init__(self):
        """Initialize CSV processor"""
        self.supported_formats = ['.csv', '.xlsx', '.xls', '.tsv']
        print("✅ CSV Processor initialized")
    
    
    def parse_csv(
        self,
        file_path: Union[str, Path, io.BytesIO],
        encoding: str = 'utf-8',
        delimiter: str = ','
    ) -> List[Dict[str, Any]]:
        """
        Parse CSV file into list of dictionaries
        
        Args:
            file_path: Path to CSV file or file-like object (BytesIO)
            encoding: File encoding (default: 'utf-8')
            delimiter: CSV delimiter (default: ',')
            
        Returns:
            List of dictionaries, one per row
            
        Example:
            processor.parse_csv("clients.csv")
            # Returns:
            # [
            #   {"first_name": "John", "last_name": "Smith", "age": "30"},
            #   {"first_name": "Jane", "last_name": "Doe", "age": "25"}
            # ]
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If CSV is malformed
        """
        try:
            # Handle different input types
            if isinstance(file_path, io.BytesIO):
                # File uploaded via API (bytes)
                file_path.seek(0)  # Reset to start
                content = file_path.read().decode(encoding)
                reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            else:
                # File path (string or Path)
                file_path = Path(file_path)
                if not file_path.exists():
                    raise FileNotFoundError(f"CSV file not found: {file_path}")
                
                with open(file_path, 'r', encoding=encoding, newline='') as f:
                    reader = csv.DictReader(f, delimiter=delimiter)
                    data = list(reader)
                    
                print(f"✅ Parsed CSV: {len(data)} rows, {len(data[0]) if data else 0} columns")
                return data
            
            # For BytesIO, read data here
            data = list(reader)
            print(f"✅ Parsed CSV from upload: {len(data)} rows")
            return data
        
        except UnicodeDecodeError as e:
            print(f"❌ Encoding error: {e}")
            raise ValueError(f"File encoding error. Try encoding='latin-1' or 'iso-8859-1'")
        
        except csv.Error as e:
            print(f"❌ CSV parsing error: {e}")
            raise ValueError(f"Invalid CSV format: {e}")
        
        except Exception as e:
            print(f"❌ Failed to parse CSV: {str(e)}")
            raise
    
    
    def parse_excel(
        self,
        file_path: Union[str, Path, io.BytesIO],
        sheet_name: Optional[Union[str, int]] = 0
    ) -> List[Dict[str, Any]]:
        """
        Parse Excel file (.xlsx, .xls) into list of dictionaries
        
        Args:
            file_path: Path to Excel file or file-like object
            sheet_name: Sheet name or index (default: 0 = first sheet)
            
        Returns:
            List of dictionaries, one per row
            
        Example:
            processor.parse_excel("clients.xlsx")
            # Returns same format as parse_csv
            
        Note:
            Requires pandas and openpyxl/xlrd:
            pip install pandas openpyxl xlrd
        """
        try:
            # Read Excel file with pandas
            if isinstance(file_path, io.BytesIO):
                file_path.seek(0)
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            else:
                file_path = Path(file_path)
                if not file_path.exists():
                    raise FileNotFoundError(f"Excel file not found: {file_path}")
                
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # Convert NaN to None, then to list of dicts
            df = df.where(pd.notna(df), None)
            data = df.to_dict('records')
            
            print(f"✅ Parsed Excel: {len(data)} rows, {len(df.columns)} columns")
            print(f"   Sheet: {sheet_name if isinstance(sheet_name, str) else f'Index {sheet_name}'}")
            
            return data
        
        except ImportError:
            print("❌ pandas not installed. Install with: pip install pandas openpyxl")
            raise Exception("Excel support requires pandas. Install with: pip install pandas openpyxl")
        
        except Exception as e:
            print(f"❌ Failed to parse Excel: {str(e)}")
            raise
    
    
    def parse_file(
        self,
        file_path: Union[str, Path, io.BytesIO],
        file_extension: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Smart parser - automatically detects CSV vs Excel
        
        Args:
            file_path: Path to file or file-like object
            file_extension: Optional extension hint (e.g., '.csv', '.xlsx')
                           Required if file_path is BytesIO
            
        Returns:
            List of dictionaries
            
        Example:
            # Automatically detects format
            data = processor.parse_file("data.csv")
            data = processor.parse_file("data.xlsx")
            
            # For uploaded files (BytesIO)
            data = processor.parse_file(uploaded_file, file_extension='.csv')
        """
        try:
            # Determine file type
            if isinstance(file_path, io.BytesIO):
                if not file_extension:
                    raise ValueError("file_extension required for BytesIO objects")
                ext = file_extension.lower()
            else:
                ext = Path(file_path).suffix.lower()
            
            # Check if supported
            if ext not in self.supported_formats:
                raise ValueError(
                    f"Unsupported file format: {ext}. "
                    f"Supported: {', '.join(self.supported_formats)}"
                )
            
            # Parse based on type
            if ext == '.csv':
                return self.parse_csv(file_path)
            elif ext == '.tsv':
                return self.parse_csv(file_path, delimiter='\t')
            elif ext in ['.xlsx', '.xls']:
                return self.parse_excel(file_path)
            else:
                raise ValueError(f"Unknown file extension: {ext}")
        
        except Exception as e:
            print(f"❌ Failed to parse file: {str(e)}")
            raise
    
    
    def validate_headers(
        self,
        data: List[Dict[str, Any]],
        required_fields: List[str],
        strict: bool = False
    ) -> bool:
        """
        Validate that CSV/Excel has required columns
        
        Args:
            data: Parsed data (list of dicts)
            required_fields: List of required column names
            strict: If True, file must have ONLY required fields (no extra)
            
        Returns:
            True if valid, False otherwise
            
        Example:
            data = processor.parse_csv("clients.csv")
            is_valid = processor.validate_headers(
                data,
                required_fields=["first_name", "last_name", "email"]
            )
        """
        if not data:
            print("❌ Empty data - cannot validate headers")
            return False
        
        # Get actual columns from first row
        actual_columns = set(data[0].keys())
        required_set = set(required_fields)
        
        # Check missing fields
        missing = required_set - actual_columns
        if missing:
            print(f"❌ Missing required columns: {', '.join(missing)}")
            return False
        
        # Check extra fields (if strict mode)
        if strict:
            extra = actual_columns - required_set
            if extra:
                print(f"❌ Unexpected columns (strict mode): {', '.join(extra)}")
                return False
        
        print(f"✅ Headers validated: {len(required_fields)} required fields present")
        return True
    
    
    def normalize_data(
        self,
        data: List[Dict[str, Any]],
        strip_whitespace: bool = True,
        remove_empty_rows: bool = True,
        convert_none_to_empty: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Clean and normalize parsed data
        
        Args:
            data: Raw parsed data
            strip_whitespace: Remove leading/trailing spaces from strings
            remove_empty_rows: Remove rows where all values are None/empty
            convert_none_to_empty: Convert None values to empty strings
            
        Returns:
            Cleaned data
            
        Example:
            raw_data = [
                {"name": "  John  ", "age": None},
                {"name": None, "age": None},  # Empty row
                {"name": "Jane", "age": "25"}
            ]
            
            clean = processor.normalize_data(raw_data)
            # Returns:
            # [
            #   {"name": "John", "age": ""},
            #   {"name": "Jane", "age": "25"}
            # ]
        """
        normalized = []
        
        for row in data:
            # Check if row is completely empty
            if remove_empty_rows:
                if all(v is None or str(v).strip() == '' for v in row.values()):
                    continue
            
            # Process each field
            clean_row = {}
            for key, value in row.items():
                # Convert None to empty string
                if value is None:
                    clean_row[key] = '' if convert_none_to_empty else None
                    continue
                
                # Strip whitespace from strings
                if strip_whitespace and isinstance(value, str):
                    clean_row[key] = value.strip()
                else:
                    clean_row[key] = value
            
            normalized.append(clean_row)
        
        removed = len(data) - len(normalized)
        print(f"✅ Data normalized: {len(normalized)} rows")
        if removed > 0:
            print(f"   Removed {removed} empty row(s)")
        
        return normalized
    
    
    def map_columns(
        self,
        data: List[Dict[str, Any]],
        column_mapping: Dict[str, str],
        keep_unmapped: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Map CSV column names to template field names
        
        Args:
            data: Parsed data with original column names
            column_mapping: Dict mapping CSV columns to template fields
                Example: {"First Name": "first_name", "Last Name": "last_name"}
            keep_unmapped: If True, include columns not in mapping
            
        Returns:
            Data with renamed columns
            
        Example:
            data = [{"First Name": "John", "Last Name": "Smith", "Extra": "data"}]
            
            mapping = {"First Name": "first_name", "Last Name": "last_name"}
            
            mapped = processor.map_columns(data, mapping)
            # Returns: [{"first_name": "John", "last_name": "Smith"}]
            
            mapped = processor.map_columns(data, mapping, keep_unmapped=True)
            # Returns: [{"first_name": "John", "last_name": "Smith", "Extra": "data"}]
        """
        mapped_data = []
        
        for row in data:
            mapped_row = {}
            
            # Map specified columns
            for csv_col, template_field in column_mapping.items():
                if csv_col in row:
                    mapped_row[template_field] = row[csv_col]
                else:
                    print(f"⚠️  Column '{csv_col}' not found in row, setting to empty")
                    mapped_row[template_field] = ''
            
            # Keep unmapped columns if requested
            if keep_unmapped:
                for key, value in row.items():
                    if key not in column_mapping:
                        mapped_row[key] = value
            
            mapped_data.append(mapped_row)
        
        print(f"✅ Columns mapped: {len(column_mapping)} field(s)")
        return mapped_data
    
    
    def get_column_names(
        self,
        data: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Get list of column names from parsed data
        
        Args:
            data: Parsed data
            
        Returns:
            List of column names
            
        Example:
            data = [{"first_name": "John", "last_name": "Smith"}]
            columns = processor.get_column_names(data)
            # Returns: ["first_name", "last_name"]
        """
        if not data:
            return []
        
        columns = list(data[0].keys())
        print(f"✅ Found {len(columns)} columns: {', '.join(columns)}")
        return columns
    
    
    def preview_data(
        self,
        data: List[Dict[str, Any]],
        num_rows: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get preview of first N rows
        
        Args:
            data: Full dataset
            num_rows: Number of rows to preview (default: 5)
            
        Returns:
            First N rows
            
        Useful for:
            - Showing user sample data before batch processing
            - Verifying column mapping
            - Quick data inspection
        """
        preview = data[:num_rows]
        print(f"✅ Preview: Showing {len(preview)} of {len(data)} rows")
        return preview
    
    
    def count_rows(self, data: List[Dict[str, Any]]) -> int:
        """
        Count number of data rows
        
        Args:
            data: Parsed data
            
        Returns:
            Number of rows
        """
        count = len(data)
        print(f"✅ Total rows: {count}")
        return count
    
    
    def validate_and_parse(
        self,
        file_path: Union[str, Path, io.BytesIO],
        required_fields: List[str],
        column_mapping: Optional[Dict[str, str]] = None,
        file_extension: Optional[str] = None,
        normalize: bool = True
    ) -> Dict[str, Any]:
        """
        All-in-one: Parse, validate, normalize, and map data
        
        Args:
            file_path: Path to file or BytesIO
            required_fields: Required template fields
            column_mapping: Optional column name mapping
            file_extension: Required if file_path is BytesIO
            normalize: Whether to clean data (default: True)
            
        Returns:
            Dict with:
                - data: Processed data ready for batch
                - columns: List of column names
                - row_count: Number of rows
                - errors: List of validation errors (empty if valid)
            
        Example:
            result = processor.validate_and_parse(
                file_path="clients.csv",
                required_fields=["first_name", "last_name"],
                column_mapping={"First Name": "first_name", "Last Name": "last_name"}
            )
            
            if result["errors"]:
                print(f"Errors: {result['errors']}")
            else:
                print(f"Ready to process {result['row_count']} PDFs!")
                data = result["data"]
        """
        result = {
            "data": [],
            "columns": [],
            "row_count": 0,
            "errors": []
        }
        
        try:
            # Step 1: Parse file
            print(f"\n📄 Step 1/5: Parsing file...")
            data = self.parse_file(file_path, file_extension)
            
            if not data:
                result["errors"].append("File is empty or contains no data")
                return result
            
            # Step 2: Get columns
            print(f"\n📋 Step 2/5: Reading columns...")
            columns = self.get_column_names(data)
            result["columns"] = columns
            
            # Step 3: Map columns if mapping provided
            if column_mapping:
                print(f"\n🗺️  Step 3/5: Mapping columns...")
                data = self.map_columns(data, column_mapping)
            else:
                print(f"\n⏭️  Step 3/5: Skipping column mapping (none provided)")
            
            # Step 4: Normalize data
            if normalize:
                print(f"\n🧹 Step 4/5: Cleaning data...")
                data = self.normalize_data(data)
            else:
                print(f"\n⏭️  Step 4/5: Skipping normalization")
            
            # Step 5: Validate required fields
            print(f"\n✅ Step 5/5: Validating required fields...")
            if not self.validate_headers(data, required_fields):
                # Get missing fields
                actual = set(data[0].keys()) if data else set()
                missing = set(required_fields) - actual
                result["errors"].append(f"Missing required fields: {', '.join(missing)}")
                return result
            
            # Success!
            result["data"] = data
            result["row_count"] = len(data)
            
            print(f"\n🎉 Success! Ready to process {result['row_count']} items")
            
            return result
        
        except Exception as e:
            result["errors"].append(str(e))
            print(f"\n❌ Validation failed: {str(e)}")
            return result


# ============================================================================
# CONVENIENCE FUNCTION - Easy import
# ============================================================================

def get_csv_processor() -> CSVProcessor:
    """Get CSV processor instance"""
    return CSVProcessor()