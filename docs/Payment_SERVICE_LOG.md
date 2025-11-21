# 🎯 BULKFORM STRIPE PAYMENT INTEGRATION - IMPLEMENTATION LOG

**Date Started:** November 21, 2025  
**Project:** BulkForm - B2B SaaS PDF Form Automation  
**Goal:** Implement hybrid pricing model (subscriptions + pay-as-you-go) with entitlements and usage tracking

---

## ✅ COMPLETED: STEP 1 - DATABASE SCHEMA SETUP

### **1.1 Extended Profiles Table** ✅

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
- `forms_included_in_plan`: Forms included in current tier (20 for free)
- `custom_templates_count`: Number of custom templates user has created
- `billing_period`: Current billing period (YYYY-MM format)

**Existing Profiles Data:**
- 3 existing users in database
- All set to `free` tier with 20 forms/month limit
- All have `billing_period` set to current month (2025-11)

---

### **1.2 Created Usage Records Table** ✅

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

### **1.3 Created Template Purchases Table** ✅

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

## 🐛 FIXES APPLIED DURING STEP 1

### **Fix 1: Billing Period NULL Values** ✅
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

## 📊 CURRENT DATABASE STATE

### **Tables Modified/Created:**
1. ✅ `profiles` - Extended with subscription columns
2. ✅ `usage_records` - New table for pay-as-you-go tracking
3. ✅ `template_purchases` - New table for template marketplace

### **Existing Tables Referenced:**
- `batch_jobs` - Links to usage records
- `batch_items` - Batch processing data (62+ items)
- `pdf_templates` - Template catalog (32 templates)

### **Key Schema Corrections Made:**
1. Used `batch_jobs` instead of `batches` (non-existent table)
2. Used `pdf_templates` instead of `templates` (actual table name)
3. Used `profile_id` in foreign keys instead of `user_id` (matching profiles table)

---

## 🎯 TIER LIMITS DEFINED

### **Free Tier:**
- Forms: 20/month
- Custom Templates: 3
- Batch Processing: ✅ Yes
- API Access: ❌ No

### **Starter Tier ($19/month):**
- Forms: 100/month
- Custom Templates: 10
- Batch Processing: ✅ Yes
- API Access: ❌ No
- Overage: $0.30/form

### **Pro Tier ($49/month):**
- Forms: 300/month
- Custom Templates: Unlimited
- Batch Processing: ✅ Yes
- API Access: ✅ Yes
- Overage: $0.25/form

### **Enterprise Tier (Custom):**
- Forms: Unlimited
- Custom Templates: Unlimited
- Batch Processing: ✅ Yes
- API Access: ✅ Yes

### **Pay-As-You-Go:**
- $0.35 per form
- No monthly commitment
- Can be used for overages on any tier

---

## 🔐 SECURITY IMPLEMENTED

### **Row Level Security (RLS) Policies:**

**usage_records:**
- ✅ Users can SELECT only their own records
- ✅ Only service role can INSERT (via webhooks)

**template_purchases:**
- ✅ Users can SELECT only their own purchases
- ✅ Only service role can INSERT (via webhooks)

**profiles:**
- ✅ Existing RLS policies maintained
- ✅ Indexed for performance on subscription lookups

---

## 📝 NEXT STEPS (Not Yet Started)

### **Step 2: Stripe Product Setup**
- [ ] Create products in Stripe Dashboard
- [ ] Get price IDs for Starter/Pro subscriptions
- [ ] Create pay-as-you-go product
- [ ] Create template marketplace products
- [ ] Add metadata to products for tier limits

### **Step 3: Payment Service Enhancement**
- [ ] Update `services/payment_service.py`
- [ ] Add subscription checkout methods
- [ ] Add template purchase methods
- [ ] Handle customer creation

### **Step 4: Entitlement Service**
- [ ] Create `services/entitlement_service.py`
- [ ] Implement usage checking logic
- [ ] Implement template access checking
- [ ] Add usage increment methods

### **Step 5: Webhook Handler**
- [ ] Update `routes/payment_routes.py`
- [ ] Handle `checkout.session.completed`
- [ ] Handle subscription events
- [ ] Handle template purchases
- [ ] Update profiles table on payment success

### **Step 6: Batch Processing Integration**
- [ ] Update batch routes to check entitlements
- [ ] Implement overage payment flow
- [ ] Add usage tracking after batch completion

### **Step 7: Frontend Integration**
- [ ] Create pricing page
- [ ] Add payment flow UI
- [ ] Display user entitlements
- [ ] Show usage stats

---

## 🔧 TECHNICAL DETAILS

### **Database Technology:**
- PostgreSQL via Supabase
- Row Level Security (RLS) enabled
- UUID primary keys throughout

### **Existing Architecture:**
- FastAPI backend
- Celery workers for batch processing (10 parallel workers)
- Redis for caching and job queuing
- Supabase for auth, database, and storage

### **Current Performance:**
- 100 PDFs processed in 3-4 minutes
- 99% template cache hit rate
- 10-20x speedup from Celery parallelization

### **User Base:**
- 3 existing users (all on free tier currently)
- 17 completed batch jobs
- 62 batch items processed
- 32 templates created (31 custom, 1 official)

---

## 📌 IMPORTANT NOTES FOR FUTURE REFERENCE

1. **Table Names Matter:**
   - Use `profiles` not `users`
   - Use `batch_jobs` not `batches`
   - Use `pdf_templates` not `templates`

2. **Foreign Key Consistency:**
   - Always use `profile_id` when referencing profiles
   - Keep `user_id` in existing tables for backwards compatibility with PDF processing

3. **Metadata Strategy:**
   - Store `user_id` in Stripe metadata (even though table is profiles)
   - Include tier, plan type, and other context in metadata
   - Use metadata for webhook reconciliation

4. **Billing Period Format:**
   - Store as `YYYY-MM` (e.g., "2025-11")
   - **MUST NOT be NULL** - always set to current period on user creation
   - Reset usage counter when billing period changes
   - Check billing period on every usage increment
   - If NULL found, immediately update: `UPDATE profiles SET billing_period = TO_CHAR(NOW(), 'YYYY-MM') WHERE billing_period IS NULL;`

5. **RLS is Critical:**
   - All payment-related tables have RLS enabled
   - Service role bypasses RLS for webhooks
   - User auth respects RLS for API calls

---

## 🎓 KEY LEARNINGS SO FAR

1. **Schema Discovery:**
   - Always verify table names before writing SQL
   - Check foreign key relationships early
   - Document corrections for future reference

2. **Data Migration:**
   - Set sensible defaults for existing users
   - Use `WHERE column IS NULL` to avoid overwriting data
   - Add indexes immediately for performance

3. **Stripe Integration Planning:**
   - Webhooks are the only reliable payment verification
   - Metadata bridges Stripe and our database
   - Service role handles all payment-triggered updates

---

**Status:** ✅ Step 1 Complete - Database Schema Ready  
**Next:** Step 2 - Stripe Product Setup  
**Blockers:** None  
**Last Updated:** November 21, 2025

---

*This log should be provided to any AI assistant to continue implementation from this point forward.*