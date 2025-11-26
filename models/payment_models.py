from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# ============================================================================
# Request Models
# ============================================================================

class SubscriptionCheckoutRequest(BaseModel):
    """Request to create a subscription checkout (starter/pro)"""
    plan_name: str  # "starter" or "pro"


class PaygCheckoutRequest(BaseModel):
    """Request to create a PAYG checkout (one-time payment for forms)"""
    quantity: int = 1  # Number of 100-form bundles


class TemplateCheckoutRequest(BaseModel):
    """Request to purchase a single template (annual subscription)"""
    # template_id comes from URL path parameter
    pass


class LibraryPassCheckoutRequest(BaseModel):
    """Request to purchase library pass (annual subscription to all templates)"""
    pass


# ============================================================================
# Response Models
# ============================================================================

class CheckoutSessionResponse(BaseModel):
    """Response with Stripe checkout URL"""
    url: str
    session_id: str


class StripeConfigResponse(BaseModel):
    """Response with Stripe publishable key"""
    publishable_key: str


class TemplatePurchaseResponse(BaseModel):
    id: str
    template_id: str
    template_name: str
    purchase_type: str
    amount_paid: int
    purchased_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool