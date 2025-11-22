# 🎯 BULKFORM STRIPE PAYMENT INTEGRATION - COMPLETE CONTEXT

**Date Started:** November 21, 2025  
**Project:** BulkForm - B2B SaaS PDF Form Automation  
**Developer:** Tari Yekorogha (Solo Founder)  
**Goal:** Implement hybrid pricing model (free single-form fills + paid bulk processing) with entitlements and usage tracking to reach $1K MRR and 10 paying customers by December 2025

---

## 📋 TABLE OF CONTENTS

1. [Project Overview](#project-overview)
2. [The BulkForm Business Model](#the-bulkform-business-model)
3. [Pricing Model](#pricing-model)
4. [Completed Work](#completed-work)
5. [Database Schema](#database-schema)
6. [Technical Stack](#technical-stack)
7. [Next Steps](#next-steps)
8. [Important Notes](#important-notes)

---

## 🎯 PROJECT OVERVIEW

### **What is BulkForm?**
BulkForm is a B2B SaaS application that automates PDF form filling using a grid-based coordinate system (150×150 grid at 300 DPI). The platform serves three distinct user needs:

1. **Template-Based Single-Form Filling (FREE):** Quick form filling using pre-made templates with a simple web form
2. **Single-Fill Mapping (FREE):** Interactive PDF mapper to create custom templates from any PDF
3. **Bulk Processing (PAID):** Industrial-strength automation for professionals processing large volumes (50+ monthly)

### **Target Users:**
- **Free Users:** Anyone who needs to fill a form once or create a custom template
- **Paid Users:** Immigration lawyers, HR departments, real estate agents, tax preparers, small law firms who process forms at scale

### **Core Value Proposition**
**"Map once, fill thousands. Or just fill one - your choice."**

The magic moment: Someone needs to sign your NDA → They go to BulkForm → Sign up (30 seconds) → Click "BulkForm NDA Template" → Fill simple web form → Download PDF → Done in 2 minutes.

When they need to fill 100 NDAs? That's when bulk processing (and payment) comes in.

### **Current Performance**
- **Processing Speed:** 100 PDFs in 3-4 minutes (10-20x improvement from 43 minutes)
- **Architecture:** FastAPI + Celery (10 parallel workers) + Redis + Supabase
- **Caching:** 99% template cache hit rate
- **Security:** End-to-end encryption, Row Level Security (RLS), private storage with signed URLs

### **Current User Base**
- 3 existing users (all on free tier)
- 17 completed batch jobs
- 62 batch items processed
- 33 templates in database (32 custom, 1 official)

---

## 🎯 THE BULKFORM BUSINESS MODEL

### **The Core Insight**
Everyone needs to fill a form at some point in their life. But most people only need to fill ONE form. The real money is in serving professionals who need to fill HUNDREDS of forms.

### **Three Distinct Flows**

#### **Flow 1: Template-Based Single-Fill (FREE for Free Templates)** 🔴 TO IMPLEMENT
```
User (MUST BE SIGNED IN) → Template Page → "Fill Single Form - FREE" →
Simple Web Form (Name, Address, Date, etc.) →
Click "Generate PDF" →
Instant Download (5 seconds) →
Done.
```

**Key Points:**
- ✅ **Authentication required** - must be signed in
- ✅ **Free templates** - accessible to all signed-in users
- ✅ **Paid templates** - require annual subscription ($10-25/year per template)
- ✅ Simple web form interface - no clicking or mapping
- ✅ Pre-mapped templates - just fill and download
- ✅ Perfect for viral sharing: "Hey, sign this NDA using BulkForm"
- ✅ SEO gold: "free I-485 form filler", "free NDA generator"
- ✅ The primary hook that gets everyone to try BulkForm

**Technical Implementation:**
- Direct PDF generation (no batch system)
- Synchronous FastAPI endpoint
- Minimal database writes (optional history tracking)
- Uses existing template mappings

**Status:** NOT YET IMPLEMENTED (Step 3)

---

#### **Flow 2: Single-Fill Mapping (FREE Forever)** ✅ ALREADY BUILT
```
User (MUST BE SIGNED IN) → /single-fill → Upload PDF →
Click on PDF to map fields →
Configure field properties →
Fill values →
Generate PDF →
Optional: Save as Template
```

**Key Points:**
- ✅ **Authentication required** - must be signed in
- ✅ **Interactive mapper** - click to place text fields and images
- ✅ **Free for all tiers** - no payment required
- ✅ **Subject to custom template limits** - 3 for free, 10 for starter, unlimited for pro
- ✅ Used to create custom templates from any PDF
- ✅ One-time use or save for future bulk processing
- ✅ The power user's tool for unique forms
- ✅ **Can bypass paid templates** - map any PDF yourself for free

**Technical Implementation:**
- Grid-based coordinate mapping system (150×150 grid)
- Canvas click events for field placement
- Field configuration UI with real-time preview
- Optional template save to database
- Synchronous PDF generation (5 seconds)

**Status:** ✅ FULLY IMPLEMENTED (existing codebase)

---

#### **Flow 3: Bulk Processing (PAID)**
```
User (MUST BE SIGNED IN) → Template Page → "Use for Bulk Processing" →
Upload CSV/JSON with 50+ rows →
Check entitlements (do they have 50 forms available?) →
If not, prompt payment →
Create batch_jobs record →
Celery workers process in parallel →
Poll progress →
Download ZIP
```

**Key Points:**
- ✅ **Authentication required** - need to track usage
- ✅ **This is the current system** - already built and working
- ✅ **This is what we charge for** - the industrial automation
- ✅ 10-20x speed improvement saves hours
- ✅ Can use any template (official, purchased, or custom)

**Status:** ✅ FULLY IMPLEMENTED (existing codebase)

---

### **The User Journey**

**Act 1: Discovery (Free)**
1. Jane needs to sign a form for her friend
2. Friend sends: "Fill this out: bulkform.com/templates/nda"
3. Jane signs up for free account (30 seconds - Google OAuth)
4. Jane clicks "Fill Single Form - FREE"
5. Jane fills simple web form in 2 minutes
6. Jane downloads PDF
7. Jane thinks: "Wow, that was easy"

**Act 2: The Custom Need**
8. Jane has a unique company form not in the template library
9. Jane goes to `/single-fill`
10. Jane uploads PDF and maps fields by clicking (5 minutes)
11. Jane fills values and downloads PDF
12. Jane saves as template: "Company Onboarding Form"
13. Jane now has a reusable custom template

**Act 3: The Problem (Realization)**
14. Months later, Jane's company needs to process 100 onboarding forms
15. Jane remembers BulkForm
16. Jane goes to her custom template
17. Jane uploads CSV with 100 rows

**Act 4: The Sale (Conversion)**
18. BulkForm says: "You need 100 forms. Free tier includes 20/month."
19. BulkForm offers: "Pay $28 for 80 more forms, or upgrade to Starter ($19/mo) for 100 forms + save $9"
20. Jane upgrades to Starter
21. BulkForm processes all 100 forms in 3 minutes
22. Jane is a customer for life

### **Why This Works**
- **Low barrier to entry:** Free template-based fills get users in the door (30 seconds to value)
- **Power user tool:** Single-fill mapping for unique forms (builds custom template library)
- **Natural upgrade path:** Once you see the magic, you want it for bulk
- **Self-qualifying customers:** Only people who process volume will pay
- **Word-of-mouth growth:** Every free user is a potential advertiser
- **Product-led growth:** The product sells itself through use

---

## 💰 PRICING MODEL

### **The Three-Tier Concept**

**Tier 0: Single-Form Fills (Two Modes)**
- Template-based: Free templates are free, paid templates require annual subscription ($10-25/year)
- Mapping mode: Always free, subject to custom template limits
- Account required for both

**Tier 1: Free Bulk Processing**
- Account required
- 20 bulk forms/month included
- 3 custom templates

**Tier 2+: Paid Bulk Processing**
- Starter: $19/mo for 100 bulk forms
- Pro: $49/mo for 300 bulk forms
- Enterprise: Custom pricing for unlimited

---

### **SUBSCRIPTION TIERS**

#### **Free Tier** (Current - All Users)
**Price:** $0/month  
**Features:**
- ✅ **Unlimited template-based single-form fills** (free templates only, account required)
- ✅ **Unlimited single-fill mapping** (create custom templates by mapping any PDF, account required)
- ✅ 3 custom templates can be saved
- ✅ 20 bulk forms per month
- ✅ Batch processing (up to bulk limit)
- ✅ Basic support
- ❌ No API access

**Use Case:** Testing BulkForm, personal projects, occasional form filling, creating a few custom templates

**Value Prop:** "Experience the full power of BulkForm before you pay anything"

---

#### **Starter Tier**
**Price:** $19/month  
**Features:**
- ✅ **Unlimited template-based single-form fills** (free templates only)
- ✅ **Unlimited single-fill mapping** (create custom templates from any PDF)
- ✅ 10 custom templates can be saved
- ✅ 100 bulk forms per month
- ✅ Batch processing
- ✅ Email support
- ❌ No API access

**Overage Pricing:** $0.30 per additional bulk form  
**Target Customers:** Small law firms, solo practitioners, HR departments (1-5 employees)  
**Monthly Value:** Process 100 forms in ~3 minutes vs. ~2 hours manual = saves $60-100 in labor  
**ROI:** Pays for itself after processing ~20-30 forms

---

#### **Pro Tier**
**Price:** $49/month  
**Features:**
- ✅ **Unlimited template-based single-form fills** (free templates only)
- ✅ **Unlimited single-fill mapping** (create custom templates from any PDF)
- ✅ Unlimited custom templates
- ✅ 300 bulk forms per month
- ✅ Batch processing
- ✅ Priority support
- ✅ API access
- ✅ Advanced analytics

**Overage Pricing:** $0.25 per additional bulk form  
**Target Customers:** Medium-sized firms, immigration law offices, HR consulting firms (5-20 employees)  
**Monthly Value:** Process 300 forms in ~9 minutes vs. ~6 hours manual = saves $180-300 in labor  
**ROI:** Pays for itself after processing ~50-75 forms

---

#### **Enterprise Tier**
**Price:** Custom (Starting at $200/month)  
**Features:**
- ✅ **Unlimited template-based single-form fills** (ALL templates free, including paid ones)
- ✅ **Unlimited single-fill mapping** (create unlimited custom templates)
- ✅ Unlimited custom templates
- ✅ Unlimited bulk forms
- ✅ Batch processing
- ✅ Dedicated account manager
- ✅ API access
- ✅ White-label options
- ✅ Custom integrations
- ✅ SLA guarantees (99.9% uptime)
- ✅ Custom template development service
- ✅ Priority Celery workers (dedicated queue)

**Target Customers:** Large law firms, enterprise HR departments, government agencies (20+ employees)  
**Monthly Value:** Unlimited processing = potentially saves hundreds of hours  
**Custom Pricing Based On:**
- Forms processed per month
- Number of users/seats
- Custom integration requirements
- SLA requirements

---

### **PAY-AS-YOU-GO (PAYG)**

**Price:** $0.35 per bulk form  
**No Monthly Commitment**

**Features:**
- ✅ **Unlimited template-based single-form fills** (free templates only)
- ✅ **Unlimited single-fill mapping** (create custom templates from any PDF)
- ✅ Process any number of bulk forms on-demand
- ✅ No subscription required
- ✅ Access to all features during processing
- ❌ No custom template storage beyond 3 (unless on paid tier)

**Use Cases:**
1. **One-time projects:** User needs to bulk process 50 forms once (pays $17.50)
2. **Overage on subscriptions:** Starter user processes 120 forms (100 included + 20 PAYG at $0.30 = $6)
3. **Seasonal spikes:** Tax season, immigration filing deadlines
4. **Evaluation:** "I want to try bulk processing before subscribing"

**How Overage Works:**
- **Free Tier:** User with 0 bulk forms remaining → Charged $0.35/form for overage
- **Starter Tier:** User with 0 bulk forms remaining → Charged $0.30/form for overage (discounted rate)
- **Pro Tier:** User with 0 bulk forms remaining → Charged $0.25/form for overage (best rate)

**Example:**
- Free user needs to bulk process 50 forms
- Has 20 included, needs 30 more
- Options:
  - Pay $10.50 (30 × $0.35) one-time
  - Upgrade to Starter for $19/mo (get 100 forms, save $8.50 this month)

---

### **TEMPLATE MARKETPLACE**

**Current Strategy:** Some official templates are FREE for template-based single-fills (the hook). Premium templates require **annual subscription** (not one-time purchase). Single-fill mapping is ALWAYS free regardless of template.

---

#### **Template Pricing Strategy - ANNUAL SUBSCRIPTION MODEL**

**The Reality:** Recurring revenue is essential. All template access is **annual subscription** (auto-renews yearly).

---

**Option A: Annual All-Access Pass (Recommended)**

**Price:** $99/year (auto-renews)

**What You Get:**
- ✅ Unlimited access to ALL official BulkForm templates
- ✅ Includes all current templates
- ✅ Includes all future templates we add
- ✅ Works for both single-fills AND bulk processing
- ✅ Auto-renews annually (cancel anytime)

**Best For:** Users who need 5+ premium templates per year

**Value Proposition:** If you need more than 4 premium templates, this pass pays for itself

---

**Option B: Individual Template Annual Subscriptions**

**Pricing Based on Complexity:**

**Simple Templates (1-3 pages):** $10/year
- Examples: NDA, basic W-9, simple lease agreements
- Low field count (under 20 fields)
- Quick to map (under 20 minutes)

**Medium Templates (4-8 pages):** $15/year
- Examples: Residential lease, employment contracts, moderately complex forms
- Medium field count (20-50 fields)
- Moderate mapping time (20-45 minutes)

**Complex Templates (9+ pages):** $20-25/year
- Examples: I-485 (18 pages), I-130, complex tax forms, multi-part applications
- High field count (50+ fields)
- Significant mapping time (45+ minutes)

**All Individual Subscriptions:**
- ✅ Auto-renew annually
- ✅ Work for both single-fills AND bulk processing
- ✅ Lifetime access while subscription is active
- ✅ Cancel anytime

---

**Template Pricing Formula:**

```
Base Price: $8/year
+ Pages: $0.50 per page (max $10)
+ Time to map: $1 per 10 minutes
+ Complexity bonus: $0-5

Examples:
- 2-page NDA, 20 min to map = $8 + $1 + $2 + $0 = $11 → Round to $10/year
- 18-page I-485, 90 min to map = $8 + $9 + $9 + $5 = $31 → Round to $25/year
- 6-page Lease, 45 min to map = $8 + $3 + $5 + $2 = $18 → Round to $15/year
```

---

**The Recommended Strategy: BOTH OPTIONS**

Offer both the Annual Pass AND individual subscriptions:

1. **Power users** (need 5+ templates) → Buy Annual Pass ($99/year)
2. **Casual users** (need 1-2 templates) → Buy individual subscriptions ($10-25/year each)
3. **Smart users** (don't want to pay) → Use single-fill mapping mode to bypass (FREE)

**The Psychology:**
- Annual Pass feels like a deal if you need multiple templates
- Individual subscriptions are low-commitment entry points
- Recurring revenue every year (not just once)
- Auto-renew = passive income
- Single-fill mapping mode = keeps users who won't pay engaged

---

**Important Note About Bypassing:**

Users can ALWAYS bypass paid templates by using **single-fill mapping mode** to create their own custom version (FREE). This is actually good:

1. ✅ Keeps price-sensitive users engaged with BulkForm
2. ✅ They still count toward your user base
3. ✅ They still use bulk processing (where you make real money)
4. ✅ They may upgrade to paid templates later when they realize time is money
5. ✅ Creates template limit pressure (3 free custom templates → upgrade to save more)

---

### **USAGE TRACKING RULES**

**What Counts Toward Monthly Bulk Limit:**
- ✅ Bulk processing only (batch with 2+ forms)
- ✅ Each form in a batch counts as 1 form
- ✅ CSV upload with 50 rows = 50 forms used

**What Does NOT Count:**
- ❌ Template-based single-form fills (unlimited with account)
- ❌ Single-fill mapping (unlimited with account)
- ❌ Template creation/saving (subject to custom template limit, not usage limit)
- ❌ Failed/errored bulk forms (retry for free)
- ❌ PAYG bulk forms (tracked separately in usage_records)

**Example Monthly Usage:**
- User on Starter plan (100 bulk forms/month)
- Week 1: Template-based single-fill 5 NDAs for clients (FREE, 0 forms used)
- Week 2: Map and fill 2 custom forms using single-fill mapping (FREE, 0 forms used, 2 custom templates created)
- Week 3: Bulk process 40 employee onboarding forms (40 forms used, 60 remaining)
- Week 4: Template-based single-fill 10 lease agreements (FREE, still 60 remaining)
- Week 5: Bulk process 70 tax forms (70 forms used, 0 remaining, 10 overage @ $0.30 = $3.00)
- Total bill: $19 subscription + $3 overage = $22

---

### **IMPORTANT: Single-Form Fill Access Rules**

**Authentication Required:**
- ✅ Users MUST be signed in for ALL features
- ✅ No anonymous access to any feature
- ✅ Reason: Track template usage, build user database, enable features

**Template Access for Single Fills:**

| Template Type | Template-Based Single-Fill | Single-Fill Mapping | Bulk Processing |
|---------------|---------------------------|---------------------|-----------------|
| Free Official Template | FREE (with sign-up) | FREE (always) | FREE (within plan limits) |
| Paid Official Template | $10-25/year subscription | FREE (always - bypass!) | Same subscription required |
| Custom Template (yours) | FREE | FREE (always) | FREE (within plan limits) |
| Custom Template (others) | Depends on owner | FREE (map yourself) | Depends on owner |

**Annual Subscription Benefits:**
- ✅ Subscribe to a premium template → Use for template-based fills AND bulk processing
- ✅ Auto-renews annually (recurring revenue)
- ✅ Access while subscription is active
- ✅ OR skip subscription and use single-fill mapping to create your own version (FREE)

---

### **THE TWO SINGLE-FILL MODES EXPLAINED**

BulkForm offers two distinct ways to fill a single form:

#### **Mode 1: Single-Fill Mapping (Already Built)** ✅
**Route:** `/single-fill` → `/single-fill/mapping`

**What it is:**
- Interactive PDF mapper where you click to place fields
- Used to create custom templates from blank PDFs
- Map once, use forever (or just use once and discard)

**User Flow:**
1. User uploads any PDF
2. Click on PDF to add text fields and images
3. Name and configure each field
4. Fill in values
5. Generate filled PDF
6. Optional: Save as reusable template

**Authentication:** Required

**Restrictions:**
- Counts toward custom template limit (3 free, 10 starter, unlimited pro) IF saved
- No tier restrictions on usage itself
- Always free for all signed-in users
- Can map ANY PDF, even paid official templates (bypassing subscription)

**Use Cases:**
- "I have a blank form and want to fill it once (or create a template)"
- "I need to map a new form that's not in the template library"
- "I don't want to pay for the official I-485 template, so I'll map it myself"
- Template creation workflow

**Technical Details:**
- Grid-based coordinate system (150×150 at 300 DPI)
- Canvas click events capture pixel coordinates
- Converts to grid coordinates for storage
- Supports text fields and image placement
- Real-time field configuration UI
- Optional template save to database
- Synchronous PDF generation (5 seconds)

---

#### **Mode 2: Template-Based Single-Fill (To Be Implemented)** 🔴
**Route:** `/templates/{id}/fill-single` → Simple web form

**What it is:**
- Pre-mapped templates with a simple web form
- No clicking, no mapping - just fill fields and download
- Uses existing templates (official or custom)

**User Flow:**
1. User browses template library
2. Clicks "Fill Single Form - FREE" (or subscribes if paid template)
3. Sees simple web form with labeled fields
4. Fills in values
5. Clicks "Generate PDF"
6. Downloads instantly

**Authentication:** Required

**Restrictions:**
- Free templates: Free for all signed-in users
- Paid templates: Requires annual subscription ($10-25/year)
- Does NOT count toward any limits (unlimited)
- Does NOT count toward custom template limits

**Use Cases:**
- "I want to quickly fill out an NDA using the official template"
- "My friend sent me a template link to fill out"
- "I need one copy of Form I-485 filled with my info (and I subscribed)"

**Technical Details:**
- Load template field mappings from database
- Generate web form dynamically from field definitions
- Synchronous PDF generation using stored coordinates
- No canvas interaction required

---

#### **Key Differences**

| Feature | Single-Fill Mapping | Template-Based Single-Fill |
|---------|---------------------|---------------------------|
| **Route** | `/single-fill` | `/templates/{id}/fill-single` |
| **Interaction** | Click to map fields | Simple web form |
| **Purpose** | Create templates / one-off mapping | Use existing templates |
| **Setup Time** | 5-10 minutes (mapping) | 30 seconds (just fill) |
| **Repeatable** | Can save as template | Template already exists |
| **Limits** | 3/10/unlimited custom templates (if saved) | Unlimited (free templates) |
| **Payment** | Always free | Free or $10-25/year (paid templates) |
| **Can Bypass Paid Templates** | ✅ Yes (map it yourself) | ❌ No (must subscribe) |
| **Status** | ✅ Built | 🔴 To be implemented |

---

#### **User Journey Example**

**Scenario 1: First-time NDA user (Template-Based)**
1. User signs up
2. Sees "BulkForm NDA Template" (free)
3. Clicks "Fill Single Form - FREE"
4. Gets simple form: Name, Date, Signature
5. Fills it out in 30 seconds
6. Downloads PDF
7. **Does NOT use mapping mode** - template already exists

**Scenario 2: Custom form user (Mapping Mode)**
1. User has a unique company form
2. Goes to `/single-fill`
3. Uploads company form PDF
4. Maps fields by clicking (5 minutes)
5. Fills values
6. Downloads filled PDF
7. Saves as template: "Company Onboarding Form"
8. Next time: Can use template-based flow instead

**Scenario 3: Smart user avoiding payment (Mapping Mode)**
1. User needs Form I-485 (paid template, $25/year)
2. User doesn't want to pay
3. User downloads blank I-485 from USCIS website
4. User goes to `/single-fill`
5. User maps I-485 fields themselves (20 minutes)
6. User fills and downloads
7. User saves as custom template
8. **User never paid for official template** - mapped it themselves

**Scenario 4: Bulk user**
1. User needs 100 NDAs
2. Uses `/templates/nda/use` (bulk flow)
3. Uploads CSV with 100 rows
4. Pays for bulk processing
5. Downloads ZIP
6. **Never touches single-fill** - they need volume

---

### **Complete Feature Access Matrix**

| Feature | Free | Starter | Pro | Enterprise |
|---------|------|---------|-----|------------|
| **Template-Based Single-Fill (Free Templates)** | Unlimited | Unlimited | Unlimited | Unlimited |
| **Template-Based Single-Fill (Paid Templates)** | $10-25/year each | $10-25/year each | $10-20/year each | FREE |
| **Annual Template Pass** | $99/year | $99/year | $99/year | FREE (included) |
| **Single-Fill Mapping** | Unlimited | Unlimited | Unlimited | Unlimited |
| **Custom Templates Saved** | 3 | 10 | Unlimited | Unlimited |
| **Bulk Forms/Month** | 20 | 100 | 300 | Unlimited |
| **API Access** | ❌ | ❌ | ✅ | ✅ |
| **Priority Support** | ❌ | Email | Priority | Dedicated |

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

-- Fix billing_period for any NULL values
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
- `forms_used_this_month`: **BULK forms usage counter only** (resets each billing period)
- `forms_included_in_plan`: Bulk forms included in current tier (20 for free, 100 for starter, 300 for pro)
- `custom_templates_count`: Number of custom templates user has created/saved
- `billing_period`: Current billing period (YYYY-MM format) - **MUST NOT BE NULL**

**Important Notes:** 
- `forms_used_this_month` tracks **bulk processing only**
- Template-based single-form fills do NOT increment this counter
- Single-fill mapping does NOT increment this counter
- Saving a template does increment `custom_templates_count` (subject to tier limits)

**Current State:**
- 3 existing users in database
- All set to `free` tier with 20 bulk forms/month limit
- All have `billing_period` set to current month (2025-11)

---

#### **1.2 Created Usage Records Table** ✅

**What We Did:**
- Created table to track pay-as-you-go bulk form processing charges
- Linked to existing `batch_jobs` table (NOT `batches` - corrected during implementation)
- Implemented Row Level Security (RLS)

**SQL Executed:**
```sql
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    batch_id UUID REFERENCES batch_jobs(id) ON DELETE SET NULL,
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
- Tracks all pay-as-you-go **bulk processing** charges
- Associates charges with batch jobs when applicable
- Stores Stripe PaymentIntent IDs for reconciliation
- Enables usage analytics and billing history
- **Does NOT track single-form fills** (those are free and don't need tracking)

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
- Created table to track template marketplace subscriptions
- Linked to existing `pdf_templates` table (NOT `templates` - corrected during implementation)
- Supports annual subscriptions (auto-renew) and annual pass
- Implemented RLS and unique constraint to prevent duplicate active subscriptions

**SQL Executed:**
```sql
CREATE TABLE template_purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    template_id UUID REFERENCES pdf_templates(id) ON DELETE CASCADE,
    purchase_type VARCHAR(20) NOT NULL, -- 'annual_template', 'annual_pass'
    amount_paid INTEGER NOT NULL, -- cents
    stripe_subscription_id TEXT, -- For recurring subscriptions
    stripe_payment_intent TEXT, -- For one-time payments (if any)
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL, -- Always set (365 days from purchase)
    auto_renew BOOLEAN DEFAULT true,
    UNIQUE(profile_id, template_id) -- Prevent duplicate active subscriptions
);

-- Indexes
CREATE INDEX idx_template_purchases_profile ON template_purchases(profile_id);
CREATE INDEX idx_template_purchases_template ON template_purchases(template_id);
CREATE INDEX idx_template_purchases_expires ON template_purchases(expires_at);
CREATE INDEX idx_template_purchases_subscription ON template_purchases(stripe_subscription_id);

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
- Tracks template marketplace annual subscriptions
- Supports two purchase types:
  - `annual_template`: Annual subscription to a specific premium template ($10-25/year)
  - `annual_pass`: Annual subscription to ALL official templates ($99/year)
- Prevents users from having duplicate active subscriptions (UNIQUE constraint)
- All subscriptions expire after 365 days and auto-renew
- Stores Stripe subscription IDs for managing renewals/cancellations

**Current Strategy:** All template access is **annual subscription** (recurring revenue). Single-fill mapping is ALWAYS free regardless.

**Existing Templates Data:**
- 33 templates in `pdf_templates` table
- 1 official template: `OFFICIAL_BF_NDA_TEMPLATE` (marked as paid in `price` field)
- 32 custom user templates

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

#### **1.4 Updated PDF Templates Table** ✅

**What We Did:**
- Added pricing and subscription-related columns to existing `pdf_templates` table
- Created computed column `is_free` that auto-updates based on `price`
- No redundant columns added

**SQL Executed:**
```sql
-- Add ONLY missing columns (is_official and price already exist)
ALTER TABLE pdf_templates
ADD COLUMN is_free BOOLEAN GENERATED ALWAYS AS (price::NUMERIC = 0) STORED,
ADD COLUMN stripe_price_id TEXT,
ADD COLUMN complexity VARCHAR(20),
ADD COLUMN rental_duration_days INTEGER DEFAULT 365;

-- Set complexity for existing official template
UPDATE pdf_templates
SET 
    complexity = 'simple',
    rental_duration_days = 365
WHERE name = 'OFFICIAL_BF_NDA_TEMPLATE';
```

**Key Schema Additions:**
- `is_free`: **Generated column** - auto-computed from `price` field (true if price = 0)
- `stripe_price_id`: Links each template to its Stripe annual subscription product
- `complexity`: 'simple', 'medium', 'complex' (for pricing formula)
- `rental_duration_days`: Always 365 for annual subscription model

**Existing Columns (Already Present):**
- ✅ `is_official`: Marks BulkForm official templates (vs user custom templates)
- ✅ `price`: Annual subscription price stored as string (e.g., "10.00", "0.00")
- ✅ `category`: Template categorization (e.g., "HR", "Legal")

**Notes:**
- `is_free` automatically updates when `price` changes (no manual updates needed)
- `stripe_price_id` will be populated after creating Stripe products
- Template subscriptions are ALWAYS annual (365 days)

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

### **STEP 2: STRIPE PRODUCT SETUP** 🔴 NOT STARTED

**Status:** Ready to implement  
**Next Action:** Create products in Stripe Dashboard

---

## 📊 DATABASE SCHEMA

### **Tables Modified/Created:**

1. ✅ **`profiles`** - Extended with subscription columns (tracks bulk usage only)
2. ✅ **`usage_records`** - New table for pay-as-you-go bulk processing tracking
3. ✅ **`template_purchases`** - New table for template annual subscriptions
4. ✅ **`pdf_templates`** - Extended with pricing columns (includes generated `is_free` column)

### **Existing Tables Referenced:**
- **`batch_jobs`** - Links to usage records (17 jobs exist) - **BULK PROCESSING ONLY**
- **`batch_items`** - Batch processing data (62+ items exist) - **BULK PROCESSING ONLY**

### **Complete Schema Relationships:**

```
profiles (id)
    ↓ (1:many)
    ├─ batch_jobs (user_id) [BULK PROCESSING ONLY]
    │   ↓ (1:many)
    │   └─ batch_items (batch_id)
    │
    ├─ usage_records (profile_id) [TRACKS BULK CHARGES ONLY]
    │   ↓ (many:1) optional
    │   └─ batch_jobs (batch_id)
    │
    ├─ template_purchases (profile_id) [ANNUAL SUBSCRIPTIONS]
    │   ↓ (many:1) optional
    │   └─ pdf_templates (template_id)
    │
    └─ pdf_templates (user_id) [CUSTOM TEMPLATES]
```

### **Key Schema Corrections Made:**
1. ✅ Used `batch_jobs` instead of `batches` (non-existent table)
2. ✅ Used `pdf_templates` instead of `templates` (actual table name)
3. ✅ Used `profile_id` in foreign keys instead of `user_id` (matching profiles table)
4. ✅ Fixed NULL `billing_period` values (MUST always be set)
5. ✅ Made `is_free` a generated column (auto-computed, no manual updates)
6. ✅ Changed template pricing from "buy once use forever" to annual subscriptions

---

## 🔧 TECHNICAL STACK

### **Backend:**
- **Framework:** FastAPI (Python)
- **Package Manager:** uv (Windows PowerShell environment)
- **Background Jobs:** Celery with 10 parallel workers (BULK PROCESSING ONLY)
- **Caching:** Redis (template caching, job queuing)
- **Database:** PostgreSQL via Supabase
- **Storage:** Supabase Storage (private buckets with signed URLs)
- **Authentication:** Supabase Auth (email/password + Google OAuth with PKCE)

### **Frontend:**
- **Template Layer:** Django
- **Styling:** Tailwind CSS
- **API Communication:** JavaScript
- **Canvas Interaction:** HTML5 Canvas for single-fill mapping mode

### **PDF Processing:**
- **Libraries:** pypdf, reportlab, PIL
- **Grid System:** 150×150 grid at 300 DPI
- **Single-Form Speed:** ~5 seconds per PDF (synchronous generation)
- **Bulk Processing Speed:** 3-4 minutes for 100 PDFs (Celery parallel workers)

### **Security:**
- **Encryption:** End-to-end encryption for sensitive data
- **Storage:** Private buckets with signed URLs (1-hour expiry)
- **Database:** Row Level Security (RLS) policies on all payment tables
- **Sessions:** Database-backed sessions (not in-memory)
- **Code Protection:** Client-side obfuscation to protect IP

### **Deployment:**
- **Backend:** Render (automatic GitHub integration)
- **Frontend:** PythonAnywhere (Django hosting)
- **Celery Workers:** Render (10 concurrent workers for bulk processing)
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
- [ ] Create Pay-As-You-Go product ($0.35 one-time per form)
- [ ] Create Annual Template Pass product ($99/year recurring)
- [ ] Create individual template subscription products ($10-25/year recurring, as you map each template)
- [ ] Add metadata to products for entitlement logic
- [ ] Copy price IDs to environment variables
- [ ] Set up webhook endpoint in Stripe Dashboard
- [ ] Get webhook signing secret

**Environment Variables Needed:**
```bash
STRIPE_SECRET_KEY=sk_test_***
STRIPE_PUBLISHABLE_KEY=pk_test_***
STRIPE_WEBHOOK_SECRET=whsec_***
STRIPE_API_VERSION=2024-12-18.acacia

# Subscription Price IDs
PRICE_STARTER_MONTHLY=price_***
PRICE_PRO_MONTHLY=price_***
PRICE_PAYG=price_***

# Template Subscription Price IDs
PRICE_TEMPLATE_ANNUAL_PASS=price_***

# Individual template price IDs (create as you map templates)
# Store these in pdf_templates.stripe_price_id column
```

---

### **Step 3: Implement Template-Based Single-Form Fill Flow** 🔴 NOT STARTED
**This is the simple, no-mapping flow for existing templates**

**IMPORTANT:** The single-fill mapping flow (`/single-fill`) is already built and working. This step is ONLY for implementing the template-based flow where users fill a simple web form.

**Tasks:**
- [ ] Create new route: `GET /templates/{id}/fill-single` (REQUIRES AUTH)
- [ ] Add template access check (free template or active annual subscription)
- [ ] If paid template without subscription, redirect to subscription purchase flow
- [ ] Build simple web form UI dynamically from template field mappings
- [ ] Create endpoint: `POST /pdf/generate-from-template` (REQUIRES AUTH)
- [ ] Implement synchronous PDF generation using stored template coordinates
- [ ] Return PDF download directly (optional: save to user history)
- [ ] Update template detail page with three buttons:
  - "Fill Single Form - FREE" (or "Subscribe to Fill" for paid templates)
  - "Use for Bulk Processing"
  - "Map It Yourself - FREE" (link to `/single-fill`)

**CLARIFICATION:** These routes are for template-based single-fill ONLY. The existing `/single-fill` routes (upload + mapping) remain unchanged and already work.

**Existing Routes (Already Built):**
```python
# Single-fill mapping flow (already working)
GET  /single-fill                    # Upload page
POST /api/pdf/upload                 # Upload PDF, get session
GET  /single-fill/mapping            # Interactive mapper
POST /api/pdf/fill-text-batch        # Fill mapped fields
POST /api/pdf/add-image              # Add images to PDF
POST /api/pdf/generate               # Generate final PDF
POST /api/templates                  # Save as template
```

**New Routes Needed:**
```python
@app.get("/templates/{template_id}/fill-single")
async def show_template_fill_form(
    template_id: str,
    user_id: str = Depends(get_current_user)  # AUTH REQUIRED
):
    """Show simple web form for template-based single-fill (auth required)"""
    template = get_template(template_id)
    
    # Check if template is free OR user has active subscription
    if not template["is_free"]:
        has_subscription = check_template_subscription(user_id, template_id)
        if not has_subscription:
            return RedirectResponse(f"/templates/{template_id}/subscribe")
    
    # Generate web form from field_mappings
    return render_template("template_fill_form.html", {
        "template": template,
        "fields": template["field_mappings"]
    })

@app.post("/pdf/generate-from-template")
async def generate_pdf_from_template(
    template_id: str,
    field_values: dict,
    user_id: str = Depends(get_current_user)  # AUTH REQUIRED
):
    """Generate single PDF from template (synchronous, no Celery)"""
    template = get_template(template_id)
    
    # Verify user has access
    if not template["is_free"]:
        has_subscription = check_template_subscription(user_id, template_id)
        if not has_subscription:
            raise HTTPException(403, "Active template subscription required")
    
    # Generate PDF
    pdf_bytes = fill_pdf_with_mappings(
        template["pdf_url"],
        template["field_mappings"],
        field_values
    )
    
    return Response(pdf_bytes, media_type="application/pdf")
```

**UI Changes Needed:**
- Template detail page: Add three buttons
- New page: Simple form dynamically generated from template field mappings
- Form should have proper labels from field names in template

---

### **Step 4: Payment Service Enhancement** 🔴 NOT STARTED
**File:** `services/payment_service.py`

**Tasks:**
- [ ] Install Stripe Python library: `uv add stripe`
- [ ] Update existing payment service with new methods:
  - `create_subscription_checkout(user_id, tier, email, customer_id?)` - For bulk plans
  - `create_payg_checkout(user_id, forms_count, email, batch_id?)` - For bulk overages
  - `create_template_subscription_checkout(user_id, template_id, email)` - For individual templates
  - `create_annual_pass_checkout(user_id, email)` - For template annual pass
  - `cancel_subscription(subscription_id)`
  - `reactivate_subscription(subscription_id)`
- [ ] Add Stripe customer creation logic
- [ ] Add metadata to all checkout sessions for webhook reconciliation

**Key Methods to Implement:**
```python
# Bulk processing subscription
PaymentService.create_subscription_checkout(
    user_id="uuid",
    tier="starter",
    email="user@example.com"
)

# Bulk overage payment
PaymentService.create_payg_checkout(
    user_id="uuid",
    forms_count=50,
    email="user@example.com",
    batch_id="uuid"
)

# Individual template subscription
PaymentService.create_template_subscription_checkout(
    user_id="uuid",
    template_id="uuid",
    email="user@example.com"
)

# Annual template pass subscription
PaymentService.create_annual_pass_checkout(
    user_id="uuid",
    email="user@example.com"
)
```

---

### **Step 5: Entitlement Service** 🔴 NOT STARTED
**File:** `services/entitlement_service.py` (NEW FILE)

**Tasks:**
- [ ] Create new service file
- [ ] Implement `get_user_entitlements(profile_id)` - Returns user's current limits and usage
- [ ] Implement `can_process_bulk_forms(profile_id, forms_count)` - Checks if user can bulk process N forms
- [ ] Implement `can_save_custom_template(profile_id)` - Checks custom template limit
- [ ] Implement `has_template_access(profile_id, template_id)` - Checks if user has active subscription to template
- [ ] Implement `increment_bulk_usage(profile_id, forms_count)` - Updates bulk usage counter only
- [ ] Implement `increment_custom_template_count(profile_id)` - Updates custom template counter
- [ ] Implement `reset_monthly_usage(profile_id)` - Resets bulk counter at billing period change
- [ ] Implement `_calculate_overage_cost(tier, overage_count)` - Calculates overage charges

**IMPORTANT:** This service only checks/tracks **bulk processing** and **custom template limits**. Single-form fills (both modes) are free and don't interact with this service for usage limits.

**Core Logic:**
```python
# Bulk usage check
can_process, reason = entitlement_service.can_process_bulk_forms("uuid", 150)

if not can_process:
    # Show payment modal for bulk overage
    pass
else:
    # Proceed with bulk processing
    pass

# Template subscription check
has_access = entitlement_service.has_template_access("uuid", "template_id")

if not has_access:
    # Template requires active subscription
    # Redirect to subscription page
    pass
else:
    # Template is free OR user has active subscription
    # Allow access
    pass

# Single-fill mapping - ALWAYS allowed
# Just proceed (but check custom template limit if saving)
```

**Tier Limits Reference:**
```python
TIER_LIMITS = {
    "free": {
        "bulk_forms_included": 20,
        "custom_templates_limit": 3,
        "template_based_single_fills": "unlimited",
        "single_fill_mapping": "unlimited"
    },
    "starter": {
        "bulk_forms_included": 100,
        "custom_templates_limit": 10,
        "template_based_single_fills": "unlimited",
        "single_fill_mapping": "unlimited"
    },
    "pro": {
        "bulk_forms_included": 300,
        "custom_templates_limit": "unlimited",
        "template_based_single_fills": "unlimited",
        "single_fill_mapping": "unlimited"
    },
    "enterprise": {
        "bulk_forms_included": "unlimited",
        "custom_templates_limit": "unlimited",
        "template_based_single_fills": "unlimited",
        "single_fill_mapping": "unlimited"
    }
}

BULK_OVERAGE_RATES = {
    "free": 35,  # $0.35 per form
    "starter": 30,  # $0.30 per form
    "pro": 25,  # $0.25 per form
}
```

---

### **Step 6: Webhook Handler** 🔴 NOT STARTED
**File:** `routes/payment_routes.py` (UPDATE EXISTING FILE)

**Tasks:**
- [ ] Update existing webhook endpoint to handle new events
- [ ] Handle `checkout.session.completed` for bulk subscriptions (Starter/Pro)
- [ ] Handle `checkout.session.completed` for bulk PAYG
- [ ] Handle `checkout.session.completed` for template subscriptions
- [ ] Handle `customer.subscription.updated` (renewals, upgrades)
- [ ] Handle `customer.subscription.deleted` (cancellations)
- [ ] Handle `invoice.payment_failed` (failed payments)
- [ ] Update `profiles` table on successful bulk subscription payments
- [ ] Insert records into `usage_records` for PAYG bulk charges
- [ ] Insert/update records in `template_purchases` for template subscription renewals

**Critical Webhook Logic:**
```python
# On bulk subscription payment success:
# 1. Update profiles table with subscription info
# 2. Set forms_included_in_plan based on tier
# 3. Reset forms_used_this_month to 0
# 4. Set billing_period to current month
# 5. Update custom_templates_limit based on tier

# On PAYG bulk payment success:
# 1. Insert into usage_records
# 2. Do NOT increment forms_used_this_month

# On template subscription payment success:
# 1. Insert/update template_purchases
# 2. Set expires_at to 365 days from now
# 3. Store stripe_subscription_id for managing renewals

# NEVER track single-form fills in webhooks (they're free)
```

---

### **Step 7: Batch Processing Integration** 🔴 NOT STARTED
**File:** `routes/batch/batch_routes.py` (UPDATE EXISTING FILE)

**Tasks:**
- [ ] Import `EntitlementService` in batch routes
- [ ] Add entitlement check BEFORE processing batch
- [ ] Handle billing period rollovers (reset usage if period changed)
- [ ] Increment bulk usage ONLY for forms included in plan

**Example Flow:**
1. User triggers batch with 150 forms
2. User is on Starter plan (100 included, 20 used = 80 remaining)
3. System calculates: Need 70 more bulk forms @ $0.30 = $21.00
4. Return payment modal to frontend
5. User pays $21.00 via Stripe
6. Webhook inserts usage_record
7. User retriggers batch processing
8. System processes all 150 forms

---

### **Step 8: Frontend Integration** 🔴 NOT STARTED

**Tasks:**
- [ ] **PRIORITY:** Add "Fill Single Form" flow to template pages
- [ ] Create simple form UI for template-based single-fills
- [ ] Update template detail pages with three buttons
- [ ] Add custom template limit warnings in single-fill mapping mode
- [ ] Create pricing page (`/pricing`)
- [ ] Add subscription checkout flows (bulk + templates)
- [ ] Add PAYG checkout for bulk overages
- [ ] Display user's current plan, bulk usage, and custom template count
- [ ] Show "Upgrade" or "Subscribe" buttons when needed
- [ ] Handle payment success/cancel redirects
- [ ] Display usage statistics and billing history

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
  "user_id": "uuid",
  "type": "bulk_subscription" | "payg_bulk" | "template_subscription" | "annual_pass",
  "tier": "starter" | "pro",
  "forms_count": "50",
  "template_id": "uuid",
  "batch_id": "uuid"
}
```

### **4. Billing Period Format**
- ✅ Store as `YYYY-MM` (e.g., "2025-11")
- ✅ **MUST NOT be NULL** - always set on user creation
- ✅ Reset **bulk** usage counter when period changes
- ✅ Check billing period on every bulk usage increment

### **5. RLS is Critical**
- ✅ All payment-related tables have RLS enabled
- ✅ Service role bypasses RLS for webhooks
- ✅ User API calls respect RLS
- ✅ Never expose service key to frontend

### **6. Webhook Verification is Mandatory**
**NEVER trust payment success without webhook verification!**

### **7. Annual Subscription Model**
- ✅ ALL template access is annual subscription (recurring revenue)
- ✅ Individual templates: $10-25/year (based on complexity)
- ✅ Annual Pass: $99/year (all templates)
- ✅ Auto-renews annually via Stripe subscriptions
- ✅ Users can bypass by using single-fill mapping (FREE)

### **8. The Three Flows - Core Differences**

**Template-Based Single-Fill (To Implement):**
- FREE for free templates
- Paid templates require annual subscription ($10-25/year)
- Authentication required
- Simple web form interface
- No usage tracking or limits

**Single-Fill Mapping (Already Built):**
- FREE forever (all tiers)
- Can bypass paid templates (map yourself)
- Subject to custom template limits IF saving
- Interactive canvas interface

**Bulk Processing (Already Built):**
- Paid (subject to tier limits)
- Tracks usage in `forms_used_this_month`
- Uses Celery workers for parallel processing

### **9. Usage Tracking Rules**

**What increments `forms_used_this_month`:**
- ✅ Bulk processing only
- ✅ Only when forms are included in plan

**What increments `custom_templates_count`:**
- ✅ Saving a template in single-fill mapping mode

**What does NOT increment any counter:**
- ❌ Template-based single-form fills
- ❌ Single-fill mapping without saving
- ❌ PAYG bulk forms (tracked separately)

### **10. Template Subscription Access**
```python
def has_template_access(user_id, template_id):
    """Check if user can access template"""
    template = get_template(template_id)
    
    # Free template
    if template["is_free"]:
        return True
    
    # User owns it (custom template)
    if template["user_id"] == user_id:
        return True
    
    # Check active subscription
    subscription = get_active_template_subscription(user_id, template_id)
    if subscription and subscription["expires_at"] > now():
        return True
    
    # Check annual pass
    annual_pass = get_annual_pass(user_id)
    if annual_pass and annual_pass["expires_at"] > now():
        return True
    
    return False
```

---

## 🎓 KEY LEARNINGS

### **1. Business Model Evolution**
- ❌ "Buy once use forever" = financial suicide
- ✅ Annual subscriptions = predictable recurring revenue
- ✅ Let power users bypass paid templates with mapping (builds loyalty)
- ✅ Two free hooks (template-based + mapping) = dual growth engines

### **2. Schema Design**
- ✅ Generated columns eliminate manual updates
- ✅ Always verify table names before writing SQL
- ✅ Document corrections for future reference

### **3. Stripe Integration**
- ✅ Webhooks are the ONLY reliable payment verification
- ✅ Metadata bridges Stripe and database
- ✅ Annual subscriptions via Stripe Subscriptions API

---

## 📊 SUCCESS METRICS

### **Technical Metrics:**
- ✅ Database schema complete (4 tables modified/created)
- ✅ Foreign keys verified (100% correct)
- ✅ RLS policies enabled (100% coverage)
- ✅ Computed column for `is_free` (auto-updates)

### **Business Metrics (Goals):**
- 🎯 10 paying customers by December 2025
- 🎯 $1,000 MRR by December 2025
- 🎯 1,000+ template-based single-fills per month
- 🎯 500+ single-fill mapping sessions per month
- 🎯 5% conversion to bulk processing
- 🎯 50% conversion from free to paid bulk
- 🎯 10% conversion to template subscriptions

---

## 🎯 THE VISION SUMMARY

**What BulkForm Is:**
A three-sided platform with recurring revenue:

1. **Free Hook #1:** Template-based single-fills (instant gratification)
2. **Free Hook #2:** Single-fill mapping (power user tool + paid template bypass)
3. **Revenue Stream #1:** Bulk processing subscriptions (primary revenue - monthly recurring)
4. **Revenue Stream #2:** Template subscriptions (secondary revenue - annual recurring)

**The Genius:**
- Single-fill mapping lets users bypass paid templates (turns objections into engagement)
- Template subscriptions are annual (recurring revenue every year)
- Free tier gives 20 bulk forms (enough to prove value)
- Bulk processing = primary money maker (clear ROI for customers)

**The Moat:**
- Speed (10-20x improvement via Celery)
- Two free entry points (template-based + mapping)
- Bypass mechanism (mapping mode) builds loyalty
- Network effects (more templates = more users)

---

**Status:** ✅ Step 1 Complete - Database Schema Ready  
**Status:** ✅ Single-Fill Mapping Flow Built  
**Status:** ✅ Bulk Processing Flow Built  
**In Progress:** Step 2 - Stripe Product Setup  
**Next:** Step 3 - Template-Based Single-Fill Flow  
**Blockers:** None  
**Last Updated:** November 22, 2025, 1:15 AM WAT

---

*END OF CONTEXT DOCUMENT*  
*This document should be provided to any AI assistant to continue BulkForm Stripe integration from this point forward.*