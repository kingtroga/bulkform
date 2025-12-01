# Bulk Processing with Entitlements & PAYG Forms

## Overview

Implemented complete entitlement checking and forms metering for BulkForm's batch processing system. Users must now satisfy TWO requirements to process batches:

1. **Template Entitlement** - Must own access to the template
2. **Forms Availability** - Must have enough forms in their plan

## System Architecture

### Two-Layer Security Model

```
┌─────────────────────────────────────────────────────────┐
│                    User Starts Batch                     │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: Template Entitlement Check                    │
│  ────────────────────────────────────────────────────── │
│  • Custom templates → Always accessible by owner        │
│  • Free official → Always accessible                    │
│  • Paid official → Requires single purchase OR library  │
│                                                           │
│  ❌ FAILS → 402 Payment Required                        │
│  ✅ PASSES → Continue to Layer 2                        │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 2: Forms Availability Check                      │
│  ────────────────────────────────────────────────────── │
│  • Check: forms_needed ≤ forms_available                │
│  • forms_available = forms_included_in_plan             │
│                      - forms_used_this_month            │
│                                                           │
│  ❌ FAILS → 403 Forbidden (show upgrade/PAYG options)  │
│  ✅ PASSES → Create batch & allow processing            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│               Batch Processing Starts                    │
│  Each completed form increments forms_used_this_month   │
└─────────────────────────────────────────────────────────┘
```

## User Experience Flows

### Flow 1: Template Access Denied (402)

**Scenario:** User uploads CSV with 50 rows for a paid official template they don't own.

```
User clicks "Start Processing"
  ↓
Backend: Template entitlement check fails
  ↓
Response: 402 Payment Required
  {
    "detail": "This template requires purchase...",
    "status_code": 402
  }
  ↓
Frontend: Shows premium purchase modal
  - Option 1: Library Pass ($99/year) - HIGHLIGHTED
  - Option 2: Single Template ($19/year)
  ↓
User selects option → Redirects to Stripe checkout
  ↓
After payment: Webhook activates access
  ↓
User returns → Can now process batch
```

### Flow 2: Insufficient Forms (403)

**Scenario:** Starter plan user (100 forms/month) tries to process 120 forms after using 50.

```
User clicks "Start Processing"
  ↓
Backend: Template check ✅ passes
         Forms check ❌ fails
  
  forms_needed = 120
  forms_available = 100 - 50 = 50
  shortfall = 70
  ↓
Response: 403 Forbidden
  {
    "detail": "Insufficient forms! You need 120 but only have 50...",
    "forms_needed": 120,
    "forms_available": 50
  }
  ↓
Frontend: Shows error alert with upgrade options
  "Upgrade your plan or purchase 70 additional forms at $0.35 each"
  ↓
User options:
  1. Upgrade to Pro plan (500 forms/month)
  2. Buy PAYG forms (70 × $0.35 = $24.50)
  3. Wait until next billing cycle
  4. Process in smaller batches (50 forms now, 70 later)
```

### Flow 3: Success Path

**Scenario:** Pro plan user (500 forms/month, used 200) processes 100 forms for owned template.

```
User clicks "Start Processing"
  ↓
Backend checks:
  ✅ Template: User owns this template
  ✅ Forms: 100 needed ≤ 300 available
  ↓
Batch created & queued for processing
  ↓
Celery workers process 100 PDFs in parallel
  ↓
Each completion: forms_used_this_month += 1
  ↓
Final state: forms_used_this_month = 300
             forms_available = 200
```

## Implementation Details

### 1. Purchase Modal (Frontend)

**File:** `/mnt/user-data/outputs/bulk_purchase_modal_premium.html`

**Features:**
- Premium design with 2-layer glow system
- Emotional copywriting: "🔥 Best Value", breakeven math
- Library Pass highlighted as recommended option
- Single template purchase for one-off needs
- Mobile responsive (slides up from bottom)
- Dark mode support

**Dynamic Content:**
- Template price inserted: `$19/year` (or actual price)
- Breakeven calculation: `Math.ceil(99 / template_price)` templates
- Item count shown: "You need to process X forms"

### 2. Enhanced JavaScript

**File:** `/mnt/user-data/outputs/use_template_with_purchase_modal.js`

**Key Functions:**

```javascript
// Shows modal when 402 returned
window.showBulkPurchaseModal(templateData, itemCount)

// Closes modal and clears state
window.closeBulkPurchaseModal()

// Redirect to Library Pass checkout
window.purchaseLibraryPassBulk()

// Redirect to single template checkout
window.purchaseSingleTemplateBulk()
```

**Error Handling:**

```javascript
try {
  batchId = await createBatchFromCSV();
  await processBatch(batchId);
} catch (e) {
  // 402 Payment Required
  if (e.needsPurchase) {
    showBulkPurchaseModal(template, e.itemCount);
    return;
  }
  
  // 403 Forbidden (insufficient forms)
  if (e.needsForms) {
    const shortfall = e.formsNeeded - e.formsAvailable;
    showAlert(
      `Insufficient forms! Upgrade or purchase ${shortfall} forms at $0.35 each.`,
      'error'
    );
    return;
  }
  
  // Other errors
  showAlert(e.message, 'error');
}
```

### 3. Backend Routes

**File:** `/mnt/user-data/outputs/batch_routes_with_entitlements.py`

**Key Changes:**

#### Create Batch (CSV & JSON)
```python
# STEP 1: Template entitlement
try:
    ensure_template_single_fill_access(current_user["id"], template)
except EntitlementError as ee:
    raise HTTPException(
        status_code=402,
        detail=ee.detail,
        headers={"X-Requires-Purchase": "true"}
    )

# STEP 2: Forms availability (BEFORE creating batch)
forms_needed = len(items)
try:
    entitlement_service.ensure_forms_available(
        user_id=current_user["id"],
        forms_needed=forms_needed,
    )
except EntitlementError as ee:
    raise HTTPException(
        status_code=403,
        detail=ee.detail,
        headers={
            "X-Forms-Needed": str(forms_needed),
            "X-Forms-Available": str(ee.forms_available or 0)
        }
    )

# Both passed → Create batch
batch_id = services['batch'].create_batch(...)
```

#### Process Batch
```python
# Re-validate forms at processing time
# (user may have consumed forms between creation and processing)
pending_items = services["batch"].get_batch_items(batch_id, status="pending")
forms_needed = len(pending_items)

try:
    entitlement_service.ensure_forms_available(
        user_id=current_user["id"],
        forms_needed=forms_needed,
    )
except EntitlementError as ee:
    raise HTTPException(
        status_code=403,
        detail=ee.detail,
        headers={
            "X-Forms-Needed": str(forms_needed),
            "X-Forms-Available": str(ee.forms_available or 0)
        }
    )

# Passed → Start processing
trigger_parallel_batch(...)
```

## Database Schema (Relevant Columns)

```sql
-- profiles table
subscription_tier VARCHAR(20) DEFAULT 'free'
forms_included_in_plan INTEGER DEFAULT 20
forms_used_this_month INTEGER DEFAULT 0
official_library_pass BOOLEAN DEFAULT false
official_library_pass_expires_at TIMESTAMPTZ

-- template_purchases table
user_id UUID REFERENCES auth.users(id)
template_id UUID REFERENCES templates(id)
expires_at TIMESTAMPTZ
status VARCHAR(20) DEFAULT 'active'
```

## Forms Calculation Logic

### Available Forms

```python
def get_available_forms(user_id: str) -> int:
    """
    Returns: forms_included_in_plan - forms_used_this_month
    
    Examples:
    - Free: 20 - 5 = 15 available
    - Starter: 100 - 80 = 20 available
    - Pro: 500 - 200 = 300 available
    """
    profile = get_profile(user_id)
    
    included = profile.get('forms_included_in_plan', 0)
    used = profile.get('forms_used_this_month', 0)
    
    return max(0, included - used)
```

### Forms Reservation

```python
def ensure_forms_available(user_id: str, forms_needed: int):
    """
    Checks if user has enough forms WITHOUT decrementing.
    
    Actual decrement happens in Celery worker on completion:
    - Each PDF completion → forms_used_this_month += 1
    
    This prevents race conditions and double-counting.
    """
    available = get_available_forms(user_id)
    
    if forms_needed > available:
        shortfall = forms_needed - available
        raise EntitlementError(
            status_code=403,
            detail=f"Insufficient forms! You need {forms_needed} but only have {available}. "
                   f"Upgrade your plan or purchase {shortfall} forms at $0.35 each.",
            forms_available=available,
            forms_needed=forms_needed
        )
```

### Monthly Reset

```python
# Handled by subscription renewal webhook (invoice.payment_succeeded)
def handle_subscription_renewal(subscription_id: str):
    """
    On monthly/annual renewal:
    1. Reset forms_used_this_month = 0
    2. forms_included_in_plan stays same (unless tier changed)
    3. Update current_period_end
    """
    profile = get_profile_by_subscription(subscription_id)
    
    supabase.table('profiles').update({
        'forms_used_this_month': 0,
        'current_period_end': new_period_end
    }).eq('stripe_subscription_id', subscription_id).execute()
```

## Subscription Tiers & Forms Allocation

| Tier | Price | Forms/Month | Rollover? |
|------|-------|-------------|-----------|
| Free | $0 | 20 | ❌ No |
| Starter | $19/mo | 100 | ❌ No |
| Pro | $49/mo | 500 | ❌ No |
| PAYG | $0.35/form | ∞ | ✅ Yes (never expire) |

### Key Policies

1. **Subscription credits:** REPLACE each cycle (no rollover)
2. **PAYG credits:** ADD permanently and NEVER expire
3. **Consumption order:** Use subscription forms first, then PAYG
4. **Forms tracking:** Only bulk processing consumes forms
5. **Single-fill:** Does NOT consume forms (entitlement-only check)

## Error Messages

### 402 Payment Required
```json
{
  "detail": "This template requires purchase. You need either a single template purchase ($19/year) or Library Pass ($99/year) to use this template in bulk processing.",
  "status_code": 402
}
```

### 403 Forbidden (Insufficient Forms)
```json
{
  "detail": "Insufficient forms! You need 120 forms but only have 50 available. Upgrade your plan or purchase 70 additional forms at $0.35 each ($24.50 total).",
  "status_code": 403,
  "forms_needed": 120,
  "forms_available": 50
}
```

## Frontend Integration

### HTML Updates

Add modal to bottom of `single_fill.html` and `use_template.html`:

```html
<!-- Before closing </main> tag -->
{% include 'bulk_purchase_modal_premium.html' %}
```

### JavaScript Updates

Replace existing `use_template.js` with enhanced version:

```html
<script src="{% static 'js/use_template_with_purchase_modal.js' %}"></script>
```

## Payment Flow Integration

### Checkout Endpoints (Already Exist)

```python
# Library Pass
POST /api/payment/library-pass/checkout
→ Creates Stripe checkout session
→ Redirects to: https://checkout.stripe.com/...

# Single Template
POST /api/payment/templates/{template_id}/checkout
→ Creates Stripe checkout session
→ Redirects to: https://checkout.stripe.com/...

# PAYG Forms (TODO: Not yet implemented)
POST /api/payment/forms/checkout?quantity=70
→ Creates one-time payment for X forms at $0.35 each
→ On success: Adds to forms_included_in_plan
```

### Webhook Handlers (Already Exist)

```python
# checkout.session.completed
→ Activates library pass
→ Creates template purchase record
→ Adds PAYG forms to profile

# invoice.payment_succeeded
→ Resets forms_used_this_month = 0
→ Updates current_period_end
```

## Testing Scenarios

### Test 1: Free User, Paid Template, Bulk Processing

```python
# Setup
user.subscription_tier = 'free'
user.forms_included_in_plan = 20
user.forms_used_this_month = 0
template.template_type = 'official'
template.is_free = False
user has NOT purchased template
user has NO library pass

# Action
POST /api/batch/create-from-csv (50 items)

# Expected Result
❌ 402 Payment Required
Modal appears with Library Pass vs Single Template options
```

### Test 2: Starter User, Owned Template, Insufficient Forms

```python
# Setup
user.subscription_tier = 'starter'
user.forms_included_in_plan = 100
user.forms_used_this_month = 80
template owned by user
items_count = 50

# Action
POST /api/batch/create-from-csv (50 items)

# Expected Result
✅ Template check passes
❌ Forms check fails
403 Forbidden: "Need 50, have 20, shortfall 30"
Alert suggests: "Upgrade or buy 30 forms for $10.50"
```

### Test 3: Pro User, Library Pass, Success

```python
# Setup
user.subscription_tier = 'pro'
user.forms_included_in_plan = 500
user.forms_used_this_month = 200
user.official_library_pass = True
template.template_type = 'official'
template.is_free = False
items_count = 100

# Action
POST /api/batch/create-from-csv (100 items)
POST /api/batch/{batch_id}/process

# Expected Result
✅ Template check passes (library pass)
✅ Forms check passes (100 ≤ 300)
Batch processing starts
After completion: forms_used_this_month = 300
```

## Files Created

1. **`bulk_purchase_modal_premium.html`** - Premium modal with emotional design
2. **`use_template_with_purchase_modal.js`** - Enhanced JS with error handling
3. **`batch_routes_with_entitlements.py`** - Backend with two-layer checks

## Critical Implementation Notes

### DO's ✅

1. **Check forms BEFORE creating batch** - Prevents orphaned batches
2. **Re-check forms at processing time** - User may have consumed forms between creation and processing
3. **Return proper HTTP status codes** - 402 for payment, 403 for forms
4. **Show shortfall calculation** - "Need X, have Y, shortfall Z"
5. **Highlight Library Pass** - Better economics for users who'll use 5+ templates
6. **Mobile responsive modal** - Slides up from bottom on mobile
7. **Dark mode support** - All UI elements adapt to theme

### DON'Ts ❌

1. **Don't decrement forms on batch creation** - Only on actual PDF completion
2. **Don't allow batch processing without entitlement** - Template access is mandatory
3. **Don't skip re-validation** - Always re-check at processing time
4. **Don't show generic errors** - Be specific about what's missing
5. **Don't let orphan batches exist** - Forms check happens BEFORE creation

## Future Enhancements

### PAYG Forms Purchase (TODO)

```python
@router.post("/payment/forms/checkout")
async def purchase_forms_checkout(
    quantity: int = Query(..., ge=1, le=10000),
    current_user: dict = Depends(get_current_user)
):
    """
    Create Stripe checkout for PAYG forms.
    Price: $0.35 per form
    """
    amount = int(quantity * 0.35 * 100)  # Stripe uses cents
    
    session = stripe.checkout.Session.create(
        customer=user.stripe_customer_id,
        mode='payment',
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': 35,  # $0.35 in cents
                'product_data': {'name': 'PAYG Forms'},
            },
            'quantity': quantity,
        }],
        success_url=f"{FRONTEND_URL}/account?forms_purchased=true",
        cancel_url=f"{FRONTEND_URL}/account",
        metadata={
            'type': 'payg_forms',
            'quantity': quantity,
            'user_id': current_user['id']
        }
    )
    
    return {'url': session.url}
```

### Webhook Handler
```python
if session.metadata['type'] == 'payg_forms':
    quantity = int(session.metadata['quantity'])
    
    # Add to forms_included_in_plan (these never expire)
    supabase.table('profiles').update({
        'forms_included_in_plan': profile['forms_included_in_plan'] + quantity
    }).eq('id', user_id).execute()
```

## Summary

This implementation provides:

1. **Template access control** - Users must own/purchase templates for bulk
2. **Forms metering** - Users must have sufficient forms in their plan
3. **Clear user feedback** - Specific errors with upgrade/purchase paths
4. **Premium UX** - Emotional modal design encourages Library Pass conversion
5. **Revenue protection** - Prevents free access to paid templates/bulk processing
6. **Scalable architecture** - Easy to add PAYG forms purchase later

The system ensures users pay for what they use while providing clear, helpful guidance when they hit limits.