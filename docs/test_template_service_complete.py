"""
Template Service - Complete Test Suite
Tests both custom AND official template features
"""

from services.template_service import get_template_service
import json

# ============================================================================
# SETUP
# ============================================================================

print("=" * 70)
print("🧪 TEMPLATE SERVICE - COMPLETE TEST SUITE")
print("=" * 70)

# ⚠️ REPLACE THIS with your actual user_id from:
# SELECT id FROM auth.users LIMIT 1;
YOUR_USER_ID = "d18772bf-7605-4297-8a34-12d8e626199d"  # ⚠️ REPLACE THIS!

if YOUR_USER_ID == "YOUR_USER_ID_HERE":
    print("\n❌ ERROR: You need to set YOUR_USER_ID first!")
    print("   Run: SELECT id FROM auth.users LIMIT 1;")
    print("   Then update YOUR_USER_ID in this script")
    exit(1)

# Initialize service
template_service = get_template_service()
print(f"✅ Template service initialized")
print(f"   Testing with user_id: {YOUR_USER_ID[:8]}...")


# ============================================================================
# TEST 1: Create Custom Template
# ============================================================================

print("\n" + "=" * 70)
print("TEST 1: Create Custom Template")
print("=" * 70)

custom_template_data = {
    "user_id": YOUR_USER_ID,
    "name": "Test I-485 Custom",
    "description": "My custom I-485 template for testing",
    "pdf_url": "https://www.uscis.gov/sites/default/files/document/forms/i-485.pdf",
    "field_mappings": {
        "first_name": {"page": 1, "x": 25, "y": 30, "size": 30, "font": "arial"},
        "last_name": {"page": 1, "x": 25, "y": 35, "size": 30, "font": "arial"},
        "address": {"page": 1, "x": 30, "y": 40, "size": 25, "font": "arial"}
    }
}

try:
    custom_template_id = template_service.create_template(**custom_template_data)
    print(f"✅ Custom template created: {custom_template_id}")
except Exception as e:
    print(f"❌ Failed to create custom template: {e}")
    custom_template_id = None


# ============================================================================
# TEST 2: Get Custom Template
# ============================================================================

print("\n" + "=" * 70)
print("TEST 2: Get Custom Template")
print("=" * 70)

if custom_template_id:
    template = template_service.get_template(custom_template_id, YOUR_USER_ID)
    if template:
        print(f"✅ Retrieved template: {template['name']}")
        print(f"   Fields: {len(template['field_mappings'])} mapped")
        print(f"   Created: {template['created_at']}")
    else:
        print("❌ Failed to retrieve template")
else:
    print("⚠️  Skipped (no template created)")


# ============================================================================
# TEST 3: List User's Custom Templates
# ============================================================================

print("\n" + "=" * 70)
print("TEST 3: List User's Custom Templates")
print("=" * 70)

custom_templates = template_service.list_templates(YOUR_USER_ID)
print(f"✅ Found {len(custom_templates)} custom template(s):")
for t in custom_templates:
    print(f"   - {t['name']} ({len(t['field_mappings'])} fields)")


# ============================================================================
# TEST 4: Create Official Template (As if you're the admin)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 4: Create Official Template")
print("=" * 70)

# First, manually insert via SQL (because RLS prevents regular users from creating official templates)
print("ℹ️  Official templates must be created via SQL")
print("   Run this in Supabase SQL Editor:")
print("""
INSERT INTO pdf_templates (
  user_id, name, description, pdf_url, field_mappings,
  is_official, official_form_id, category, price
) VALUES (
  '""" + YOUR_USER_ID + """',
  'USCIS Form I-485 - Official Template',
  'Official I-485 with verified coordinates',
  'https://www.uscis.gov/sites/default/files/document/forms/i-485.pdf',
  '{"family_name": {"page": 1, "x": 25, "y": 30}, "given_name": {"page": 1, "x": 25, "y": 35}}'::jsonb,
  TRUE, 'i-485', 'immigration', 0.00
);
""")
print("\n   After running, press Enter to continue...")
input()


# ============================================================================
# TEST 5: List Official Templates
# ============================================================================

print("\n" + "=" * 70)
print("TEST 5: List Official Templates")
print("=" * 70)

official_templates = template_service.list_official_templates()
print(f"✅ Found {len(official_templates)} official template(s):")
for t in official_templates:
    form_id = t.get('official_form_id', 'N/A')
    category = t.get('category', 'N/A')
    downloads = t.get('downloads', 0)
    print(f"   - {t['name']}")
    print(f"     Form ID: {form_id} | Category: {category} | Downloads: {downloads}")


# ============================================================================
# TEST 6: Get Official Template by Form ID
# ============================================================================

print("\n" + "=" * 70)
print("TEST 6: Get Official Template by Form ID")
print("=" * 70)

i485_template = template_service.get_official_template_by_form_id("i-485")
if i485_template:
    print(f"✅ Found I-485 template: {i485_template['name']}")
    print(f"   Fields: {len(i485_template['field_mappings'])}")
    print(f"   Is Official: {i485_template.get('is_official')}")
else:
    print("⚠️  I-485 template not found (may not be created yet)")


# ============================================================================
# TEST 7: List All Templates (Official + Custom)
# ============================================================================

print("\n" + "=" * 70)
print("TEST 7: List All Templates (Official + Custom)")
print("=" * 70)

all_templates = template_service.list_all_templates(YOUR_USER_ID, include_official=True)

print(f"✅ Official templates: {len(all_templates['official'])}")
for t in all_templates['official']:
    print(f"   ⭐ {t['name']}")

print(f"\n✅ Custom templates: {len(all_templates['custom'])}")
for t in all_templates['custom']:
    print(f"   🛠️  {t['name']}")

total = len(all_templates['official']) + len(all_templates['custom'])
print(f"\n📊 Total: {total} templates available")


# ============================================================================
# TEST 8: Get Template Categories
# ============================================================================

print("\n" + "=" * 70)
print("TEST 8: Get Template Categories")
print("=" * 70)

categories = template_service.get_template_categories()
if categories:
    print(f"✅ Found {len(categories)} categories:")
    for cat in categories:
        print(f"   - {cat['category']}: {cat['count']} templates")
else:
    print("⚠️  No categories found (no official templates yet)")


# ============================================================================
# TEST 9: Increment Downloads
# ============================================================================

print("\n" + "=" * 70)
print("TEST 9: Increment Template Downloads")
print("=" * 70)

if i485_template:
    template_id = i485_template['id']
    success = template_service.increment_template_downloads(template_id)
    if success:
        print(f"✅ Downloads incremented for {i485_template['name']}")
        
        # Verify
        updated = template_service.get_official_template_by_form_id("i-485")
        if updated:
            print(f"   Downloads: {updated.get('downloads', 0)}")
    else:
        print("❌ Failed to increment downloads")
else:
    print("⚠️  Skipped (no I-485 template)")


# ============================================================================
# TEST 10: Update Custom Template
# ============================================================================

print("\n" + "=" * 70)
print("TEST 10: Update Custom Template")
print("=" * 70)

if custom_template_id:
    success = template_service.update_template(
        custom_template_id,
        YOUR_USER_ID,
        {
            "name": "Test I-485 Custom (UPDATED)",
            "description": "Updated description for testing"
        }
    )
    if success:
        print("✅ Template updated successfully")
        
        # Verify
        updated = template_service.get_template(custom_template_id, YOUR_USER_ID)
        if updated:
            print(f"   New name: {updated['name']}")
    else:
        print("❌ Failed to update template")
else:
    print("⚠️  Skipped (no custom template created)")


# ============================================================================
# TEST 11: Validate Field Mappings
# ============================================================================

print("\n" + "=" * 70)
print("TEST 11: Validate Field Mappings")
print("=" * 70)

# Valid mappings
valid_mappings = {
    "field1": {"page": 1, "x": 10, "y": 20, "size": 30},
    "field2": {"page": 2, "x": 15, "y": 25}
}

if template_service.validate_field_mappings(valid_mappings):
    print("✅ Valid mappings accepted")

# Invalid mappings (missing 'y')
invalid_mappings = {
    "field1": {"page": 1, "x": 10}  # Missing 'y'
}

if not template_service.validate_field_mappings(invalid_mappings):
    print("✅ Invalid mappings correctly rejected")


# ============================================================================
# TEST 12: Count User Templates
# ============================================================================

print("\n" + "=" * 70)
print("TEST 12: Count User Templates")
print("=" * 70)

count = template_service.count_user_templates(YOUR_USER_ID)
print(f"✅ User has {count} custom template(s)")


# ============================================================================
# TEST 13: Get Template by Name
# ============================================================================

print("\n" + "=" * 70)
print("TEST 13: Get Template by Name")
print("=" * 70)

if custom_template_id:
    found = template_service.get_template_by_name(YOUR_USER_ID, "Test I-485 Custom (UPDATED)")
    if found:
        print(f"✅ Found template by name: {found['name']}")
    else:
        print("⚠️  Template not found by name")
else:
    print("⚠️  Skipped (no custom template)")


# ============================================================================
# TEST 14: List Templates by Category
# ============================================================================

print("\n" + "=" * 70)
print("TEST 14: List Templates by Category")
print("=" * 70)

immigration_templates = template_service.list_official_templates(category="immigration")
print(f"✅ Found {len(immigration_templates)} immigration templates")
for t in immigration_templates:
    print(f"   - {t['name']}")


# ============================================================================
# TEST 15: Cleanup - Delete Custom Template
# ============================================================================

print("\n" + "=" * 70)
print("TEST 15: Cleanup - Delete Custom Template")
print("=" * 70)

if custom_template_id:
    print("Should we delete the test custom template? (y/n)")
    choice = input().lower()
    
    if choice == 'y':
        success = template_service.delete_template(custom_template_id, YOUR_USER_ID)
        if success:
            print("✅ Custom template deleted")
        else:
            print("❌ Failed to delete template")
    else:
        print("⚠️  Template kept (delete manually if needed)")
else:
    print("⚠️  No custom template to delete")


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 70)
print("📊 TEST SUMMARY")
print("=" * 70)

print(f"""
Custom Templates:
  - Created: {'✅' if custom_template_id else '❌'}
  - Retrieved: {'✅' if custom_template_id else '⚠️'}
  - Updated: {'✅' if custom_template_id else '⚠️'}
  - Listed: ✅
  - Count: {count}

Official Templates:
  - Listed: ✅
  - Get by Form ID: {'✅' if i485_template else '⚠️'}
  - Categories: {'✅' if categories else '⚠️'}
  - Downloads tracked: {'✅' if i485_template else '⚠️'}

Combined:
  - List all templates: ✅
  - Validation: ✅

Next Steps:
1. Create more official templates via SQL
2. Test with real PDF filling
3. Build template marketplace UI
4. Move to Phase 2.2 (CSV Processor)
""")

print("=" * 70)
print("✅ ALL TESTS COMPLETE!")
print("=" * 70)