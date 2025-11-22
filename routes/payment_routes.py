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
    StripeConfigResponse
)
from services.supabase_client import get_supabase
from services.auth import get_current_user

load_dotenv()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["Payments"])
supabase = get_supabase()

STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

logger.info("Payment routes initialized")


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
        
        # Block if user has active subscription
        if current_status == "active" and current_tier in ["starter", "pro"]:
            logger.warning(f"❌ User {user_id} already has active {current_tier} subscription")
            raise HTTPException(
                400, 
                f"You already have an active {current_tier} subscription. "
                "Please cancel your current subscription before switching plans."
            )
    
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
    
    Request body: {"quantity": 2}  (2 × 100 = 200 forms)
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
    
    # Handle checkout completion
    if event_type == "checkout.session.completed":
        logger.info("🎯 Processing checkout.session.completed")
        try:
            PaymentService.handle_checkout_completed(event_data)
            logger.info("✅ Checkout processed successfully")
        except Exception as e:
            logger.error(f"❌ Error processing checkout: {e}", exc_info=True)
            # Still return 200 to prevent Stripe retries
    
    else:
        logger.debug(f"Ignoring event type: {event_type}")
    
    return PlainTextResponse("ok", status_code=200)