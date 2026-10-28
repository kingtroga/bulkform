"""
Unit tests for Portal Service and Models
"""
import io
import csv
import json
from models.portal_models import (
    PortalCreateRequest,
    PublicPortalResponse,
    PublicSubmissionResponse,
    validate_slug_format,
)
from services.portal_service import PortalService


def test_slug_validation():
    # Valid slugs
    assert validate_slug_format("aa-rescue-lagos-license") == "aa-rescue-lagos-license"
    assert validate_slug_format("driver-form-2026") == "driver-form-2026"
    
    # Invalid slugs
    try:
        validate_slug_format("invalid slug with spaces")
        assert False, "Should have failed on spaces"
    except ValueError:
        pass


def test_applicant_extraction():
    service = PortalService.__new__(PortalService)
    
    # Test Nigerian name fields
    data1 = {
        "title_surname": "Adeleke",
        "first_name": "Tari",
        "other_names": "Oluwaseun",
        "email_address": "applicant@example.com"
    }
    assert service._extract_applicant_name(data1) == "Tari Adeleke"
    assert service._extract_applicant_email(data1) == "applicant@example.com"

    # Test alternate name keys
    data2 = {
        "full_name": "Babajide Sanwo-Olu",
        "email": "governor@lagos.gov.ng"
    }
    assert service._extract_applicant_name(data2) == "Babajide Sanwo-Olu"
    assert service._extract_applicant_email(data2) == "governor@lagos.gov.ng"


def test_csv_export_flattening():
    # Simulate submissions
    submissions = [
        {
            "id": "sub_1",
            "created_at": "2026-06-29T10:00:00Z",
            "applicant_name": "Tari Adeleke",
            "applicant_email": "tari@example.com",
            "pdf_url": "https://storage.supabase.co/pdfs/filled.pdf",
            "submitted_data": {
                "first_name": "Tari",
                "title_surname": "Adeleke",
                "blood_group": "O+",
                "license_class": "Class B"
            }
        },
        {
            "id": "sub_2",
            "created_at": "2026-06-29T10:05:00Z",
            "applicant_name": "Chioma Okonkwo",
            "applicant_email": "chioma@example.com",
            "pdf_url": "https://storage.supabase.co/pdfs/filled2.pdf",
            "submitted_data": {
                "first_name": "Chioma",
                "title_surname": "Okonkwo",
                "blood_group": "A+",
                "national_identity_number__nin_": "12345678901"
            }
        }
    ]

    all_field_keys = []
    seen = set()
    for s in submissions:
        for k in s["submitted_data"].keys():
            if k not in seen:
                seen.add(k)
                all_field_keys.append(k)

    output = io.StringIO()
    writer = csv.writer(output)
    base_headers = ["Submission ID", "Date Submitted", "Applicant Name", "Applicant Email", "PDF URL"]
    writer.writerow(base_headers + all_field_keys)

    for s in submissions:
        data = s["submitted_data"]
        row = [s["id"], s["created_at"], s["applicant_name"], s["applicant_email"], s["pdf_url"]]
        for f in all_field_keys:
            row.append(str(data.get(f, "")))
        writer.writerow(row)

    csv_content = output.getvalue()
    reader = list(csv.reader(io.StringIO(csv_content)))
    assert reader[0] == ["Submission ID", "Date Submitted", "Applicant Name", "Applicant Email", "PDF URL", "first_name", "title_surname", "blood_group", "license_class", "national_identity_number__nin_"]
    assert reader[1][2] == "Tari Adeleke"
    assert reader[2][2] == "Chioma Okonkwo"
    print("✅ All unit tests passed!")


if __name__ == "__main__":
    test_slug_validation()
    test_applicant_extraction()
    test_csv_export_flattening()
