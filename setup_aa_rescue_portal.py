"""
Setup AA Rescue Portal Script
Finds the Lagos State Drivers Licence Application Form template in Supabase
and links it to a public portal slug 'aa-rescue-lagos-license'.
"""

import os
import sys
from dotenv import load_dotenv
from services.supabase_client import get_supabase, init_supabase
from services.portal_service import get_portal_service

load_dotenv()


def setup_portal():
    print("=" * 70)
    print("🚗 BULKFORM: Setting up AA Rescue Driver's Licence Portal")
    print("=" * 70)

    try:
        init_supabase()
        supabase = get_supabase()
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        print("Please ensure SUPABASE_URL and SUPABASE_KEY are set in your environment.")
        return

    # 1. Search for Lagos State template
    print("🔍 Looking for 'Lagos State Drivers Licence Application Form'...")
    res = (
        supabase.table("pdf_templates")
        .select("id, name, user_id, field_mappings")
        .ilike("name", "%Lagos%Licen%")
        .execute()
    )

    template = None
    if res.data:
        template = res.data[0]
        print(f"✅ Found template: '{template['name']}' (ID: {template['id']})")
    else:
        # Search by Driver
        res2 = (
            supabase.table("pdf_templates")
            .select("id, name, user_id, field_mappings")
            .ilike("name", "%Driver%")
            .execute()
        )
        if res2.data:
            template = res2.data[0]
            print(f"✅ Found template: '{template['name']}' (ID: {template['id']})")
        else:
            print("⚠️  Could not automatically find template matching 'Lagos State Drivers Licence'.")
            template_id_input = input("Enter template UUID manually: ").strip()
            if not template_id_input:
                print("Aborting.")
                return
            res3 = supabase.table("pdf_templates").select("id, name, user_id").eq("id", template_id_input).execute()
            if not res3.data:
                print("❌ Template not found in database.")
                return
            template = res3.data[0]

    slug = "aa-rescue-lagos-license"
    name = template.get("name") or "Lagos State Drivers Licence Application Form - AA Rescue"
    description = (
        "Fill out the Lagos State Drivers Licence Application Form online. "
        "This template covers personal information, address details, LASRRA number, "
        "National Identity Number (NIN), licence class, blood group, next of kin, "
        "education and employment status. Complete it fast, print it, and submit for "
        "a new licence or renewal in Lagos State, Nigeria."
    )

    # 2. Check if portal already exists
    existing = supabase.table("form_portals").select("*").eq("slug", slug).execute()
    portal_service = get_portal_service()

    if existing.data:
        portal = existing.data[0]
        print(f"ℹ️  Portal already exists (ID: {portal['id']}). Updating configuration...")
        updated = portal_service.update_portal(
            portal_id=portal["id"],
            user_id=portal["user_id"],
            updates={
                "name": name,
                "description": description,
                "is_active": True,
                "email_settings": {
                    "send_applicant_email": False,
                    "notify_owner": False,
                    "owner_email": "",
                    "subject": "Your Completed Driver's License Application"
                }
            }
        )
        portal = updated or portal
    else:
        print(f"✨ Creating new public portal '{slug}'...")
        portal = portal_service.create_portal(
            user_id=template["user_id"],
            template_id=template["id"],
            name=name,
            slug=slug,
            description=description,
            email_settings={
                "send_applicant_email": False,
                "notify_owner": False,
                "owner_email": "",
                "subject": "Your Completed Driver's License Application"
            }
        )
        print(f"✅ Portal created successfully! (ID: {portal['id']})")

    base_backend = os.getenv("BACKEND_URL", "https://api.bulkform.app")
    base_frontend = os.getenv("FRONTEND_URL", "https://www.bulkform.app")

    live_csv_url = f"{base_backend}/api/public/portals/{slug}/live-feed.csv?token={portal['access_token']}"
    public_form_url = f"{base_frontend}/forms/{slug}/"

    print("\n" + "=" * 70)
    print("🎉 PORTAL READY FOR AA RESCUE!")
    print("=" * 70)
    print(f"🌐 Public Form URL:   {public_form_url}")
    print(f"📊 Live CSV URL:       {live_csv_url}")
    print(f"🔑 Portal Access Token: {portal['access_token']}")
    print("-" * 70)
    print("📋 GOOGLE SHEETS FORMULA (Paste into Cell A1):")
    print(f'   =IMPORTDATA("{live_csv_url}")')
    print("=" * 70 + "\n")


if __name__ == "__main__":
    setup_portal()
