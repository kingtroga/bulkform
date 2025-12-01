# Stripe Subscription Behavior - How It Works

## 🔄 Automatic Renewals Explained

### **YES - Stripe automatically charges users when it's time to renew**

When a user subscribes to a BulkForm plan (Starter $19/month or Pro $49/month), here's what happens:

---

## Initial Subscription

1. **User clicks "Subscribe to Starter"** → Creates Stripe Checkout Session
2. **User completes payment** → Stripe creates a Subscription object
3. **Webhook fires** (`checkout.session.completed`) → Your backend updates database:
   ```python
   - subscription_tier: "starter"
   - subscription_status: "active"
   - stripe_subscription_id: "sub_xxxxx"
   - stripe_customer_id: "cus_xxxxx"
   - current_period_end: "2025-12-23T00:00:00Z"  # 1 month from now
   - forms_included_in_plan: 100
   ```

---

## Automatic Renewal (What Stripe Does)

### **30 Days Later (when current_period_end is reached):**

1. **Stripe automatically attempts to charge the customer** using:
   - Their saved payment method (card on file)
   - The same price they originally paid ($19 or $49)

2. **If payment succeeds:**
   - Stripe fires webhook: `invoice.payment_succeeded`
   - Subscription remains `active`
   - `current_period_end` extends by 1 month
   - Customer is charged automatically
   - **User does NOT need to do anything**

3. **If payment fails:**
   - Stripe fires webhook: `invoice.payment_failed`
   - Stripe retries the payment (default: 3 attempts over 1 week)
   - Subscription status may become `past_due`
   - If all retries fail → subscription becomes `unpaid` or `canceled`

---

## What You Need to Handle

### **Webhook Events to Listen For:**

```python
# Current (already implemented)
'checkout.session.completed'  # Initial subscription creation

# Need to add (for proper renewal handling):
'invoice.payment_succeeded'   # Successful renewal - extend period
'invoice.payment_failed'      # Failed payment - notify user
'customer.subscription.updated'  # Plan changes
'customer.subscription.deleted'  # Subscription ended
```

---

## User Cancellation Behavior

### **When user clicks "Cancel Subscription":**

1. **Your backend calls Stripe:**
   ```python
   stripe.Subscription.modify(
       subscription_id,
       cancel_at_period_end=True  # Don't cancel immediately
   )
   ```

2. **What happens:**
   - Subscription remains `active` until `current_period_end`
   - User keeps access until end date
   - Stripe will NOT charge them next month
   - Status changes to `canceled` in your database
   - Badge shows "Canceled" with yellow color
   - UI shows: "Subscription ends on December 23, 2025"

3. **On the end date:**
   - Stripe fires webhook: `customer.subscription.deleted`
   - Subscription status becomes `canceled` or `inactive`
   - User loses access to paid features
   - Forms quota resets to free tier (0 forms)

---

## Current Implementation Status

### ✅ **What You Have:**
- Initial subscription creation
- Webhook handling for `checkout.session.completed`
- Cancel subscription endpoint
- Database schema for tracking subscriptions

### ⚠️ **What You're Missing:**
- Webhook handlers for renewal events
- Email notifications for payment failures
- Grace period handling for failed payments
- Automatic downgrade when subscription expires

---

## Recommended Improvements

### 1. **Add Renewal Webhook Handler**
```python
@router.post("/webhook")
async def stripe_webhook(request: Request):
    event_type = event["type"]
    
    # Existing
    if event_type == "checkout.session.completed":
        PaymentService.handle_checkout_completed(event_data)
    
    # NEW - Handle renewals
    elif event_type == "invoice.payment_succeeded":
        PaymentService.handle_successful_renewal(event_data)
    
    # NEW - Handle failed payments
    elif event_type == "invoice.payment_failed":
        PaymentService.handle_failed_payment(event_data)
    
    # NEW - Handle subscription end
    elif event_type == "customer.subscription.deleted":
        PaymentService.handle_subscription_ended(event_data)
```

### 2. **Handle Successful Renewal**
```python
@staticmethod
def handle_successful_renewal(invoice: Dict[str, Any]):
    """Update subscription period when renewal succeeds"""
    subscription_id = invoice.get("subscription")
    
    # Get latest subscription data
    sub = stripe.Subscription.retrieve(subscription_id)
    
    # Update database
    supabase.table("profiles").update({
        "subscription_status": "active",
        "current_period_end": _stripe_ts_to_iso(sub.current_period_end),
        "forms_used_this_month": 0  # Reset usage counter
    }).eq("stripe_subscription_id", subscription_id).execute()
```

### 3. **Handle Failed Payment**
```python
@staticmethod
def handle_failed_payment(invoice: Dict[str, Any]):
    """Notify user when payment fails"""
    customer_email = invoice.get("customer_email")
    
    # Send email notification (using your email service)
    send_email(
        to=customer_email,
        subject="Payment Failed - BulkForm Subscription",
        body="Your recent payment failed. Please update your payment method..."
    )
    
    # Update status
    supabase.table("profiles").update({
        "subscription_status": "past_due"
    }).eq("stripe_subscription_id", subscription_id).execute()
```

### 4. **Handle Subscription End**
```python
@staticmethod
def handle_subscription_ended(subscription: Dict[str, Any]):
    """Downgrade user when subscription expires"""
    subscription_id = subscription.get("id")
    
    # Downgrade to free tier
    supabase.table("profiles").update({
        "subscription_tier": "free",
        "subscription_status": "canceled",
        "forms_included_in_plan": 0,
        "forms_used_this_month": 0
    }).eq("stripe_subscription_id", subscription_id).execute()
```

---

## User Communication

### **What to tell users:**

✅ **Good messaging:**
- "Your subscription will automatically renew on [date]"
- "We'll charge your payment method on file"
- "Cancel anytime before [date] to avoid the next charge"
- "You'll keep access until [date] even after canceling"

❌ **Avoid saying:**
- "We might charge you" (sounds uncertain)
- "Your card will be charged" (too aggressive)
- "Renews forever" (sounds scary)

---

## Summary

**Q: Does Stripe automatically charge users?**
**A: YES** - That's the entire point of subscriptions. Once a user subscribes:
1. Stripe saves their payment method
2. Charges them automatically each billing cycle
3. Only stops if user cancels or payment fails repeatedly

**Q: Do users need to re-enter their card?**
**A: NO** - Stripe keeps the payment method on file and uses it for renewals

**Q: What if user wants to stop?**
**A: They click "Cancel Subscription"** - which sets `cancel_at_period_end=True`, meaning:
- No future charges
- Access until current period ends
- Then subscription deactivates

**Q: What about failed payments?**
**A: Stripe automatically retries** - You should handle webhooks to:
- Notify users of failures
- Give them time to update payment
- Eventually downgrade if payment never succeeds

---

## Your Updated Profile Page Behavior

### ✅ What happens now:

1. **User clicks "Cancel Subscription"**
2. **Custom modal appears:** "Are you sure? You'll keep access until [end date]"
3. **User confirms**
4. **Backend calls Stripe:** `cancel_at_period_end=True`
5. **Success modal shows:** "Canceled. Access until December 23, 2025. No further charges."
6. **Page reloads:**
   - Badge changes to "Canceled" (yellow)
   - Text shows: "Subscription ends on December 23, 2025"
   - "Cancel Subscription" button disappears (already canceled)
   - User can still use forms until end date

### ✅ What users see:
- Clear end date (not "renews")
- Confirmation they won't be charged again
- They keep access until paid period ends
- Professional, anxiety-free cancellation

Perfect! 🎯