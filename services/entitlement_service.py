# services/entitlement_service.py

import time
from typing import Dict, Any, List, Tuple, Optional

from services.supabase_client import get_supabase
from fastapi import HTTPException
from services.template_service import get_template_service

template_service = get_template_service()


def ensure_template_single_fill_access(user_id: str, template: dict):
    """
    Flow 1 access rules:

    - Custom template:
        - Only the owner (template.user_id) can use it.
    - Official template:
        - If is_free or price == 0 and no stripe_price_id → free for all signed-in users.
        - Otherwise, user must have:
            - active Library Pass, OR
            - active annual purchase for this template.
    """
    # 1) Custom templates → owner only
    if not template.get("is_official", False):
        if template.get("user_id") != user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this template."
            )
        return

    # 2) Official templates that are free
    if template.get("is_free") or (
        template.get("price") in (0, 0.0, None)
        and not template.get("stripe_price_id")
    ):
        # Any signed-in user can use free official templates
        return

    # 3) Official paid templates → check Library Pass, then per-template purchase
    # Use the same Supabase client already hanging off template_service
    sb = template_service.supabase

    # 3a) Library Pass check
    profile_res = (
        sb
        .table("profiles")
        .select("official_library_pass, official_library_pass_expires_at")
        .eq("id", user_id)
        .single()
        .execute()
    )
    profile = profile_res.data or {}

    has_pass = False
    if profile.get("official_library_pass"):
        exp_raw = profile.get("official_library_pass_expires_at")
        try:
            exp_ts = int(exp_raw)
        except (TypeError, ValueError):
            exp_ts = 0

        if exp_ts and exp_ts > int(time.time()):
            has_pass = True

    if has_pass:
        return

    # 3b) Per-template purchase check
    purchase_res = (
        sb
        .table("template_purchases")
        .select("expires_at")
        .eq("profile_id", user_id)
        .eq("template_id", template["id"])
        .single()
        .execute()
    )
    purchase = purchase_res.data

    if purchase:
        exp_raw = purchase.get("expires_at")
        try:
            exp_ts = int(exp_raw)
        except (TypeError, ValueError):
            exp_ts = 0

        # 0 or None → treat as "no expiry"
        if exp_ts == 0 or exp_ts > int(time.time()):
            return

    # If we got here, user has no valid access
    raise HTTPException(
        status_code=402,  # Payment Required → frontend can trigger Stripe purchase
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

        # expires is stored as unix timestamp (string or int)
        try:
            exp_ts = int(expires)
        except (TypeError, ValueError):
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
                try:
                    exp_ts = int(expires)
                except (TypeError, ValueError):
                    exp_ts = 0

                now = int(time.time())
                if exp_ts == 0 or exp_ts > now:
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
