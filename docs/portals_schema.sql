-- ============================================================================
-- BULKFORM PUBLIC PORTALS & SUBMISSIONS SCHEMA
-- File: docs/portals_schema.sql
-- Run this migration in your Supabase SQL Editor
-- ============================================================================

-- ============================================================================
-- 1. CREATE TABLES
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.form_portals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES public.pdf_templates(id) ON DELETE CASCADE,
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    allowed_origins TEXT[] DEFAULT ARRAY['*']::TEXT[],
    email_settings JSONB DEFAULT '{"send_applicant_email": false, "notify_owner": false, "owner_email": "", "subject": "Your Completed Form"}'::jsonb,
    sheet_settings JSONB DEFAULT '{"google_sheet_url": null, "webhook_url": null}'::jsonb,
    access_token VARCHAR(64) UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(24), 'hex'),
    total_submissions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.form_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portal_id UUID NOT NULL REFERENCES public.form_portals(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES public.pdf_templates(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    applicant_name VARCHAR(255),
    applicant_email VARCHAR(255),
    submitted_data JSONB NOT NULL,
    pdf_url TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    ip_address VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. CREATE INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_form_portals_slug ON public.form_portals(slug);
CREATE INDEX IF NOT EXISTS idx_form_portals_user_id ON public.form_portals(user_id);
CREATE INDEX IF NOT EXISTS idx_form_portals_access_token ON public.form_portals(access_token);

CREATE INDEX IF NOT EXISTS idx_form_submissions_portal_id ON public.form_submissions(portal_id);
CREATE INDEX IF NOT EXISTS idx_form_submissions_user_id ON public.form_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_form_submissions_created_at ON public.form_submissions(created_at DESC);

-- ============================================================================
-- 3. ENABLE ROW LEVEL SECURITY & POLICIES
-- ============================================================================

ALTER TABLE public.form_portals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.form_submissions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can manage their own portals" ON public.form_portals;
CREATE POLICY "Users can manage their own portals"
    ON public.form_portals
    FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Public can view active portals" ON public.form_portals;
CREATE POLICY "Public can view active portals"
    ON public.form_portals
    FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS "Portal owners can view their submissions" ON public.form_submissions;
CREATE POLICY "Portal owners can view their submissions"
    ON public.form_submissions
    FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 4. AUTO-INCREMENT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION public.increment_portal_submissions()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE public.form_portals
    SET total_submissions = total_submissions + 1,
        updated_at = NOW()
    WHERE id = NEW.portal_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_increment_portal_submissions ON public.form_submissions;
CREATE TRIGGER trigger_increment_portal_submissions
    AFTER INSERT ON public.form_submissions
    FOR EACH ROW
    EXECUTE FUNCTION public.increment_portal_submissions();
