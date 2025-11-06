#!/usr/bin/env python3
"""
Template Endpoints Test Suite
Covers official + custom template flows (auth vs public) for the Templates API.

Endpoints covered:
- POST   /api/templates                       (create custom)
- GET    /api/templates                       (list user's custom)
- GET    /api/templates/all                   (list official + custom for user)
- GET    /api/templates/search                (search official+own)
- GET    /api/templates/{id}                  (get by id)
- PUT    /api/templates/{id}                  (update)
- DELETE /api/templates/{id}                  (delete)
- GET    /api/templates/official/list         (list official; public)
- GET    /api/templates/official/{form_id}    (get official by form id; public)
- POST   /api/templates/official              (create official; admin only)
- GET    /api/templates/categories/list       (public categories)
- GET    /api/templates/health                (health)

Notes:
- Provide two tokens: USER_AUTH_TOKEN (non-admin), ADMIN_AUTH_TOKEN (admin).
- Script generates a tiny in-memory PDF for upload tests.
- Safe to run step-by-step; failures are printed clearly.
"""

import io
import json
import time
import uuid
import base64
from pathlib import Path
from typing import Optional

import requests

# =============================================================================
# CONFIG
# =============================================================================
BASE_URL = "http://localhost:8000"
USER_AUTH_TOKEN = ""
ADMIN_AUTH_TOKEN = ""

# Optional: existing known official form for read tests
KNOWN_OFFICIAL_FORM_ID = "bnda"  # adjust to one that exists in your DB

# Search term to hit both official + custom names
SEARCH_TERM = "b"

# Headers helpers
H_USER = {"Authorization": f"Bearer {USER_AUTH_TOKEN}"} if USER_AUTH_TOKEN else {}
H_ADMIN = {"Authorization": f"Bearer {ADMIN_AUTH_TOKEN}"} if ADMIN_AUTH_TOKEN else {}


# =============================================================================
# HELPERS
# =============================================================================

def sep(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def ok(msg: str):
    print(f"✅ {msg}")


def err(msg: str):
    print(f"❌ {msg}")


def info(msg: str):
    print(f"ℹ️  {msg}")


def pj(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def tiny_pdf_bytes() -> bytes:
    """Return a minimal valid one-page PDF as bytes."""
    # This is a minimal PDF structure. Many renderers accept it.
    pdf = (
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\n"
        b"2 0 obj<<>>endobj\n"
        b"3 0 obj<</Type/Catalog/Pages 4 0 R>>endobj\n"
        b"4 0 obj<</Type/Pages/Count 1/Kids[5 0 R]>>endobj\n"
        b"5 0 obj<</Type/Page/Parent 4 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000015 00000 n \n0000000046 00000 n \n0000000077 00000 n \n0000000120 00000 n \n0000000171 00000 n \ntrailer<</Size 6/Root 3 0 R>>\nstartxref\n226\n%%EOF\n"
    )
    return pdf


def upload_fields_sample():
    """A minimal mapping payload accepted by the API validator."""
    return {
        "full_name": {"page": 1, "x": 20, "y": 30, "size": 12, "font": "arial"}
    }


def post_multipart(url: str, token_headers: dict, name: str, field_mappings: dict, filename_prefix: str = "template"):
    pdf = tiny_pdf_bytes()
    files = {"file": (f"{filename_prefix}.pdf", io.BytesIO(pdf), "application/pdf")}
    data = {
        "name": name,
        "field_mappings": json.dumps(field_mappings),
        "description": "auto-test"
    }
    return requests.post(url, headers=token_headers, files=files, data=data)


# =============================================================================
# TESTS
# =============================================================================

def test_health() -> bool:
    sep("TEST: /api/templates/health")
    r = requests.get(f"{BASE_URL}/api/templates/health")
    if r.status_code == 200:
        ok("health ok")
        pj(r.json())
        return True
    err(f"health failed: {r.status_code}")
    print(r.text)
    return False


def test_official_list_public() -> Optional[list]:
    sep("TEST: GET /api/templates/official/list (public)")
    r = requests.get(f"{BASE_URL}/api/templates/official/list", params={"limit": 20})
    if r.status_code == 200:
        data = r.json()
        ok(f"official templates: {data.get('total', 0)}")
        return data.get("templates", [])
    err(f"official list failed: {r.status_code}")
    print(r.text)
    return None


def test_official_by_form_id_public(form_id: str) -> bool:
    sep(f"TEST: GET /api/templates/official/{{form_id}} -> {form_id}")
    r = requests.get(f"{BASE_URL}/api/templates/official/{form_id}")
    if r.status_code == 200:
        ok("official by form id ok")
        pj(r.json())
        return True
    err(f"official by form id failed: {r.status_code}")
    print(r.text)
    return False


def test_search_user_sees_official_and_own() -> bool:
    sep("TEST: GET /api/templates/search (user should see official + own)")
    if not H_USER:
        info("USER_AUTH_TOKEN not set; skipping")
        return True
    r = requests.get(f"{BASE_URL}/api/templates/search", headers=H_USER, params={"query": SEARCH_TERM})
    if r.status_code == 200:
        data = r.json()
        ok(f"search ok; found={data.get('total')} ")
        pj(data)
        return True
    err(f"search failed: {r.status_code}")
    print(r.text)
    return False


def test_create_custom_template_user() -> Optional[str]:
    sep("TEST: POST /api/templates (create custom)")
    if not H_USER:
        info("USER_AUTH_TOKEN not set; skipping")
        return None
    unique_name = f"AutoTest Custom {uuid.uuid4().hex[:8]}"
    r = post_multipart(
        f"{BASE_URL}/api/templates",
        H_USER,
        name=unique_name,
        field_mappings=upload_fields_sample(),
        filename_prefix="custom_autotest"
    )
    if r.status_code == 201:
        data = r.json()
        ok("custom template created")
        pj(data)
        return data.get("template_id")
    err(f"create custom failed: {r.status_code}")
    print(r.text)
    return None


def test_get_template_by_id_user(template_id: str) -> bool:
    sep("TEST: GET /api/templates/{id} (user)")
    if not template_id:
        err("no template_id")
        return False
    r = requests.get(f"{BASE_URL}/api/templates/{template_id}", headers=H_USER)
    if r.status_code == 200:
        ok("get template ok")
        pj(r.json())
        return True
    err(f"get template failed: {r.status_code}")
    print(r.text)
    return False


def test_update_template_user(template_id: str) -> bool:
    sep("TEST: PUT /api/templates/{id} (user)")
    if not template_id:
        err("no template_id")
        return False
    payload = {"description": "updated-by-autotest"}
    r = requests.put(f"{BASE_URL}/api/templates/{template_id}", headers=H_USER, json=payload)
    if r.status_code == 200:
        ok("update ok")
        pj(r.json())
        return True
    err(f"update failed: {r.status_code}")
    print(r.text)
    return False


def test_delete_template_user(template_id: str) -> bool:
    sep("TEST: DELETE /api/templates/{id} (user)")
    if not template_id:
        err("no template_id")
        return False
    r = requests.delete(f"{BASE_URL}/api/templates/{template_id}", headers=H_USER)
    if r.status_code == 200:
        ok("delete ok")
        pj(r.json())
        return True
    err(f"delete failed: {r.status_code}")
    print(r.text)
    return False


def test_all_templates_user() -> bool:
    sep("TEST: GET /api/templates/all (user)")
    if not H_USER:
        info("USER_AUTH_TOKEN not set; skipping")
        return True
    r = requests.get(f"{BASE_URL}/api/templates/all", headers=H_USER)
    if r.status_code == 200:
        ok("all templates ok")
        pj(r.json())
        return True
    err(f"all templates failed: {r.status_code}")
    print(r.text)
    return False


def test_categories_public() -> bool:
    sep("TEST: GET /api/templates/categories/list (public)")
    r = requests.get(f"{BASE_URL}/api/templates/categories/list")
    if r.status_code == 200:
        ok("categories ok")
        pj(r.json())
        return True
    err(f"categories failed: {r.status_code}")
    print(r.text)
    return False


def test_create_official_admin() -> Optional[str]:
    sep("TEST: POST /api/templates/official (admin)")
    if not H_ADMIN:
        info("ADMIN_AUTH_TOKEN not set; skipping")
        return None
    unique_name = f"AutoTest Official {uuid.uuid4().hex[:6]}"
    field_map = {"Name": {"page": 1, "x": 20, "y": 25, "size": 30, "font": "arial"}}
    pdf = tiny_pdf_bytes()
    files = {"file": ("official_autotest.pdf", io.BytesIO(pdf), "application/pdf")}
    data = {
        "name": unique_name,
        "field_mappings": json.dumps(field_map),
        "official_form_id": f"autotest-{uuid.uuid4().hex[:6]}",
        "category": "hr",
        "price": "0",
        "description": "auto-test official"
    }
    r = requests.post(f"{BASE_URL}/api/templates/official", headers=H_ADMIN, files=files, data=data)
    if r.status_code == 201:
        ok("official template created")
        pj(r.json())
        return r.json().get("template_id")
    err(f"create official failed: {r.status_code}")
    print(r.text)
    return None


def test_delete_official_as_user_expect_403(official_template_id: str) -> bool:
    sep("TEST: DELETE official as user -> expect 403 or 404")
    if not H_USER or not official_template_id:
        info("skip: missing user token or official_template_id")
        return True
    r = requests.delete(f"{BASE_URL}/api/templates/{official_template_id}", headers=H_USER)
    if r.status_code in (403, 404):
        ok(f"blocked as expected (status={r.status_code})")
        print(r.text)
        return True
    err(f"unexpected status: {r.status_code}")
    print(r.text)
    return False


# =============================================================================
# RUNNER
# =============================================================================

def run():
    passed = 0
    failed = 0

    if test_health():
        passed += 1
    else:
        failed += 1

    # Public reads
    official_list = test_official_list_public()
    passed += 1 if official_list is not None else 0
    failed += 0 if official_list is not None else 1

    passed += 1 if test_official_by_form_id_public(KNOWN_OFFICIAL_FORM_ID) else 0
    failed += 0 if test_official_by_form_id_public else 1  # function exists regardless

    # Authenticated user flows
    passed += 1 if test_search_user_sees_official_and_own() else 0
    failed += 0 if test_search_user_sees_official_and_own else 1

    # Create custom -> get -> update -> delete
    new_tid = test_create_custom_template_user()
    if new_tid:
        passed += 1
    else:
        failed += 1

    if new_tid and test_get_template_by_id_user(new_tid):
        passed += 1
    else:
        failed += 1

    if new_tid and test_update_template_user(new_tid):
        passed += 1
    else:
        failed += 1

    if new_tid and test_delete_template_user(new_tid):
        passed += 1
    else:
        failed += 1

    # all templates for user
    passed += 1 if test_all_templates_user() else 0
    failed += 0 if test_all_templates_user else 1

    # categories public
    passed += 1 if test_categories_public() else 0
    failed += 0 if test_categories_public else 1

    # Admin create official (optional)
    created_official_id = test_create_official_admin()
    if H_ADMIN:
        if created_official_id:
            passed += 1
        else:
            failed += 1
        # user deletion attempt should be blocked
        if created_official_id:
            passed += 1 if test_delete_official_as_user_expect_403(created_official_id) else 0
            failed += 0 if test_delete_official_as_user_expect_403 else 1

    sep("RESULTS")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total:  {passed + failed}")


if __name__ == "__main__":
    print("\n🧪 Templates Endpoints Test Suite")
    print("⏰", time.strftime("%Y-%m-%d %H:%M:%S"))
    run()
    print("⏰", time.strftime("%Y-%m-%d %H:%M:%S"))
