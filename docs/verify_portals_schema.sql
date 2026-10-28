-- ============================================================================
-- VERIFY PORTALS & SUBMISSIONS SCHEMA
-- Run this in your Supabase SQL Editor to check if the migration succeeded
-- ============================================================================

SELECT 
    'Table Check' AS check_type,
    tablename AS item_name,
    CASE 
        WHEN rowsecurity = true THEN 'Created with RLS Enabled ✅' 
        ELSE 'Created (RLS Disabled) ⚠️' 
    END AS status_details
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename IN ('form_portals', 'form_submissions')

UNION ALL

SELECT 
    'Policy Check' AS check_type,
    policyname || ' (' || tablename || ')' AS item_name,
    'Active ✅' AS status_details
FROM pg_policies
WHERE schemaname = 'public' 
  AND tablename IN ('form_portals', 'form_submissions')

UNION ALL

SELECT 
    'Trigger Check' AS check_type,
    trigger_name || ' on ' || event_object_table AS item_name,
    'Installed ✅' AS status_details
FROM information_schema.triggers
WHERE trigger_schema = 'public'
  AND event_object_table IN ('form_portals', 'form_submissions');
