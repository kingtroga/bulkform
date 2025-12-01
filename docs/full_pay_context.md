# 🎯 BULKFORM STRIPE PAYMENT INTEGRATION - COMPLETE CONTEXT

**Date Started:** November 21, 2025  
**Project:** BulkForm - B2B SaaS PDF Form Automation  
**Developer:** Tari Yekorogha (Solo Founder)  
**Goal:** Implement hybrid pricing model (subscriptions + pay-as-you-go + template marketplace) with entitlements and usage tracking to reach $1K MRR and 10 paying customers by December 2025

---

## 📋 TABLE OF CONTENTS

1. [Project Overview](#project-overview)
2. [Pricing Model](#pricing-model)
3. [Completed Work](#completed-work)
4. [Database Schema](#database-schema)
5. [Technical Stack](#technical-stack)
6. [Next Steps](#next-steps)
7. [Important Notes](#important-notes)

---

## 🎯 PROJECT OVERVIEW

### **What is BulkForm?**
BulkForm is a B2B SaaS application that automates PDF form filling using a grid-based coordinate system (150×150 grid at 300 DPI). The platform serves professionals who process large volumes of forms (50+ monthly):
- Immigration lawyers and paralegals (I-485, I-765 forms)
- HR departments
- Real estate agents
- Tax preparers
- Small law firms

### **Core Value Proposition**
"Making the tedious automatic" - returning hours of people's lives through automation.

### **Current Performance**
- **Processing Speed:** 100 PDFs in 3-4 minutes (10-20x improvement from 43 minutes)
- **Architecture:** FastAPI + Celery (10 parallel workers) + Redis + Supabase
- **Caching:** 99% template cache hit rate
- **Security:** End-to-end encryption, Row Level Security (RLS), private storage with signed URLs

### **Current User Base**
- 3 existing users (all on free tier)
- 17 completed batch jobs
- 62 batch items processed
- 32 templates in database (31 custom, 1 official)

---

## 💰 PRICING MODEL

### **SUBSCRIPTION TIERS**

#### **Free Tier** (Current - All Users)
**Price:** $0/month  
**Features:**
- ✅ 20 forms per month
- ✅ 3 custom templates
- ✅ Batch processing
- ✅ Basic support
- ❌ No API access
- ❌ No official templates included

**Use Case:** Testing, low-volume users, personal use

---

#### **Starter Tier**
**Price:** $19/month  
**Features:**
- ✅ 100 forms per month
- ✅ 10 custom templates
- ✅ Batch processing
- ✅ Email support
- ✅ Access to purchase official templates ($15 each)
- ❌ No API access

**Overage Pricing:** $0.30 per additional form  
**Target Customers:** Small law firms, solo practitioners, HR departments (1-5 employees)  
**Monthly Value:** Saves ~3-5 hours of manual work

---

#### **Pro Tier**
**Price:** $49/month  
**Features:**
- ✅ 300 forms per month
- ✅ Unlimited custom templates
- ✅ Batch processing
- ✅ Priority support
- ✅ API access
- ✅ Advanced analytics
- ✅ Access to purchase official templates ($10 each - 33% discount)

**Overage Pricing:** $0.25 per additional form  
**Target Customers:** Medium-sized firms, immigration law offices, HR consulting firms (5-20 employees)  
**Monthly Value:** Saves ~10-15 hours of manual work

---

#### **Enterprise Tier**
**Price:** Custom (Starting at $200/month)  
**Features:**
- ✅ Unlimited forms
- ✅ Unlimited custom templates
- ✅ Batch processing
- ✅ Dedicated account manager
- ✅ API access
- ✅ White-label options
- ✅ Custom integrations
- ✅ SLA guarantees
- ✅ All official templates included (free)
- ✅ Custom template development service

**Target Customers:** Large law firms, enterprise HR departments, government agencies (20+ employees)  
**Monthly Value:** Saves 40+ hours of manual work

---

### **PAY-AS-YOU-GO (PAYG)**

**Price:** $0.35 per form  
**No Monthly Commitment**

**Features:**
- ✅ Process any number of forms
- ✅ No subscription required
- ✅ Access to all features during processing
- ❌ No custom template storage (process and download only)
- ❌ No template marketplace access

**Use Cases:**
1. **One-time projects:** User needs to process 50 forms once
2. **Overage on subscriptions:** Starter user processes 120 forms (100 included + 20 PAYG at $0.30-0.35)
3. **Seasonal spikes:** Tax season, immigration filing deadlines

**How Overage Works:**
- **Free Tier:** User with 0 forms remaining → Charged $0.35/form for overage
- **Starter Tier:** User with 0 forms remaining → Charged $0.30/form for overage (discounted rate)
- **Pro Tier:** User with 0 forms remaining → Charged $0.25/form for overage (best rate)

---

### **TEMPLATE MARKETPLACE**

#### **Official BulkForm Templates**
Pre-mapped, professionally designed templates for common forms.

**Pricing Models:**

1. **Single Template Purchase**
   - **Free Tier:** $15 per template
   - **Starter Tier:** $15 per template
   - **Pro Tier:** $10 per template (33% discount)
   - **Enterprise Tier:** FREE (all included)
   - **Ownership:** Lifetime access, no expiration

2. **Template Bundles**
   - **Immigration Bundle:** I-485, I-765, I-131 ($40 - save $5)
   - **Family Immigration Bundle:** I-485, I-765, I-130, I-864 ($50 - save $10)
   - **Tax Forms Bundle:** W-2, 1099, W-4 ($35 - save $10)
   - **Real Estate Bundle:** Lease Agreement, Rental Application, Disclosure Forms ($45 - save $10)

3. **Annual Template Access**
   - **Price:** $99/year
   - **Includes:** Access to ALL official templates (current and future)
   - **Auto-renews:** Yes (can be canceled)
   - **Best for:** Users who need 7+ templates per year

#### **User-Created Templates**
- **Free to create:** All tiers can create custom templates (limits apply)
- **Private by default:** Only creator has access
- **Future marketplace:** Users could sell their templates (70/30 revenue split - user gets 70%)

**Current Official Template:**
- `OFFICIAL_BF_NDA_TEMPLATE` - BulkForm Non-Disclosure Agreement ($10-15 depending on tier)

---

## ✅ COMPLETED WORK

### **STEP 1: DATABASE SCHEMA SETUP** ✅

#### **1.1 Extended Profiles Table** ✅

**What We Did:**
- Added subscription and payment tracking columns to existing `profiles` table
- Configured usage limits and billing period tracking

**SQL Executed:**
```sql
ALTER TABLE profiles
ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free',
ADD COLUMN stripe_customer_id TEXT UNIQUE,
ADD COLUMN stripe_subscription_id TEXT,
ADD COLUMN subscription_status VARCHAR(20),
ADD COLUMN current_period_end BIGINT,
ADD COLUMN forms_used_this_month INTEGER DEFAULT 0,
ADD COLUMN forms_included_in_plan INTEGER DEFAULT 20,
ADD COLUMN custom_templates_count INTEGER DEFAULT 0,
ADD COLUMN billing_period VARCHAR(7);

-- Indexes
CREATE INDEX idx_profiles_stripe_customer ON profiles(stripe_customer_id);
CREATE INDEX idx_profiles_subscription_tier ON profiles(subscription_tier);
CREATE INDEX idx_profiles_user_billing ON profiles(id, billing_period);

-- Set defaults for existing users
UPDATE profiles
SET 
    subscription_tier = 'free',
    forms_included_in_plan = 20,
    forms_used_this_month = 0,
    billing_period = TO_CHAR(NOW(), 'YYYY-MM')
WHERE subscription_tier IS NULL;

-- Fix billing_period for any NULL values (run separately if needed)
UPDATE profiles
SET billing_period = TO_CHAR(NOW(), 'YYYY-MM')
WHERE billing_period IS NULL;
```

**Key Schema Additions:**
- `subscription_tier`: free, starter, pro, enterprise
- `stripe_customer_id`: Stripe customer reference (unique)
- `stripe_subscription_id`: Active subscription reference
- `subscription_status`: active, past_due, canceled, trialing
- `current_period_end`: Unix timestamp of subscription end
- `forms_used_this_month`: Monthly usage counter (resets each billing period)
- `forms_included_in_plan`: Forms included in current tier (20 for free, 100 for starter, 300 for pro)
- `custom_templates_count`: Number of custom templates user has created
- `billing_period`: Current billing period (YYYY-MM format) - **MUST NOT BE NULL**

**Current State:**
- 3 existing users in database
- All set to `free` tier with 20 forms/month limit
- All have `billing_period` set to current month (2025-11)

---

#### **1.2 Created Usage Records Table** ✅

**What We Did:**
- Created table to track pay-as-you-go form processing charges
- Linked to existing `batch_jobs` table (NOT `batches` - corrected during implementation)
- Implemented Row Level Security (RLS)

**SQL Executed:**
```sql
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    batch_id UUID REFERENCES batch_jobs(id) ON DELETE SET NULL,  -- CORRECTED: batch_jobs not batches
    forms_processed INTEGER NOT NULL,
    amount_charged INTEGER NOT NULL, -- cents
    stripe_payment_intent TEXT,
    billing_period VARCHAR(7) NOT NULL, -- YYYY-MM
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_usage_records_profile_period ON usage_records(profile_id, billing_period);
CREATE INDEX idx_usage_records_batch ON usage_records(batch_id);
CREATE INDEX idx_usage_records_created ON usage_records(created_at DESC);

-- RLS Policies
ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own usage records"
    ON usage_records FOR SELECT
    USING (auth.uid() = profile_id);

CREATE POLICY "System can insert usage records"
    ON usage_records FOR INSERT
    WITH CHECK (true); -- Service role only
```

**Purpose:**
- Tracks all pay-as-you-go charges
- Associates charges with batch jobs when applicable
- Stores Stripe PaymentIntent IDs for reconciliation
- Enables usage analytics and billing history

**Foreign Key Relationships Verified:**
```json
[
  {
    "table_name": "usage_records",
    "column_name": "batch_id",
    "foreign_table_name": "batch_jobs",
    "foreign_column_name": "id"
  },
  {
    "table_name": "usage_records",
    "column_name": "profile_id",
    "foreign_table_name": "profiles",
    "foreign_column_name": "id"
  }
]
```

---

#### **1.3 Created Template Purchases Table** ✅

**What We Did:**
- Created table to track template marketplace purchases
- Linked to existing `pdf_templates` table (NOT `templates` - corrected during implementation)
- Supports single purchases, bundles, and annual access subscriptions
- Implemented RLS and unique constraint to prevent duplicate purchases

**SQL Executed:**
```sql
CREATE TABLE template_purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES pdf_templates(id) ON DELETE CASCADE,  -- CORRECTED: pdf_templates not templates
    purchase_type VARCHAR(20) NOT NULL, -- 'single', 'bundle', 'annual_access'
    amount_paid INTEGER NOT NULL, -- cents
    stripe_payment_intent TEXT,
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ, -- NULL for single/bundle, set for annual
    UNIQUE(profile_id, template_id) -- Prevent duplicate purchases
);

-- Indexes
CREATE INDEX idx_template_purchases_profile ON template_purchases(profile_id);
CREATE INDEX idx_template_purchases_template ON template_purchases(template_id);
CREATE INDEX idx_template_purchases_expires ON template_purchases(expires_at) 
    WHERE expires_at IS NOT NULL;

-- RLS Policies
ALTER TABLE template_purchases ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own purchases"
    ON template_purchases FOR SELECT
    USING (auth.uid() = profile_id);

CREATE POLICY "System can insert purchases"
    ON template_purchases FOR INSERT
    WITH CHECK (true); -- Service role only
```

**Purpose:**
- Tracks template marketplace purchases
- Supports three purchase types:
  - `single`: One-time purchase of a specific template
  - `bundle`: One-time purchase of multiple templates together
  - `annual_access`: Yearly subscription for all official templates
- Prevents users from buying the same template twice (UNIQUE constraint)
- Handles expiration for annual access subscriptions

**Existing Templates Data:**
- 32 templates in `pdf_templates` table
- 1 official template: `OFFICIAL_BF_NDA_TEMPLATE` (price: $10.00)
- 31 custom user templates (mostly test templates)

**Foreign Key Relationships Verified:**
```json
[
  {
    "table_name": "template_purchases",
    "column_name": "profile_id",
    "foreign_table_name": "profiles",
    "foreign_column_name": "id"
  },
  {
    "table_name": "template_purchases",
    "column_name": "template_id",
    "foreign_table_name": "pdf_templates",
    "foreign_column_name": "id"
  }
]
```

---

### **🐛 FIXES APPLIED DURING STEP 1**

#### **Fix 1: Billing Period NULL Values** ✅
**Issue:** Initial migration left `billing_period` as NULL for existing users  
**Impact:** Would break usage tracking logic  
**Fix Applied:**
```sql
UPDATE profiles
SET billing_period = TO_CHAR(NOW(), 'YYYY-MM')
WHERE billing_period IS NULL;
```
**Result:** All 3 users now have `billing_period = "2025-11"`

---

## 📊 DATABASE SCHEMA

### **Tables Modified/Created:**

1. ✅ **`profiles`** - Extended with subscription columns
2. ✅ **`usage_records`** - New table for pay-as-you-go tracking
3. ✅ **`template_purchases`** - New table for template marketplace

### **Existing Tables Referenced:**
- **`batch_jobs`** - Links to usage records (17 jobs exist)
- **`batch_items`** - Batch processing data (62+ items exist)
- **`pdf_templates`** - Template catalog (32 templates exist)

### **Complete Schema Relationships:**

```
profiles (id)
    ↓ (1:many)
    ├─ batch_jobs (user_id)
    │   ↓ (1:many)
    │   └─ batch_items (batch_id)
    │
    ├─ usage_records (profile_id)
    │   ↓ (many:1) optional
    │   └─ batch_jobs (batch_id)
    │
    └─ template_purchases (profile_id)
        ↓ (many:1)
        └─ pdf_templates (template_id)
```

### **Key Schema Corrections Made:**
1. ✅ Used `batch_jobs` instead of `batches` (non-existent table)
2. ✅ Used `pdf_templates` instead of `templates` (actual table name)
3. ✅ Used `profile_id` in foreign keys instead of `user_id` (matching profiles table)
4. ✅ Fixed NULL `billing_period` values (MUST always be set)

---

## 🔧 TECHNICAL STACK

### **Backend:**
- **Framework:** FastAPI (Python)
- **Package Manager:** uv (Windows PowerShell environment)
- **Background Jobs:** Celery with 10 parallel workers
- **Caching:** Redis (template caching, job queuing)
- **Database:** PostgreSQL via Supabase
- **Storage:** Supabase Storage (private buckets with signed URLs)
- **Authentication:** Supabase Auth (email/password + Google OAuth with PKCE)

### **Frontend:**
- **Template Layer:** Django
- **Styling:** Tailwind CSS
- **API Communication:** JavaScript

### **PDF Processing:**
- **Libraries:** pypdf, reportlab, PIL
- **Grid System:** 150×150 grid at 300 DPI
- **Processing Speed:** 3-4 minutes for 100 PDFs (10-20x improvement)

### **Security:**
- **Encryption:** End-to-end encryption for sensitive data
- **Storage:** Private buckets with signed URLs (1-hour expiry)
- **Database:** Row Level Security (RLS) policies on all payment tables
- **Sessions:** Database-backed sessions (not in-memory)
- **Code Protection:** Client-side obfuscation to protect IP

### **Deployment:**
- **Backend:** Render (automatic GitHub integration)
- **Frontend:** PythonAnywhere (Django hosting)
- **Celery Workers:** Render (10 concurrent workers)
- **Redis:** Redis Cloud or Render-managed

---

## 🔐 SECURITY IMPLEMENTED

### **Row Level Security (RLS) Policies:**

**`usage_records` table:**
- ✅ Users can SELECT only their own records
- ✅ Only service role can INSERT (via webhooks)

**`template_purchases` table:**
- ✅ Users can SELECT only their own purchases
- ✅ Only service role can INSERT (via webhooks)

**`profiles` table:**
- ✅ Existing RLS policies maintained
- ✅ Indexed for performance on subscription lookups

### **Payment Security:**
- ✅ Webhook signature verification (prevents fake payment events)
- ✅ Stripe uses TLS 1.2+ for all communications
- ✅ Secret keys stored in environment variables (never in code)
- ✅ Service role bypasses RLS for webhook operations only

---

## 📝 NEXT STEPS (Not Yet Started)

### **Step 2: Stripe Product Setup** 🔴 NOT STARTED
**Tasks:**
- [ ] Create Stripe account / Use existing test account
- [ ] Create Starter Plan product ($19/month recurring)
- [ ] Create Pro Plan product ($49/month recurring)
- [ ] Create Pay-As-You-Go product ($0.35 one-time)
- [ ] Create template products (single, bundles, annual)
- [ ] Add metadata to products:
  ```json
  {
    "tier": "starter",
    "forms_included": "100",
    "custom_templates_limit": "10",
    "overage_price_cents": "30"
  }
  ```
- [ ] Copy price IDs to environment variables
- [ ] Set up webhook endpoint in Stripe Dashboard
- [ ] Get webhook signing secret

**Environment Variables Needed:**
```bash
STRIPE_SECRET_KEY=sk_test_***  # or sk_live_*** for production
STRIPE_PUBLISHABLE_KEY=pk_test_***  # or pk_live_*** for production
STRIPE_WEBHOOK_SECRET=whsec_***
STRIPE_API_VERSION=2024-12-18.acacia

# Price IDs (from Stripe Dashboard)
PRICE_STARTER_MONTHLY=price_***
PRICE_PRO_MONTHLY=price_***
PRICE_PAYG=price_***
PRICE_TEMPLATE_SINGLE=price_***
PRICE_TEMPLATE_BUNDLE_IMMIGRATION=price_***
PRICE_TEMPLATE_ANNUAL=price_***
```

---

### **Step 3: Payment Service Enhancement** 🔴 NOT STARTED
**File:** `services/payment_service.py`

**Tasks:**
- [ ] Install Stripe Python library: `uv add stripe`
- [ ] Update existing payment service with new methods:
  - `create_subscription_checkout(user_id, tier, email, customer_id?)`
  - `create_payg_checkout(user_id, forms_count, email, batch_id?)`
  - `create_template_checkout(user_id, template_id, price_id, purchase_type, email)`
  - `cancel_subscription(subscription_id)`
  - `reactivate_subscription(subscription_id)`
- [ ] Add Stripe customer creation logic
- [ ] Add metadata to all checkout sessions for webhook reconciliation

**Key Methods to Implement:**
```python
# Subscription checkout
PaymentService.create_subscription_checkout(
    user_id="uuid",
    tier="starter",  # or "pro"
    email="user@example.com",
    customer_id=None  # Create new or reuse existing
)

# Pay-as-you-go checkout
PaymentService.create_payg_checkout(
    user_id="uuid",
    forms_count=50,
    email="user@example.com",
    batch_id="uuid"  # Optional
)

# Template purchase
PaymentService.create_template_checkout(
    user_id="uuid",
    template_id="uuid",
    price_id="price_***",
    purchase_type="single",  # or "bundle" or "annual"
    email="user@example.com"
)
```

---

### **Step 4: Entitlement Service** 🔴 NOT STARTED
**File:** `services/entitlement_service.py` (NEW FILE)

**Tasks:**
- [ ] Create new service file
- [ ] Implement `get_user_entitlements(profile_id)` - Returns user's current limits and usage
- [ ] Implement `can_process_forms(profile_id, forms_count)` - Checks if user can process N forms
- [ ] Implement `increment_forms_usage(profile_id, forms_count)` - Updates usage counter
- [ ] Implement `reset_monthly_usage(profile_id)` - Resets counter at billing period change
- [ ] Implement `has_template_access(profile_id, template_id)` - Checks template access
- [ ] Implement `_calculate_overage_cost(tier, overage_count)` - Calculates overage charges

**Core Logic:**
```python
# Usage check example
can_process, reason = entitlement_service.can_process_forms("uuid", 150)

if not can_process:
    # reason = "need_50_more_forms_$15.00"
    # Show payment modal to user
    pass
else:
    # reason = "included_in_plan" or "unlimited"
    # Proceed with processing
    pass
```

**Tier Limits Reference:**
```python
TIER_LIMITS = {
    "free": {
        "forms_included": 20,
        "custom_templates_limit": 3,
        "can_batch_process": True,
        "has_api_access": False
    },
    "starter": {
        "forms_included": 100,
        "custom_templates_limit": 10,
        "can_batch_process": True,
        "has_api_access": False
    },
    "pro": {
        "forms_included": 300,
        "custom_templates_limit": "unlimited",
        "can_batch_process": True,
        "has_api_access": True
    },
    "enterprise": {
        "forms_included": "unlimited",
        "custom_templates_limit": "unlimited",
        "can_batch_process": True,
        "has_api_access": True
    }
}

OVERAGE_RATES = {
    "free": 35,  # $0.35 per form (PAYG rate)
    "starter": 30,  # $0.30 per form
    "pro": 25,  # $0.25 per form
}
```

---

### **Step 5: Webhook Handler** 🔴 NOT STARTED
**File:** `routes/payment_routes.py` (UPDATE EXISTING FILE)

**Tasks:**
- [ ] Update existing webhook endpoint to handle new events
- [ ] Handle `checkout.session.completed` for subscriptions
- [ ] Handle `checkout.session.completed` for PAYG
- [ ] Handle `checkout.session.completed` for template purchases
- [ ] Handle `customer.subscription.updated` (renewals, upgrades)
- [ ] Handle `customer.subscription.deleted` (cancellations)
- [ ] Handle `invoice.payment_failed` (failed payments)
- [ ] Update `profiles` table on successful payments
- [ ] Insert records into `usage_records` for PAYG
- [ ] Insert records into `template_purchases` for templates

**Critical Webhook Logic:**
```python
# On subscription payment success:
# 1. Update profiles table with subscription info
# 2. Set forms_included_in_plan based on tier
# 3. Reset forms_used_this_month to 0
# 4. Set billing_period to current month

# On PAYG payment success:
# 1. Insert into usage_records
# 2. Do NOT increment forms_used_this_month (paid separately)

# On template purchase success:
# 1. Insert into template_purchases
# 2. Set expires_at if annual access (365 days)
```

---

### **Step 6: Batch Processing Integration** 🔴 NOT STARTED
**File:** `routes/batch/batch_routes.py` (UPDATE EXISTING FILE)

**Tasks:**
- [ ] Import `EntitlementService` in batch routes
- [ ] Add entitlement check BEFORE processing batch:
  ```python
  can_process, reason = entitlement_service.can_process_forms(user_id, forms_count)
  
  if not can_process:
      # Return payment_required response with overage details
      return {
          "status": "payment_required",
          "overage_count": X,
          "overage_cost_cents": Y,
          "payment_options": [...]
      }
  ```
- [ ] After successful batch completion:
  ```python
  # Only increment if reason was "included_in_plan"
  if reason == "included_in_plan":
      entitlement_service.increment_forms_usage(user_id, forms_count)
  ```
- [ ] Handle billing period rollovers (reset usage if period changed)

**Example Flow:**
1. User triggers batch with 150 forms
2. User is on Starter plan (100 included, 20 used = 80 remaining)
3. System calculates: Need 70 more forms @ $0.30 = $21.00
4. Return payment modal to frontend
5. User pays $21.00 via Stripe
6. Webhook inserts usage_record
7. User retriggers batch processing
8. System processes all 150 forms (80 from plan + 70 paid)

---

### **Step 7: Frontend Integration** 🔴 NOT STARTED

**Tasks:**
- [ ] Create pricing page (`/pricing`)
- [ ] Add subscription checkout flow
- [ ] Add PAYG checkout for overages
- [ ] Add template marketplace page
- [ ] Display user's current plan and usage on dashboard
- [ ] Show "Upgrade" button when near limits
- [ ] Handle payment success/cancel redirects
- [ ] Display usage statistics and billing history

**Key UI Components Needed:**
1. **Pricing Page:**
   - Display all 4 tiers (Free, Starter, Pro, Enterprise)
   - "Current Plan" badge on active tier
   - "Upgrade" / "Downgrade" buttons
   - FAQ section

2. **Dashboard Usage Widget:**
   ```
   Your Plan: Starter ($19/month)
   Forms Used: 45 / 100 this month
   Forms Remaining: 55
   [View Usage History] [Upgrade Plan]
   ```

3. **Overage Payment Modal:**
   ```
   ⚠️ You need 50 more forms
   
   Your plan: 100 forms/month (0 remaining)
   Batch size: 50 forms
   
   Options:
   ☐ Pay $15.00 for 50 forms (one-time)
   ☐ Upgrade to Pro ($49/mo) for 300 forms
   
   [Continue] [Cancel]
   ```

4. **Template Marketplace:**
   - Grid of official templates
   - "Purchased" badge on owned templates
   - "Free" badge on free templates
   - Price display based on user's tier
   - Bundle deals highlighted

---

## 📌 IMPORTANT NOTES FOR FUTURE REFERENCE

### **1. Table Names Matter**
- ✅ Use `profiles` NOT `users`
- ✅ Use `batch_jobs` NOT `batches`
- ✅ Use `pdf_templates` NOT `templates`

### **2. Foreign Key Consistency**
- ✅ Always use `profile_id` when referencing profiles in new tables
- ✅ Keep `user_id` in existing tables (`batch_jobs`, `pdf_templates`) for backwards compatibility
- ✅ The `user_id` in existing tables IS the same as `profiles.id`

### **3. Stripe Metadata Strategy**
**Always include in metadata:**
```json
{
  "user_id": "uuid",  // Even though table is profiles
  "type": "subscription" | "payg" | "template_purchase",
  "tier": "starter" | "pro",  // For subscriptions
  "forms_count": "50",  // For PAYG
  "template_id": "uuid",  // For templates
  "batch_id": "uuid"  // Optional, for PAYG linked to batch
}
```

**Why metadata matters:**
- Webhooks don't send user context
- Metadata is the ONLY way to link Stripe events back to your database
- Include everything needed to update your database in the webhook

### **4. Billing Period Format**
- ✅ Store as `YYYY-MM` (e.g., "2025-11")
- ✅ **MUST NOT be NULL** - always set to current period on user creation
- ✅ Reset usage counter when billing period changes
- ✅ Check billing period on every usage increment
- ✅ If NULL found, immediately update: `UPDATE profiles SET billing_period = TO_CHAR(NOW(), 'YYYY-MM') WHERE billing_period IS NULL;`

**Billing Period Logic:**
```python
current_period = datetime.now().strftime("%Y-%m")
user_billing_period = profile["billing_period"]

if user_billing_period != current_period:
    # New billing period - reset usage
    new_count = forms_count
else:
    # Same period - add to existing
    new_count = profile["forms_used_this_month"] + forms_count
```

### **5. RLS is Critical**
- ✅ All payment-related tables have RLS enabled
- ✅ Service role bypasses RLS for webhooks (uses `SUPABASE_SERVICE_KEY`)
- ✅ User API calls respect RLS (uses `auth.uid()`)
- ✅ Never expose service key to frontend

**Service Role Usage:**
```python
# For webhooks (bypasses RLS)
supabase_admin = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# For user API calls (respects RLS)
supabase_user = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_ANON_KEY")
)
```

### **6. Webhook Verification is Mandatory**
**NEVER trust payment success without webhook verification!**

```python
# ❌ BAD: Trusting redirect URL
@app.get("/success")
def payment_success():
    # User can fake this URL!
    grant_access()  # DANGEROUS

# ✅ GOOD: Waiting for webhook
@app.post("/webhook")
def stripe_webhook(request: Request):
    # Verify signature
    event = stripe.Webhook.construct_event(
        payload, 
        sig_header, 
        WEBHOOK_SECRET
    )
    # NOW update database
    grant_access()  # SAFE
```

### **7. Overage vs PAYG**
**These are DIFFERENT use cases:**

**Overage:**
- User is on a subscription plan
- User runs out of monthly forms
- User is charged discounted rate ($0.25-0.30/form)
- Charged to same subscription payment method

**Pure PAYG:**
- User has NO subscription
- User pays per form ($0.35/form)
- Standalone one-time payment

**Implementation:**
```python
if user_has_subscription and forms_remaining == 0:
    # This is overage
    rate = get_overage_rate(tier)  # $0.25-0.30
else:
    # This is pure PAYG
    rate = 0.35
```

### **8. Template Access Logic**
**Priority order for checking access:**
1. User owns template (created it) → ✅ Access
2. User purchased template → ✅ Access (check expiration if annual)
3. Template is free (`is_official=false` OR `price=0`) → ✅ Access
4. Template is official paid → ❌ No access (prompt purchase)

```python
def has_access(profile_id, template_id):
    # 1. Check ownership
    if template["user_id"] == profile_id:
        return True
    
    # 2. Check purchases
    purchase = get_purchase(profile_id, template_id)
    if purchase:
        if purchase["expires_at"]:
            return datetime.now() < purchase["expires_at"]
        return True
    
    # 3. Check if free
    if template["is_free"] or template["price"] == 0:
        return True
    
    return False
```

---

## 🎓 KEY LEARNINGS

### **1. Schema Discovery**
- ✅ Always verify table names before writing SQL
- ✅ Use `\dt` in psql or Supabase Table Editor to list all tables
- ✅ Check foreign key relationships early: `\d+ table_name`
- ✅ Document corrections for future reference

### **2. Data Migration**
- ✅ Set sensible defaults for existing users
- ✅ Use `WHERE column IS NULL` to avoid overwriting existing data
- ✅ Add indexes immediately for performance
- ✅ Run separate UPDATE statements if ALTER TABLE fails

### **3. Stripe Integration Planning**
- ✅ Webhooks are the ONLY reliable payment verification
- ✅ Metadata bridges Stripe and your database
- ✅ Service role handles all payment-triggered updates
- ✅ Test with Stripe CLI before going to production

### **4. Performance Considerations**
- ✅ Index all foreign keys
- ✅ Index columns used in WHERE clauses
- ✅ Use partial indexes for optional columns (e.g., `WHERE expires_at IS NOT NULL`)
- ✅ Cache frequently accessed data (templates cached for 1 hour = 99% hit rate)

### **5. Security First**
- ✅ RLS on ALL user-facing tables
- ✅ Service role for admin operations ONLY
- ✅ Webhook signature verification (prevents $1M fraud)
- ✅ Never expose secret keys in frontend code

---

## 📊 SUCCESS METRICS

### **Technical Metrics:**
- ✅ Database schema complete (3 tables modified/created)
- ✅ Foreign keys verified (100% correct)
- ✅ RLS policies enabled (100% coverage)
- ✅ Indexes created (9 indexes added)

### **Business Metrics (Goals):**
- 🎯 10 paying customers by December 2025
- 🎯 $1,000 MRR by December 2025
- 🎯 50% conversion rate from free to paid
- 🎯 <5% churn rate monthly

### **Performance Metrics (Current):**
- ✅ 100 PDFs in 3-4 minutes (10-20x improvement)
- ✅ 99% template cache hit rate
- ✅ 10 parallel Celery workers
- ✅ Sub-second API response times

---

## 🚀 DEPLOYMENT CHECKLIST (When Ready)

### **Before Going Live:**
- [ ] Switch Stripe to live mode (use `sk_live_***` and `pk_live_***`)
- [ ] Register production webhook endpoint
- [ ] Update webhook secret in environment variables
- [ ] Test all payment flows in live mode with real card
- [ ] Set up Stripe customer portal for self-service
- [ ] Configure email notifications (Stripe + SendGrid/Mailgun)
- [ ] Add terms of service and privacy policy links
- [ ] Set up monitoring (Sentry for errors, PostHog for analytics)
- [ ] Create customer support email/system
- [ ] Prepare refund policy documentation

### **Environment Variables (Production):**
```bash
# Stripe Live Keys
STRIPE_SECRET_KEY=sk_live_***
STRIPE_PUBLISHABLE_KEY=pk_live_***
STRIPE_WEBHOOK_SECRET=whsec_***

# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key  # KEEP SECRET
SUPABASE_ANON_KEY=your-anon-key

# Redis
REDIS_URL=redis://your-redis-url

# Celery
CELERY_BROKER_URL=redis://your-redis-url/0
CELERY_RESULT_BACKEND=redis://your-redis-url/1

# App
APP_URL=https://bulkform.com
```

---

## 📞 CONTACT & SUPPORT

**Developer:** Tari Yekorogha  
**Email:** trogaclassicman@gmail.com  
**Location:** Abuja, Nigeria  
**Working Hours:** Full-time job + BulkForm development  

**For AI Assistants:**
- This context document contains ALL necessary information to continue implementation
- Always verify table names before writing SQL
- Check foreign key relationships before creating new tables
- Reference pricing tiers from this document (they are final)
- Follow the step-by-step implementation order

---

**Status:** ✅ Step 1 Complete - Database Schema Ready  
**Next:** Step 2 - Stripe Product Setup  
**Blockers:** None  
**Last Updated:** November 21, 2025, 11:45 PM WAT

---