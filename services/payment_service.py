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
APP_URL = os.getenv("APP_URL", "http://localhost:5173")
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
        
        Flow:
        1. User clicks "Subscribe to Pro"
        2. This creates a Stripe checkout session
        3. User pays
        4. Stripe webhook fires with user_id in metadata
        5. We update the database
        """
        logger.info(f"📋 Creating {plan_name} subscription checkout for user {user_id}")
        
        # Get the right price ID
        if plan_name == "starter":
            price_id = PRICE_STARTER_MONTHLY
        elif plan_name == "pro":
            price_id = PRICE_PRO_MONTHLY
        else:
            raise ValueError(f"Unknown plan: {plan_name}")
        
        logger.info(f"Using price ID: {price_id}")
        
        # Create Stripe session
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "plan_name": plan_name,
                "type": "subscription"
            }
        )
        
        logger.info(f"✅ Checkout created: {session.id}")
        return session
    
    @staticmethod
    def create_payg_checkout(user_id: str, quantity: int) -> stripe.checkout.Session:
        """
        Create checkout for PAYG forms (one-time payment).
        
        Flow:
        1. User clicks "Buy 100 forms"
        2. This creates a Stripe checkout session
        3. User pays
        4. Stripe webhook fires with user_id and form count in metadata
        5. We add forms to their account
        """
        logger.info(f"📋 Creating PAYG checkout for user {user_id} - {quantity} units")
        
        forms_to_add = quantity * FORMS_PER_PAYG_UNIT
        logger.info(f"Will add {forms_to_add} forms ({quantity} × {FORMS_PER_PAYG_UNIT})")
        
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": PRICE_PAYG, "quantity": quantity}],
            success_url=f"{APP_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "forms_to_add": str(forms_to_add),
                "type": "payg"
            }
        )
        
        logger.info(f"✅ PAYG checkout created: {session.id}")
        return session
    
    @staticmethod
    def create_template_checkout(user_id: str, template_id: str, price_id: str) -> stripe.checkout.Session:
        """
        Create checkout for single template annual access.
        
        Flow:
        1. User clicks "Buy Template" (e.g., I-485)
        2. This creates a Stripe checkout session
        3. User pays
        4. Stripe webhook fires with user_id and template_id
        5. We record purchase in template_purchases table
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
                "type": "template"
            }
        )
        
        logger.info(f"✅ Template checkout created: {session.id}")
        return session
    
    @staticmethod
    def create_library_pass_checkout(user_id: str) -> stripe.checkout.Session:
        """
        Create checkout for library pass (all templates).
        
        Flow:
        1. User clicks "Buy All Templates Pass"
        2. This creates a Stripe checkout session
        3. User pays
        4. Stripe webhook fires with user_id
        5. We set official_library_pass = true in their profile
        """
        logger.info(f"📋 Creating library pass checkout for user {user_id}")
        
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": PRICE_TEMPLATE_ANNUAL_PASS, "quantity": 1}],
            success_url=f"{APP_URL}/billing/library-pass/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/billing/cancel",
            metadata={
                "user_id": user_id,
                "type": "library_pass"
            }
        )
        
        logger.info(f"✅ Library pass checkout created: {session.id}")
        return session
    
    # ========================================================================
    # WEBHOOK HANDLERS
    # ========================================================================
    
    @staticmethod
    def handle_checkout_completed(session: Dict[str, Any]) -> None:
        """
        Handle successful payment.
        This is THE critical function that updates your database.
        """
        session_id = session.get("id")
        metadata = session.get("metadata", {})
        payment_type = metadata.get("type")
        user_id = metadata.get("user_id")
        
        logger.info(f"🎉 PAYMENT COMPLETED - Session: {session_id}")
        logger.info(f"Type: {payment_type}, User: {user_id}")
        logger.info(f"Metadata: {metadata}")
        
        if not user_id:
            logger.error("❌ No user_id in metadata!")
            return
        
        # Get Stripe data
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        amount_total = session.get("amount_total", 0)
        
        logger.info(f"Customer: {customer_id}, Subscription: {subscription_id}, Amount: ${amount_total/100:.2f}")
        
        # Handle based on type
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
    
    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================
    
    @staticmethod
    def _handle_subscription_payment(user_id: str, plan_name: str, customer_id: str, subscription_id: str):
        """Update profile with subscription details"""
        logger.info(f"💳 Processing {plan_name} subscription for user {user_id}")
        
        # Get subscription details from Stripe
        sub = stripe.Subscription.retrieve(subscription_id)
        
        # Determine form allowance
        forms = 100 if plan_name == "starter" else 500
        
        # Update database
        result = supabase.table("profiles").update({
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "subscription_status": sub.status,
            "subscription_tier": plan_name,
            "current_period_end": sub.current_period_end,  # Send as Unix timestamp
            "forms_included_in_plan": forms
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ Subscription activated: {plan_name} plan, {forms} forms/month")
        logger.debug(f"Database response: {result}")
    
    @staticmethod
    def _handle_payg_payment(user_id: str, forms_to_add: int):
        """Add forms to user's account"""
        logger.info(f"💰 Adding {forms_to_add} forms to user {user_id}")
        
        # Get current form count
        result = supabase.table("profiles").select("forms_included_in_plan").eq("id", user_id).single().execute()
        current_forms = result.data.get("forms_included_in_plan", 0)
        
        new_total = current_forms + forms_to_add
        logger.info(f"Current: {current_forms}, Adding: {forms_to_add}, New Total: {new_total}")
        
        # Update database
        supabase.table("profiles").update({
            "forms_included_in_plan": new_total
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ PAYG forms added: user now has {new_total} forms")
    
    @staticmethod
    def _handle_template_payment(user_id: str, template_id: str, customer_id: str, subscription_id: str, amount: int):
        """Record template purchase"""
        logger.info(f"📄 Recording template purchase - user: {user_id}, template: {template_id}")
        
        # Get subscription details
        sub = stripe.Subscription.retrieve(subscription_id)
        
        # Record in template_purchases table
        supabase.table("template_purchases").upsert({
            "profile_id": user_id,
            "template_id": template_id,
            "purchase_type": "annual_access",
            "amount_paid": amount,
            "expires_at": sub.current_period_end  # Send as Unix timestamp
        }, on_conflict="profile_id,template_id").execute()
        
        logger.info(f"✅ Template purchase recorded, expires: {sub.current_period_end}")
    
    @staticmethod
    def _handle_library_pass_payment(user_id: str, customer_id: str, subscription_id: str):
        """Activate library pass"""
        logger.info(f"📚 Activating library pass for user {user_id}")
        
        # Get subscription details
        sub = stripe.Subscription.retrieve(subscription_id)
        
        # Update profile
        supabase.table("profiles").update({
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription_id,
            "subscription_status": sub.status,
            "official_library_pass": True,
            "official_library_pass_expires_at": sub.current_period_end  # Send as Unix timestamp
        }).eq("id", user_id).execute()
        
        logger.info(f"✅ Library pass activated, expires: {sub.current_period_end}")
    
    @staticmethod
    def construct_webhook_event(payload: bytes, signature: str, secret: str):
        """Verify and construct Stripe webhook event"""
        return stripe.Webhook.construct_event(payload, signature, secret)