import os
import logging
from typing import Dict, Any
from datetime import datetime, timezone

import stripe
from dotenv import load_dotenv

from services.supabase_client import get_supabase

load_dotenv()

logger = logging.getLogger(__name__)
supabase = get_supabase()

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe.api_version = "2024-12-18.acacia"

# Environment variables
APP_URL = "https://www.bulkform.app"
PRICE_STARTER_MONTHLY = os.getenv("PRICE_STARTER_MONTHLY")
PRICE_PRO_MONTHLY = os.getenv("PRICE_PRO_MONTHLY")
PRICE_PAYG = os.getenv("PRICE_PAYG")
PRICE_TEMPLATE_ANNUAL_PASS = os.getenv("PRICE_TEMPLATE_ANNUAL_PASS")
FORMS_PER_PAYG_UNIT = int(os.getenv("FORMS_PER_PAYG_UNIT", "100"))

logger.info(f"Payment Service initialized - APP_URL: {APP_URL}")


class PaymentService:
    
    # ========================================================================
    # CHECKOUT SESSION CREATORS
    # ========================================================================
    
    @staticmethod
    def create_subscription_checkout(user_id: str, plan_name: str) -> stripe.checkout.Session:
        """
        Create checkout for starter/pro subscription.
        """
        logger.info(f"📋 Creating {plan_name} subscription checkout for user {user_id}")
        
        if plan_name == "starter":
            price_id = PRICE_STARTER_MONTHLY
        elif plan_name == "pro":
            price_id = PRICE_PRO_MONTHLY
        else:
            raise ValueError(f"Unknown plan: {plan_name}")
        
        logger.info(f"Using price ID: {price_id}")
        
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "plan_name": plan_name,
                "type": "subscription",
            },
        )
        
        logger.info(f"✅ Checkout created: {session.id}")
        return session
    
    @staticmethod
    def create_payg_checkout(user_id: str, quantity: int) -> stripe.checkout.Session:
        """
        Create checkout for PAYG forms (one-time payment).

        `quantity` = number of forms the user is buying.
        """
        logger.info(f"📋 Creating PAYG checkout for user {user_id} - {quantity} forms")
        
        # quantity is already "forms", no extra multiplier
        forms_to_add = quantity
        logger.info(f"Will add {forms_to_add} forms to user account")

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": PRICE_PAYG, "quantity": quantity}],
            success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "forms_to_add": str(forms_to_add),
                "type": "payg",
            },
        )

        logger.info(f"✅ PAYG checkout created: {session.id}")
        return session

    
    @staticmethod
    def create_template_checkout(user_id: str, template_id: str, price_id: str) -> stripe.checkout.Session:
        """
        Create checkout for single template annual access.
        """
        logger.info(f"📋 Creating template checkout - user: {user_id}, template: {template_id}")
        logger.info(f"Using template price ID: {price_id}")
        
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_URL}/templates/{template_id}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/templates/{template_id}",
            metadata={
                "user_id": user_id,
                "template_id": template_id,
                "type": "template",
            },
        )
        
        logger.info(f"✅ Template checkout created: {session.id}")
        return session
    
    @staticmethod
    def create_library_pass_checkout(user_id: str) -> stripe.checkout.Session:
        """
        Create checkout for library pass (all templates).
        """
        logger.info(f"📋 Creating library pass checkout for user {user_id}")
        
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": PRICE_TEMPLATE_ANNUAL_PASS, "quantity": 1}],
            success_url=f"{APP_URL}/billing/library-pass/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "type": "library_pass",
            },
        )
        
        logger.info(f"✅ Library pass checkout created: {session.id}")
        return session
    
    # ========================================================================
    # WEBHOOK HANDLERS
    # ========================================================================
    
    @staticmethod
    def handle_checkout_completed(session: Dict[str, Any]) -> None:
        """
        Handle successful payment. Updates database based on metadata.type.
        """
        session_id = session.get("id")
        metadata = session.get("metadata", {}) or {}
        payment_type = metadata.get("type")
        user_id = metadata.get("user_id")
        
        logger.info(f"🎉 PAYMENT COMPLETED - Session: {session_id}")
        logger.info(f"Type: {payment_type}, User: {user_id}")
        logger.info(f"Metadata: {metadata}")
        
        if not user_id:
            logger.error("❌ No user_id in metadata!")
            return
        
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        amount_total = session.get("amount_total", 0)
        
        logger.info(
            f"Customer: {customer_id}, Subscription: {subscription_id}, "
            f"Amount: ${amount_total/100:.2f}"
        )
        
        if payment_type == "subscription":
            PaymentService._handle_subscription_payment(
                user_id, metadata.get("plan_name"), customer_id, subscription_id
            )
        
        elif payment_type == "payg":
            PaymentService._handle_payg_payment(
                user_id, int(metadata.get("forms_to_add", 0))
            )
        
        elif payment_type == "template":
            PaymentService._handle_template_payment(
                user_id, metadata.get("template_id"), customer_id, subscription_id, amount_total
            )
        
        elif payment_type == "library_pass":
            PaymentService._handle_library_pass_payment(
                user_id, customer_id, subscription_id
            )
        
        else:
            logger.warning(f"Unknown payment type: {payment_type}")
    
    @staticmethod
    def handle_subscription_renewal(invoice: Dict[str, Any]) -> None:
        """
        Handle automatic subscription renewals.
        
        This is triggered by invoice.payment_succeeded for recurring subscriptions.
        On renewal:
        1. REPLACE forms with subscription tier amount (not add)
        2. Reset forms_used_this_month to 0
        3. Update current_period_end
        """
        invoice_id = invoice.get("id")
        subscription_id = invoice.get("subscription")
        customer_id = invoice.get("customer")
        amount_paid = invoice.get("amount_paid", 0)
        
        logger.info(f"🔄 SUBSCRIPTION RENEWAL - Invoice: {invoice_id}")
        logger.info(f"Subscription: {subscription_id}, Customer: {customer_id}, Amount: ${amount_paid/100:.2f}")
        
        # Check if this is actually a renewal (not first payment)
        # First payments come through checkout.session.completed
        billing_reason = invoice.get("billing_reason")
        
        if billing_reason == "subscription_create":
            logger.info("⏭️ Skipping - this is initial subscription (handled by checkout.session.completed)")
            return
        
        if not subscription_id:
            logger.warning("⚠️ No subscription_id in invoice - skipping")
            return
        
        # Get subscription details from Stripe
        try:
            sub = stripe.Subscription.retrieve(subscription_id)
        except Exception as e:
            logger.error(f"❌ Failed to retrieve subscription {subscription_id}: {e}")
            return
        
        # Find user by stripe_customer_id
        profile_result = supabase.table("profiles").select(
            "id, subscription_tier, forms_included_in_plan, forms_used_this_month"
        ).eq("stripe_customer_id", customer_id).execute()
        
        if not profile_result.data or len(profile_result.data) == 0:
            logger.error(f"❌ No profile found for customer {customer_id}")
            return
        
        user_id = profile_result.data[0]["id"]
        current_tier = profile_result.data[0]["subscription_tier"]
        current_forms = profile_result.data[0]["forms_included_in_plan"]
        forms_used = profile_result.data[0]["forms_used_this_month"]
        
        logger.info(f"👤 User: {user_id}, Current tier: {current_tier}")
        logger.info(f"📊 Current forms: {current_forms}, Used this month: {forms_used}")
        
        # Get period end from subscription
        period_end_unix = sub.get("current_period_end")
        
        # Determine forms for this tier
        if current_tier == "starter":
            new_forms = 100
        elif current_tier == "pro":
            new_forms = 500
        else:
            logger.warning(f"⚠️ Unknown tier '{current_tier}' - defaulting to 100 forms")
            new_forms = 100
        
        # RENEWAL LOGIC: REPLACE forms (don't add)
        # This prevents accumulation and is standard SaaS behavior
        logger.info(f"🔄 Renewal: REPLACING {current_forms} forms with {new_forms} forms")
        logger.info(f"🔄 Resetting forms_used_this_month from {forms_used} to 0")
        
        # Update profile with renewal
        supabase.table("profiles").update({
            "subscription_status": sub.status,
            "current_period_end": period_end_unix,
            "forms_included_in_plan": new_forms,  # REPLACE, not add
            "forms_used_this_month": 0,  # Reset monthly counter
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ Subscription renewed: {current_tier} plan")
        logger.info(f"📊 New state - Forms: {new_forms}, Used: 0, Period end: {period_end_unix}")
        
        # Also handle template/library pass renewals
        PaymentService._handle_template_library_renewals(sub, user_id)
    
    @staticmethod
    def _handle_template_library_renewals(sub: stripe.Subscription, user_id: str) -> None:
        """
        Check if this subscription includes template purchases or library pass.
        Update expiry dates on renewal.
        """
        # Get subscription items to check what's being renewed
        items = sub.get("items", {}).get("data", [])
        
        for item in items:
            price_id = item.get("price", {}).get("id")
            
            # Check if this is the library pass price
            if price_id == PRICE_TEMPLATE_ANNUAL_PASS:
                logger.info(f"📚 Renewing library pass for user {user_id}")
                
                expires_at_iso = PaymentService._stripe_ts_to_iso(sub.get("current_period_end"))
                
                supabase.table("profiles").update({
                    "official_library_pass": True,
                    "official_library_pass_expires_at": expires_at_iso,
                }).eq("id", user_id).execute()
                
                logger.info(f"✅ Library pass renewed, expires: {expires_at_iso}")
            
            else:
                # Check if this price_id belongs to any template
                template_result = supabase.table("pdf_templates").select(
                    "id"
                ).eq("stripe_price_id", price_id).execute()
                
                if template_result.data and len(template_result.data) > 0:
                    template_id = template_result.data[0]["id"]
                    logger.info(f"📄 Renewing template {template_id} for user {user_id}")
                    
                    expires_at_iso = PaymentService._stripe_ts_to_iso(sub.get("current_period_end"))
                    
                    supabase.table("template_purchases").update({
                        "expires_at": expires_at_iso,
                    }).eq("profile_id", user_id).eq("template_id", template_id).execute()
                    
                    logger.info(f"✅ Template {template_id} renewed, expires: {expires_at_iso}")
    
    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================
    @staticmethod
    def _stripe_ts_to_iso(ts: int | None) -> str | None:
        """Convert Stripe unix timestamp → UTC ISO8601 string for timestamptz columns."""
        if not ts:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    
    @staticmethod
    def _handle_subscription_payment(user_id: str, plan_name: str, customer_id: str, subscription_id: str):
        """Update profile with subscription details"""
        logger.info(f"💳 Processing {plan_name} subscription for user {user_id}")
        
        sub = stripe.Subscription.retrieve(subscription_id)

        # current_period_end is bigint in DB, use Unix timestamp directly
        period_end_unix = sub.get("current_period_end")
        
        # Get current forms to ADD new subscription forms
        profile = supabase.table("profiles").select(
            "forms_included_in_plan, subscription_tier, current_period_end"
        ).eq("id", user_id).single().execute()
        
        current_forms = profile.data.get("forms_included_in_plan", 0) or 0
        old_tier = profile.data.get("subscription_tier")
        old_period_end = profile.data.get("current_period_end")
        
        # Determine form allowance for new subscription
        new_forms = 100 if plan_name == "starter" else 500
        
        # Logic: Only ADD forms if this is genuinely a NEW subscription or UPGRADE
        # Prevent resubscribe exploitation
        is_resubscribe = False
        
        if old_tier in ["starter", "pro"] and old_period_end:
            # Check if they're resubscribing within 30 days of cancellation
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).timestamp()
            time_since_expiry = current_time - old_period_end
            
            # If resubscribing within 30 days, this is exploitation prevention
            if time_since_expiry < (30 * 24 * 60 * 60):  # 30 days
                is_resubscribe = True
                logger.warning(
                    f"⚠️ User {user_id} resubscribing within 30 days. "
                    f"Old tier: {old_tier}, Time since expiry: {time_since_expiry/86400:.1f} days"
                )
        
        if is_resubscribe:
            # For resubscribes: REPLACE forms with new subscription amount
            # This prevents the cancel/resub exploit
            final_forms = new_forms
            logger.info(
                f"🔄 Resubscribe detected - REPLACING forms. "
                f"Old: {current_forms}, New: {final_forms}"
            )
        else:
            # For new subscriptions or upgrades: ADD forms
            final_forms = current_forms + new_forms
            logger.info(
                f"➕ New subscription - ADDING forms. "
                f"Current: {current_forms}, Adding: {new_forms}, Total: {final_forms}"
            )
        
        result = supabase.table("profiles").update({
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "subscription_status": sub.status,
            "subscription_tier": plan_name,
            "current_period_end": period_end_unix,
            "forms_included_in_plan": final_forms,
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ Subscription activated: {plan_name} plan, {final_forms} total forms")
        logger.debug(f"Database response: {result}")

    @staticmethod
    def _handle_payg_payment(user_id: str, forms_to_add: int):
        """Add forms to user's account"""
        logger.info(f"💰 Adding {forms_to_add} forms to user {user_id}")
        
        result = supabase.table("profiles").select("forms_included_in_plan").eq("id", user_id).single().execute()
        current_forms = result.data.get("forms_included_in_plan", 0)
        
        new_total = current_forms + forms_to_add
        logger.info(f"Current: {current_forms}, Adding: {forms_to_add}, New Total: {new_total}")
        
        supabase.table("profiles").update({
            "forms_included_in_plan": new_total
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ PAYG forms added: user now has {new_total} forms")
    
    @staticmethod
    def _handle_template_payment(user_id: str, template_id: str, customer_id: str, subscription_id: str, amount: int):
        """Record template purchase"""
        logger.info(f"📄 Recording template purchase - user: {user_id}, template: {template_id}")
        
        sub = stripe.Subscription.retrieve(subscription_id)

        # expires_at is timestamptz in template_purchases, use ISO string
        expires_at_iso = PaymentService._stripe_ts_to_iso(sub.get("current_period_end"))
        
        supabase.table("template_purchases").upsert(
            {
                "profile_id": user_id,
                "template_id": template_id,
                "purchase_type": "annual_access",
                "amount_paid": amount,
                # optional: if you want to store something from Stripe
                "stripe_payment_intent": sub.get("latest_invoice"),
                "expires_at": expires_at_iso,          # ✅ ISO string (timestamptz)
            },
            on_conflict="profile_id,template_id",
        ).execute()
        
        logger.info(f"✅ Template purchase recorded, expires: {expires_at_iso}")

    
    @staticmethod
    def _handle_library_pass_payment(user_id: str, customer_id: str, subscription_id: str):
        """Activate library pass"""
        logger.info(f"📚 Activating library pass for user {user_id}")
        
        sub = stripe.Subscription.retrieve(subscription_id)

        # official_library_pass_expires_at is timestamptz, use ISO string
        expires_at_iso = PaymentService._stripe_ts_to_iso(sub.get("current_period_end"))
        
        supabase.table("profiles").update({
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "subscription_status": sub.status,
            "official_library_pass": True,
            "official_library_pass_expires_at": expires_at_iso,   # ✅ ISO string (timestamptz)
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ Library pass activated, expires: {expires_at_iso}")

    
    @staticmethod
    def construct_webhook_event(payload: bytes, signature: str, secret: str):
        """Verify and construct Stripe webhook event"""
        return stripe.Webhook.construct_event(payload, signature, secret)