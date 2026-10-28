"""
Portal Service
Handles logic for public intake portals, anonymous submissions,
PDF generation, email notification triggers, and live spreadsheet feeds.
"""

import os
import io
import csv
import json
import uuid
import secrets
import base64
import tempfile
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from services.supabase_client import get_supabase
from services.template_service import get_template_service
from routes.batch.batch_processing import fill_single_pdf_sync


class PortalService:
    def __init__(self):
        self.supabase = get_supabase()
        self.template_service = get_template_service()

    # =========================================================================
    # PORTAL CRUD & MANAGEMENT
    # =========================================================================

    def create_portal(
        self,
        user_id: str,
        template_id: str,
        name: str,
        slug: str,
        description: Optional[str] = None,
        email_settings: Optional[Dict[str, Any]] = None,
        sheet_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new public form portal"""
        # Check if slug exists
        existing = (
            self.supabase.table("form_portals")
            .select("id")
            .eq("slug", slug.strip().lower())
            .execute()
        )
        if existing.data:
            raise ValueError(f"Portal slug '{slug}' is already taken.")

        # Verify template exists
        template = self.template_service.get_template(template_id, user_id)
        if not template:
            # Check official templates
            template = (
                self.supabase.table("pdf_templates")
                .select("id, name")
                .eq("id", template_id)
                .execute()
            )
            if not template.data:
                raise ValueError("Template not found.")

        access_token = secrets.token_hex(24)
        email_cfg = email_settings or {
            "send_applicant_email": False,
            "notify_owner": False,
            "owner_email": "",
            "subject": f"Your Completed Document - {name}"
        }
        sheet_cfg = sheet_settings or {
            "google_sheet_url": None,
            "webhook_url": None
        }

        payload = {
            "user_id": user_id,
            "template_id": template_id,
            "name": name.strip(),
            "slug": slug.strip().lower(),
            "description": description.strip() if description else None,
            "is_active": True,
            "email_settings": email_cfg,
            "sheet_settings": sheet_cfg,
            "access_token": access_token,
            "total_submissions": 0
        }

        result = self.supabase.table("form_portals").insert(payload).execute()
        if not result.data:
            raise Exception("Failed to create portal.")
        return result.data[0]

    def get_portal_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve public portal metadata by slug"""
        res = (
            self.supabase.table("form_portals")
            .select("*")
            .eq("slug", slug.strip().lower())
            .eq("is_active", True)
            .execute()
        )
        if not res.data:
            return None
        portal = res.data[0]

        # Retrieve template field info
        template = (
            self.supabase.table("pdf_templates")
            .select("id, name, field_mappings, field_order, pdf_url")
            .eq("id", portal["template_id"])
            .execute()
        )
        if template.data:
            portal["template"] = template.data[0]
        else:
            portal["template"] = None

        return portal

    def get_portal_by_id(self, portal_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get portal by ID verifying ownership"""
        res = (
            self.supabase.table("form_portals")
            .select("*, pdf_templates(name)")
            .eq("id", portal_id)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_portal_by_token(self, portal_id: str, access_token: str) -> Optional[Dict[str, Any]]:
        """Get portal by ID and secure access token (for live export feeds)"""
        res = (
            self.supabase.table("form_portals")
            .select("*")
            .eq("id", portal_id)
            .eq("access_token", access_token)
            .execute()
        )
        return res.data[0] if res.data else None

    def list_user_portals(self, user_id: str) -> List[Dict[str, Any]]:
        """List all portals owned by a user"""
        res = (
            self.supabase.table("form_portals")
            .select("*, pdf_templates(name)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    def update_portal(self, portal_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update portal settings"""
        valid_fields = ["name", "description", "is_active", "email_settings", "sheet_settings"]
        clean_updates = {k: v for k, v in updates.items() if k in valid_fields and v is not None}
        if not clean_updates:
            return self.get_portal_by_id(portal_id, user_id)

        clean_updates["updated_at"] = datetime.utcnow().isoformat()
        res = (
            self.supabase.table("form_portals")
            .update(clean_updates)
            .eq("id", portal_id)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data[0] if res.data else None

    # =========================================================================
    # PUBLIC SUBMISSION & PDF GENERATION
    # =========================================================================

    def process_public_submission(
        self,
        slug: str,
        form_data: Dict[str, Any],
        uploaded_files: Optional[Dict[str, Tuple[str, bytes]]] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process an anonymous submission:
        1. Resolve portal & template
        2. Handle text, signatures, and uploaded images
        3. Fill PDF via fill_single_pdf_sync
        4. Save submission record
        5. Trigger email or webhook notifications if configured
        """
        portal = self.get_portal_by_slug(slug)
        if not portal:
            raise ValueError(f"Portal '{slug}' not found or inactive.")

        template_id = portal["template_id"]
        template = self.template_service.get_template(template_id, portal["user_id"])
        if not template:
            # Fallback to direct DB query (e.g. for official templates)
            t_res = self.supabase.table("pdf_templates").select("*").eq("id", template_id).execute()
            if not t_res.data:
                raise ValueError("Template for this portal could not be loaded.")
            template = t_res.data[0]

        field_mappings = template.get("field_mappings", {})
        client_data = dict(form_data)
        temp_files_to_cleanup = []

        try:
            # Handle uploaded files (e.g. passport photo, signature file)
            if uploaded_files:
                for field_name, (filename, file_bytes) in uploaded_files.items():
                    if file_bytes:
                        suffix = os.path.splitext(filename)[1] or ".png"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(file_bytes)
                            client_data[field_name] = tmp.name
                            temp_files_to_cleanup.append(tmp.name)

            # Handle base64 data URLs in client_data (e.g., signature pads sending data:image/png;base64,...)
            for field_name, field_config in field_mappings.items():
                val = client_data.get(field_name)
                if isinstance(val, str) and val.startswith("data:image/") and ";base64," in val:
                    header, b64_str = val.split(";base64,", 1)
                    ext = ".png"
                    if "image/jpeg" in header or "image/jpg" in header:
                        ext = ".jpg"
                    img_bytes = base64.b64decode(b64_str)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(img_bytes)
                        client_data[field_name] = tmp.name
                        temp_files_to_cleanup.append(tmp.name)

            # Extract applicant identification for record keeping
            applicant_name = self._extract_applicant_name(client_data)
            applicant_email = self._extract_applicant_email(client_data)

            # Fill PDF synchronously using established engine
            submission_uuid = str(uuid.uuid4())
            render_res = fill_single_pdf_sync(
                template=template,
                client_data=client_data,
                user_id=portal["user_id"],
                batch_id=f"portal_{portal['id']}",
                item_index=int(datetime.utcnow().timestamp())
            )

            pdf_url = render_res["storage_url"]
            storage_path = render_res["storage_path"]

            # Sanitize client_data before saving to DB (remove local temp file paths)
            saved_data = {}
            for k, v in client_data.items():
                if isinstance(v, str) and (v.startswith(tempfile.gettempdir()) or "tmp" in v):
                    saved_data[k] = "[Attached Image File]"
                else:
                    saved_data[k] = v

            # Insert into form_submissions table
            submission_record = {
                "id": submission_uuid,
                "portal_id": portal["id"],
                "template_id": template["id"],
                "user_id": portal["user_id"],
                "applicant_name": applicant_name,
                "applicant_email": applicant_email,
                "submitted_data": saved_data,
                "pdf_url": pdf_url,
                "storage_path": storage_path,
                "ip_address": ip_address,
                "created_at": datetime.utcnow().isoformat()
            }
            self.supabase.table("form_submissions").insert(submission_record).execute()

            # Handle optional email & webhook dispatch (best effort, non-blocking)
            self._dispatch_notifications(portal, submission_record, pdf_url)

            return {
                "status": "success",
                "message": "Your form has been processed successfully.",
                "submission_id": submission_uuid,
                "pdf_url": pdf_url,
                "applicant_name": applicant_name,
                "created_at": submission_record["created_at"]
            }

        finally:
            for tmp_path in temp_files_to_cleanup:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception as clean_err:
                    print(f"⚠️  Cleanup warning: {clean_err}")

    # =========================================================================
    # SPREADSHEET EXPORTS (CSV / XLSX / LIVE FEED)
    # =========================================================================

    def get_submissions(self, portal_id: str, limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch paginated submissions for a portal"""
        res = (
            self.supabase.table("form_submissions")
            .select("*", count="exact")
            .eq("portal_id", portal_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return (res.data or [], res.count or 0)

    def export_csv_data(self, portal_id: str) -> str:
        """
        Export all submissions for a portal into a CSV string.
        Flattens submitted_data so each form field is a dedicated column.
        Ideal for Excel and Google Sheets '=IMPORTDATA("...")'
        """
        submissions_res = (
            self.supabase.table("form_submissions")
            .select("*")
            .eq("portal_id", portal_id)
            .order("created_at", desc=False)
            .execute()
        )
        submissions = submissions_res.data or []
        if not submissions:
            return "Submission ID,Date,Applicant Name,Applicant Email,PDF URL\n"

        # Determine all unique form keys across all submissions
        all_field_keys = []
        seen_keys = set()
        for s in submissions:
            data = s.get("submitted_data", {})
            for k in data.keys():
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_field_keys.append(k)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        base_headers = ["Submission ID", "Date Submitted", "Applicant Name", "Applicant Email", "PDF URL"]
        writer.writerow(base_headers + all_field_keys)

        # Data rows
        for s in submissions:
            data = s.get("submitted_data", {})
            row = [
                s.get("id"),
                s.get("created_at"),
                s.get("applicant_name") or "",
                s.get("applicant_email") or "",
                s.get("pdf_url")
            ]
            for field in all_field_keys:
                val = data.get(field, "")
                if isinstance(val, (dict, list)):
                    row.append(json.dumps(val))
                else:
                    row.append(str(val) if val is not None else "")
            writer.writerow(row)

        return output.getvalue()

    def export_excel_data(self, portal_id: str) -> bytes:
        """Export submissions to an Excel (.xlsx) workbook"""
        import pandas as pd
        csv_str = self.export_csv_data(portal_id)
        df = pd.read_csv(io.StringIO(csv_str))

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Submissions")
        return output.getvalue()

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _extract_applicant_name(self, client_data: Dict[str, Any]) -> str:
        """Extract applicant name from common field naming conventions"""
        first = client_data.get("first_name") or client_data.get("firstname") or ""
        last = (
            client_data.get("title_surname")
            or client_data.get("surname")
            or client_data.get("last_name")
            or client_data.get("lastname")
            or ""
        )
        full = f"{first} {last}".strip()
        if full:
            return full
        for key in ["full_name", "fullname", "name", "applicant_name"]:
            if client_data.get(key):
                return str(client_data[key]).strip()
        return "Anonymous Applicant"

    def _extract_applicant_email(self, client_data: Dict[str, Any]) -> Optional[str]:
        """Extract applicant email if provided"""
        for key in ["email_address", "email", "applicant_email"]:
            val = client_data.get(key)
            if val and "@" in str(val):
                return str(val).strip()
        return None

    def _dispatch_notifications(self, portal: Dict[str, Any], submission: Dict[str, Any], pdf_url: str):
        """Dispatches optional notifications based on portal email & sheet settings"""
        email_settings = portal.get("email_settings") or {}
        sheet_settings = portal.get("sheet_settings") or {}

        # 1. Webhook trigger (if AA Rescue supplied a webhook or Zapier URL)
        webhook_url = sheet_settings.get("webhook_url")
        if webhook_url:
            asyncio.create_task(self._send_webhook(webhook_url, submission))

        # 2. Email settings check
        send_applicant = email_settings.get("send_applicant_email", False)
        notify_owner = email_settings.get("notify_owner", False)
        owner_email = email_settings.get("owner_email")
        applicant_email = submission.get("applicant_email")

        # Log intended email action (SMTP dispatch can be connected to provider when configured)
        if send_applicant and applicant_email:
            print(f"📧 [Portal Email] Sending PDF copy to applicant: {applicant_email} ({pdf_url[:60]}...)")
        if notify_owner and owner_email:
            print(f"📧 [Portal Email] Notifying portal owner: {owner_email} of new submission {submission['id']}")

    async def _send_webhook(self, url: str, data: Dict[str, Any]):
        """Post submission payload to external webhook"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=data)
                print(f"✅ Webhook delivered to {url}")
        except Exception as e:
            print(f"⚠️  Webhook delivery failed: {e}")


# Singleton instance
_portal_service = None

def get_portal_service() -> PortalService:
    global _portal_service
    if _portal_service is None:
        _portal_service = PortalService()
    return _portal_service
