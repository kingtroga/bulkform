# services/entitlement_service.py

import time
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone  # ✅ NEW

from services.supabase_client import get_supabase
from fastapi import HTTPException
from services.template_service import get_template_service

template_service = get_template_service()


def _parse_supabase_timestamp(raw) -> Optional[int]:
    """
    Convert Supabase timestamptz (e.g. '2026-11-22 05:05:05+00') or a unix ts
    into a unix timestamp (int). Returns None if parsing fails.
    """
    if raw is None:
        return None

    try:
        # Already numeric?
        if isinstance(raw, (int, float)):
            return int(raw)

        s = str(raw).strip()
        # Pure integer string?
        if s.isdigit():
            return int(s)

        # Normalize ISO format: space -> 'T'
        s_norm = s.replace(" ", "T")

        # Fix timezone like '+00' into '+00:00' if needed
        for sign in ["+", "-"]:
            idx = s_norm.rfind(sign)
            if idx > 10:
                main = s_norm[:idx]
                tz = s_norm[idx:]
                # e.g. '+00' or '-03'
                if len(tz) == 3:
                    tz = tz + ":00"
                    s_norm = main + tz
                break

        dt = datetime.fromisoformat(s_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return int(dt.timestamp())
    except Exception:
        return None


def ensure_template_single_fill_access(user_id: str, template: dict):
    """
    Flow 1 access rules:
    - Custom template: owner only
    - Official free templates: allow all
    - Paid official templates:
        • Allow if user has active library pass
        • Allow if user purchased this template within validity
    """
    # ----------------------------------------------------------------------
    # 1. CUSTOM TEMPLATES → owner only
    # ----------------------------------------------------------------------
    if not template.get("is_official", False):
        if template.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="You do not own this template.")
        return

    # ----------------------------------------------------------------------
    # 2. OFFICIAL FREE TEMPLATES
    # ----------------------------------------------------------------------
    if template.get("is_free") or (
        template.get("price") in (0, 0.0, None)
        and not template.get("stripe_price_id")
    ):
        return

    # ----------------------------------------------------------------------
    # 3. PAID OFFICIAL TEMPLATES -> check entitlements
    # ----------------------------------------------------------------------
    sb = template_service.supabase

    # ---- 3a. Check Library Pass ----
    try:
        profile_res = (
            sb.table("profiles")
            .select("official_library_pass, official_library_pass_expires_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile = (profile_res.data[0] if profile_res.data else {}) or {}
    except Exception:
        profile = {}

    has_pass = False
    exp_raw = profile.get("official_library_pass_expires_at")
    if profile.get("official_library_pass") and exp_raw:
        exp_ts = _parse_supabase_timestamp(exp_raw)  # ✅ FIXED
        if exp_ts is not None and exp_ts > int(time.time()):
            has_pass = True

    if has_pass:
        return

    # ---- 3b. Check per-template purchase ----
    try:
        purchase_res = (
            sb.table("template_purchases")
            .select("expires_at")
            .eq("profile_id", user_id)
            .eq("template_id", template["id"])
            .limit(1)
            .execute()
        )
        purchase = (purchase_res.data[0] if purchase_res.data else {}) or {}
    except Exception:
        purchase = {}

    exp_raw = purchase.get("expires_at")
    if exp_raw:
        exp_ts = _parse_supabase_timestamp(exp_raw)  # ✅ FIXED
        now = int(time.time())
        if exp_ts is not None and (exp_ts == 0 or exp_ts > now):
            return  # PURCHASE VALID

    # ----------------------------------------------------------------------
    # 4. DENY ACCESS → No pass, no purchase
    # ----------------------------------------------------------------------
    raise HTTPException(
        status_code=402,
        detail="You need to purchase this template or get a Library Pass before you can fill it."
    )


class EntitlementError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class EntitlementService:
    """
    Central place for:
    - Template access (official/free/library pass/purchase)
    - Forms usage (subscription + PAYG)
    """

    def __init__(self):
        self.supabase = get_supabase()

    # ----------------------------------------------------------------------
    # PROFILE HELPERS
    # ----------------------------------------------------------------------
    def _get_profile(self, user_id: str) -> Dict[str, Any]:
        result = (
            self.supabase
            .table("profiles")
            .select(
                "id, subscription_tier, subscription_status, "
                "forms_included_in_plan, forms_used_this_month, "
                "official_library_pass, official_library_pass_expires_at"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise EntitlementError(404, "Profile not found")

        return result.data

    def _has_active_library_pass(self, profile: Dict[str, Any]) -> bool:
        if not profile.get("official_library_pass"):
            return False

        expires = profile.get("official_library_pass_expires_at")
        if not expires:
            return False

        # ✅ FIXED: parse Supabase timestamptz / unix ts safely
        exp_ts = _parse_supabase_timestamp(expires)
        if exp_ts is None:
            return False

        now = int(time.time())
        return exp_ts > now

    # ----------------------------------------------------------------------
    # TEMPLATE ACCESS
    # ----------------------------------------------------------------------
    def user_has_template_access(
        self,
        user_id: str,
        template: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Returns a structured result:

        {
          "has_access": bool,
          "access_via": "owner|free|library_pass|purchase|none",
          "requires_payment": bool,
          "reason": str
        }
        """

        # Custom template: only owner can use it
        if not template.get("is_official", False):
            if template.get("user_id") == user_id:
                return {
                    "has_access": True,
                    "access_via": "owner",
                    "requires_payment": False,
                    "reason": "You own this custom template."
                }
            # RLS should already block this, but be explicit:
            return {
                "has_access": False,
                "access_via": "none",
                "requires_payment": False,
                "reason": "You do not own this template."
            }

        # Official template
        # 1) Completely free template
        if template.get("is_free") or (template.get("price") in (0, 0.0, None) and not template.get("stripe_price_id")):
            return {
                "has_access": True,
                "access_via": "free",
                "requires_payment": False,
                "reason": "This official template is free to use."
            }

        # Fetch profile once
        profile = self._get_profile(user_id)

        # 2) Library pass (covers ALL official templates)
        if self._has_active_library_pass(profile):
            return {
                "has_access": True,
                "access_via": "library_pass",
                "requires_payment": False,
                "reason": "You have an active Library Pass."
            }

        # 3) Per-template purchase
        tpl_id = template.get("id")
        if tpl_id:
            purchase_result = (
                self.supabase
                .table("template_purchases")
                .select("id, expires_at, purchase_type")
                .eq("profile_id", user_id)
                .eq("template_id", tpl_id)
                .single()
                .execute()
            )

            purchase = purchase_result.data
            if purchase:
                expires = purchase.get("expires_at")
                exp_ts = _parse_supabase_timestamp(expires)  # ✅ FIXED
                now = int(time.time())
                if exp_ts is not None and (exp_ts == 0 or exp_ts > now):
                    return {
                        "has_access": True,
                        "access_via": "purchase",
                        "requires_payment": False,
                        "reason": "You purchased this template."
                    }

        # No access
        return {
            "has_access": False,
            "access_via": "none",
            "requires_payment": True,
            "reason": "You need to purchase this template or get a Library Pass."
        }

    def annotate_templates_for_user(
        self,
        user_id: str,
        templates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Adds entitlement info to each template dict for easy frontend use.
        """
        annotated: List[Dict[str, Any]] = []
        for t in templates:
            ent = self.user_has_template_access(user_id, t)
            t_with = dict(t)
            t_with["has_access"] = ent["has_access"]
            t_with["access_via"] = ent["access_via"]
            t_with["requires_payment"] = ent["requires_payment"]
            t_with["access_reason"] = ent["reason"]
            annotated.append(t_with)
        return annotated

    # ----------------------------------------------------------------------
    # FORM USAGE (SUBSCRIPTION + PAYG)
    # ----------------------------------------------------------------------
    def ensure_forms_available(
        self,
        user_id: str,
        forms_needed: int,
    ) -> Dict[str, Any]:
        """
        Ensures the user has enough forms to process N items.
        This is a *reservation* at the point of starting a batch.

        NOTE:
        - Simple version: deduct up-front from `forms_included_in_plan`.
        - You can later refine to log each usage in a separate `usage_records` table.
        """
        if forms_needed <= 0:
            return {"ok": True, "remaining": None}

        profile = self._get_profile(user_id)
        included = profile.get("forms_included_in_plan", 0) or 0
        used = profile.get("forms_used_this_month", 0) or 0

        remaining = included - used
        if remaining < forms_needed:
            raise EntitlementError(
                402,  # Payment Required
                f"Not enough forms. Needed {forms_needed}, but you only have {remaining} available."
            )

        new_used = used + forms_needed

        # Optimistic update
        self.supabase.table("profiles").update(
            {"forms_used_this_month": new_used}
        ).eq("id", user_id).execute()

        return {"ok": True, "remaining": included - new_used}


_entitlement_service: Optional[EntitlementService] = None


def get_entitlement_service() -> EntitlementService:
    global _entitlement_service
    if _entitlement_service is None:
        _entitlement_service = EntitlementService()
    return _entitlement_service
