import os
import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from services.payment_service import PaymentService
from models.payment_models import (
    SubscriptionCheckoutRequest,
    PaygCheckoutRequest,
    TemplateCheckoutRequest,
    LibraryPassCheckoutRequest,
    CheckoutSessionResponse,
    StripeConfigResponse,
    TemplatePurchaseResponse
)
from services.supabase_client import get_supabase
from services.auth import get_current_user
from datetime import datetime, timezone

load_dotenv()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["Payments"])
supabase = get_supabase()

STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

logger.info("Payment routes initialized")


def _normalize_timestamp(value):
    """
    Accepts:
      - Unix timestamp (int/float)
      - ISO string (e.g. '2025-11-22T03:45:00+00:00')
    Returns: (iso_string_or_none, unix_timestamp_or_none)
    """
    if value is None:
        return None, None

    # Already a unix timestamp
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
        return dt.isoformat(), int(value)

    # Likely an ISO string from Supabase/PostgREST
    if isinstance(value, str):
        try:
            # Handle possible "Z" suffix
            cleaned = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt.astimezone(timezone.utc).isoformat(), int(dt.timestamp())
        except Exception as e:
            logger.warning(f"Unexpected timestamp format in DB: {value} ({e})")
            # Fall back to returning the raw string
            return value, None

    # Unknown type
    logger.warning(f"Unknown timestamp type: {type(value)} ({value})")
    return None, None


# ============================================================================
# SUBSCRIPTION MANAGEMENT
# ============================================================================

@router.post("/subscription/cancel")
async def cancel_subscription(
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel active subscription.
    
    🔒 Requires authentication
    
    Cancels the user's active subscription (starter/pro).
    Subscription remains active until the end of the current billing period.
    """
    user_id = current_user["id"]
    logger.info(f"🚫 Cancel subscription request - user: {user_id}")
    
    # Get user's profile to find subscription
    try:
        profile = supabase.table("profiles").select(
            "stripe_subscription_id, subscription_tier, subscription_status"
        ).eq("id", user_id).single().execute()
        
        if not profile.data:
            raise HTTPException(404, "Profile not found")
        
        subscription_id = profile.data.get("stripe_subscription_id")
        current_tier = profile.data.get("subscription_tier")
        current_status = profile.data.get("subscription_status")
        
        # Check if user has an active subscription
        if not subscription_id:
            logger.warning(f"User {user_id} has no subscription to cancel")
            raise HTTPException(400, "No active subscription found")
        
        if current_status != "active":
            logger.warning(f"User {user_id} subscription is not active (status: {current_status})")
            raise HTTPException(400, f"Subscription is not active (current status: {current_status})")
        
        logger.info(f"Canceling subscription: {subscription_id} (tier: {current_tier})")
        
        # Cancel subscription in Stripe
        import stripe
        canceled_sub = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )
        
        logger.info(f"✅ Subscription canceled in Stripe - will end at {canceled_sub.current_period_end}")
        
        # Update database
        supabase.table("profiles").update({
            "subscription_status": "canceled"  # Mark as canceled but still active until period ends
        }).eq("id", user_id).execute()
        
        from datetime import datetime, timezone
        period_end = datetime.fromtimestamp(canceled_sub.current_period_end, tz=timezone.utc)
        
        return {
            "message": "Subscription canceled successfully",
            "subscription_id": subscription_id,
            "tier": current_tier,
            "cancel_at_period_end": True,
            "access_until": period_end.isoformat(),
            "access_until_timestamp": canceled_sub.current_period_end
        }
        
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error canceling subscription: {e}")
        raise HTTPException(500, f"Failed to cancel subscription: {str(e)}")
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to cancel subscription: {str(e)}")


@router.get("/subscription/status")
async def get_subscription_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current subscription status.
    
    🔒 Requires authentication
    
    Returns detailed information about the user's subscription.
    """
    user_id = current_user["id"]
    logger.info(f"📊 Subscription status request - user: {user_id}")
    
    try:
        profile = supabase.table("profiles").select(
            "subscription_tier, subscription_status, stripe_subscription_id, "
            "current_period_end, forms_included_in_plan, forms_used_this_month, "
            "official_library_pass, official_library_pass_expires_at"
        ).eq("id", user_id).single().execute()
        
        if not profile.data:
            raise HTTPException(404, "Profile not found")
        
        data = profile.data

        # Safely coerce to ints (None → 0)
        included = data.get("forms_included_in_plan") or 0
        used = data.get("forms_used_this_month") or 0
        
        forms_remaining = max(0, included - used)
        
        response = {
            "subscription_tier": data.get("subscription_tier", "free"),
            "subscription_status": data.get("subscription_status"),
            "forms_included": included,
            "forms_used": used,
            "forms_remaining": forms_remaining,
            "official_library_pass": data.get("official_library_pass", False),
        }
        
        # Add period end (handles both unix and ISO string)
        current_period_raw = data.get("current_period_end")
        iso_val, ts_val = _normalize_timestamp(current_period_raw)
        if iso_val:
            response["current_period_end"] = iso_val
            if ts_val is not None:
                response["current_period_end_timestamp"] = ts_val
        
        # Add library pass expiry (handles both unix and ISO string)
        pass_raw = data.get("official_library_pass_expires_at")
        pass_iso, pass_ts = _normalize_timestamp(pass_raw)
        if pass_iso:
            response["library_pass_expires_at"] = pass_iso
            if pass_ts is not None:
                response["library_pass_expires_at_timestamp"] = pass_ts
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription status: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to get subscription status: {str(e)}")

@router.get("/template-purchases")
async def get_user_template_purchases(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all individual template purchases for the current user.
    
    🔒 Requires authentication
    
    Returns only active (non-expired) template purchases.
    """
    user_id = current_user["id"]
    logger.info(f"📋 Template purchases request - user: {user_id}")
    
    try:
        # Fetch template purchases with template details
        response = supabase.table("template_purchases")\
            .select("*, pdf_templates(name)")\
            .eq("profile_id", user_id)\
            .order("purchased_at", desc=True)\
            .execute()
        
        purchases = []
        now = datetime.now(timezone.utc)
        
        for purchase in response.data:
            # Check if purchase is still active
            expires_at = None
            is_active = True
            
            if purchase.get("expires_at"):
                # Use your existing _normalize_timestamp function
                iso_val, ts_val = _normalize_timestamp(purchase["expires_at"])
                if iso_val:
                    expires_at = datetime.fromisoformat(iso_val.replace("Z", "+00:00"))
                    is_active = expires_at > now
            
            # Only return active purchases
            if is_active:
                template_name = "Unknown Template"
                if purchase.get("pdf_templates"):
                    template_name = purchase["pdf_templates"].get("name", "Unknown Template")
                
                purchases.append({
                    "id": purchase["id"],
                    "template_id": purchase["template_id"],
                    "template_name": template_name,
                    "purchase_type": purchase["purchase_type"],
                    "amount_paid": purchase["amount_paid"],
                    "purchased_at": purchase["purchased_at"],
                    "expires_at": purchase.get("expires_at"),
                    "is_active": is_active
                })
        
        logger.info(f"✅ Found {len(purchases)} active template purchases for user {user_id}")
        return purchases
        
    except Exception as e:
        logger.error(f"Error fetching template purchases: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to fetch template purchases: {str(e)}")

# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@router.get("/config", response_model=StripeConfigResponse)
async def get_stripe_config():
    """Get Stripe publishable key for frontend"""
    if not STRIPE_PUBLISHABLE_KEY:
        raise HTTPException(500, "Stripe not configured")
    return StripeConfigResponse(publishable_key=STRIPE_PUBLISHABLE_KEY)


# ============================================================================
# CHECKOUT ENDPOINTS
# ============================================================================

@router.post("/subscription/checkout", response_model=CheckoutSessionResponse)
async def create_subscription_checkout(
    req: SubscriptionCheckoutRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create Stripe checkout for starter/pro subscription.
    
    Request body: {"plan_name": "starter"} or {"plan_name": "pro"}
    """
    user_id = current_user["id"]
    logger.info(f"🛒 Subscription checkout request - user: {user_id}, plan: {req.plan_name}")
    
    if req.plan_name not in ["starter", "pro"]:
        raise HTTPException(400, f"Invalid plan: {req.plan_name}. Use 'starter' or 'pro'.")
    
    # Check if user already has an active subscription
    profile = supabase.table("profiles").select(
        "subscription_tier, subscription_status, stripe_subscription_id"
    ).eq("id", user_id).single().execute()
    
    if profile.data:
        current_tier = profile.data.get("subscription_tier")
        current_status = profile.data.get("subscription_status")
        stripe_sub_id = profile.data.get("stripe_subscription_id")
        
        # Block ONLY if status is "active" (not "canceled")
        if current_status == "active" and current_tier in ["starter", "pro"]:
            logger.warning(f"❌ User {user_id} already has active {current_tier} subscription")
            raise HTTPException(
                400, 
                f"You already have an active {current_tier} subscription. "
                "Please cancel your current subscription before switching plans."
            )
        
        # If status is "canceled", cancel the old subscription in Stripe first
        if current_status == "canceled" and stripe_sub_id:
            logger.info(f"♻️ User has canceled subscription. Canceling immediately in Stripe before creating new one.")
            try:
                import stripe
                stripe.Subscription.delete(stripe_sub_id)
                logger.info(f"✅ Old subscription {stripe_sub_id} deleted")
            except Exception as e:
                logger.warning(f"Failed to delete old subscription: {e}")
    
    try:
        session = PaymentService.create_subscription_checkout(user_id, req.plan_name)
        return CheckoutSessionResponse(url=session.url, session_id=session.id)
    except Exception as e:
        logger.error(f"Failed to create subscription checkout: {e}", exc_info=True)
        raise HTTPException(400, str(e))

@router.post("/payg/checkout", response_model=CheckoutSessionResponse)
async def create_payg_checkout(
    req: PaygCheckoutRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create Stripe checkout for PAYG forms.

    Request body: {"quantity": 200}  (200 forms)
    """
    user_id = current_user["id"]
    logger.info(f"🛒 PAYG checkout request - user: {user_id}, quantity: {req.quantity}")
    
    if req.quantity < 1:
        raise HTTPException(400, "Quantity must be at least 1")
    
    try:
        session = PaymentService.create_payg_checkout(user_id, req.quantity)
        return CheckoutSessionResponse(url=session.url, session_id=session.id)
    except Exception as e:
        logger.error(f"Failed to create PAYG checkout: {e}", exc_info=True)
        raise HTTPException(400, str(e))


@router.post("/templates/{template_id}/checkout", response_model=CheckoutSessionResponse)
async def create_template_checkout(
    template_id: str,
    req: TemplateCheckoutRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create Stripe checkout for single template purchase.
    
    Path parameter: template_id (UUID of template)
    """
    user_id = current_user["id"]
    logger.info(f"🛒 Template checkout request - user: {user_id}, template: {template_id}")
    
    # Check if user already owns this template
    existing_purchase = supabase.table("template_purchases").select("id, expires_at").eq(
        "profile_id", user_id
    ).eq("template_id", template_id).execute()
    
    if existing_purchase.data:
        expires_at = existing_purchase.data[0].get("expires_at")
        logger.warning(f"❌ User {user_id} already owns template {template_id}")
        raise HTTPException(
            400,
            f"You already own this template. It will automatically renew when it expires."
        )
    
    # Fetch template to get price_id
    result = supabase.table("pdf_templates").select("stripe_price_id, is_free").eq("id", template_id).single().execute()
    
    if not result.data:
        raise HTTPException(404, "Template not found")
    
    if result.data.get("is_free"):
        raise HTTPException(400, "This template is free")
    
    price_id = result.data.get("stripe_price_id")
    if not price_id:
        raise HTTPException(400, "Template missing price configuration")
    
    try:
        session = PaymentService.create_template_checkout(user_id, template_id, price_id)
        return CheckoutSessionResponse(url=session.url, session_id=session.id)
    except Exception as e:
        logger.error(f"Failed to create template checkout: {e}", exc_info=True)
        raise HTTPException(400, str(e))


@router.post("/library-pass/checkout", response_model=CheckoutSessionResponse)
async def create_library_pass_checkout(
    req: LibraryPassCheckoutRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create Stripe checkout for library pass (all templates).
    """
    user_id = current_user["id"]
    logger.info(f"🛒 Library pass checkout request - user: {user_id}")
    
    # Check if user already has library pass
    profile = supabase.table("profiles").select(
        "official_library_pass, official_library_pass_expires_at"
    ).eq("id", user_id).single().execute()
    
    if profile.data and profile.data.get("official_library_pass"):
        expires_at = profile.data.get("official_library_pass_expires_at")
        logger.warning(f"❌ User {user_id} already has library pass (expires: {expires_at})")
        raise HTTPException(
            400,
            "You already have an active Library Pass. "
            "It will automatically renew when it expires."
        )
    
    try:
        session = PaymentService.create_library_pass_checkout(user_id)
        return CheckoutSessionResponse(url=session.url, session_id=session.id)
    except Exception as e:
        logger.error(f"Failed to create library pass checkout: {e}", exc_info=True)
        raise HTTPException(400, str(e))


# ============================================================================
# WEBHOOK
# ============================================================================

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint.
    
    This receives events from Stripe when payments succeed/fail.
    
    Handles:
    - checkout.session.completed: Initial purchases (subscriptions, PAYG, templates, library pass)
    - invoice.payment_succeeded: Subscription renewals (monthly/annual auto-billing)
    """
    logger.info("📨 Webhook received")
    
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured!")
        return PlainTextResponse("Webhook not configured", status_code=500)
    
    # Get payload and signature
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    
    # Verify and construct event
    try:
        event = PaymentService.construct_webhook_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        logger.error(f"❌ Invalid webhook signature: {e}")
        return PlainTextResponse("Invalid signature", status_code=400)
    
    event_type = event["type"]
    event_data = event["data"]["object"]
    
    logger.info(f"📬 Event type: {event_type}")
    
    # Handle checkout completion (initial purchases)
    if event_type == "checkout.session.completed":
        logger.info("🎯 Processing checkout.session.completed")
        try:
            PaymentService.handle_checkout_completed(event_data)
            logger.info("✅ Checkout processed successfully")
        except Exception as e:
            logger.error(f"❌ Error processing checkout: {e}", exc_info=True)
            # Still return 200 to prevent Stripe retries
    
    # Handle subscription renewals (auto-billing)
    elif event_type == "invoice.payment_succeeded":
        logger.info("🔄 Processing invoice.payment_succeeded (renewal)")
        try:
            PaymentService.handle_subscription_renewal(event_data)
            logger.info("✅ Renewal processed successfully")
        except Exception as e:
            logger.error(f"❌ Error processing renewal: {e}", exc_info=True)
            # Still return 200 to prevent Stripe retries
    
    else:
        logger.debug(f"Ignoring event type: {event_type}")
    
    return PlainTextResponse("ok", status_code=200)