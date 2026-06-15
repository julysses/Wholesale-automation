-- ── Migration 012: Enrichment fan-out rate guard ─────────────────────────────
--
-- DEPENDS ON migration 011 (RealtyAPI integration), which creates the
-- trigger_enrich_lead() function and the enrich_lead_on_insert trigger.
-- Run this AFTER 011.
--
-- Problem: 011's trigger fires an enrich-property edge-function call (which in turn
-- pulls comps + runs Claude ARV) on EVERY lead INSERT. A bulk CSV import of
-- thousands of leads would fan out into thousands of RealtyAPI + Claude calls at
-- once — expensive and rate-limit-prone.
--
-- Guard: this redefines trigger_enrich_lead() to consult a database setting
-- `app.enrich_on_insert`. When set to 'false', per-insert enrichment is skipped.
-- The trigger object from 011 is unchanged — it automatically uses this new body.
--
-- Recommended bulk-import workflow:
--   ALTER DATABASE postgres SET app.enrich_on_insert = 'false';  -- before import
--   -- ... run the bulk import ...
--   ALTER DATABASE postgres SET app.enrich_on_insert = 'true';   -- after import
--   -- then backfill enrichment for the leads you care about, e.g. priority ones:
--   --   SELECT net.http_post(
--   --     url := current_setting('app.supabase_url') || '/functions/v1/enrich-property',
--   --     headers := jsonb_build_object('Content-Type','application/json',
--   --                'Authorization','Bearer ' || current_setting('app.supabase_anon_key')),
--   --     body := jsonb_build_object('lead_id', id, 'address', property_address)::text)
--   --   FROM leads WHERE priority = TRUE AND id NOT IN (SELECT lead_id FROM property_enrichment);
--
-- Default (setting absent) preserves 011's behavior: enrichment runs on insert.

CREATE OR REPLACE FUNCTION trigger_enrich_lead()
RETURNS TRIGGER AS $$
DECLARE
  v_url     TEXT;
  v_anon    TEXT;
  v_enabled TEXT;
BEGIN
  -- Operator kill-switch for bulk imports. Absent/true → enrich; 'false' → skip.
  BEGIN
    v_enabled := current_setting('app.enrich_on_insert');
  EXCEPTION WHEN OTHERS THEN
    v_enabled := 'true';
  END;
  IF lower(coalesce(v_enabled, 'true')) = 'false' THEN
    RETURN NEW;
  END IF;

  BEGIN
    v_url  := current_setting('app.supabase_url');
    v_anon := current_setting('app.supabase_anon_key');
  EXCEPTION WHEN OTHERS THEN
    -- If settings not configured, skip silently — manual enrichment still works
    RETURN NEW;
  END;

  PERFORM net.http_post(
    url     := v_url || '/functions/v1/enrich-property',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer ' || v_anon
    ),
    body    := jsonb_build_object(
      'lead_id', NEW.id,
      'address', NEW.property_address
    )::text
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
