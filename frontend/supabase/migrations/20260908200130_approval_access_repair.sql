-- Repair recursive profile policies and enforce the existing shared-workspace
-- approval model. No business data is deleted or reassigned.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon;
GRANT USAGE ON SCHEMA private TO authenticated;

-- The policy must inspect profiles without recursively re-entering its own RLS.
-- This narrow helper has no arguments, returns only the caller's admin status,
-- and lives outside the exposed API schema.
CREATE OR REPLACE FUNCTION private.is_approved_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT auth.uid() IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role = 'admin' AND status = 'approved'
  );
$$;
REVOKE ALL ON FUNCTION private.is_approved_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.is_approved_admin() TO authenticated;

DROP POLICY IF EXISTS profiles_admin_read ON public.profiles;
DROP POLICY IF EXISTS profiles_admin_write ON public.profiles;
CREATE POLICY profiles_admin_read ON public.profiles FOR SELECT TO authenticated
  USING ((SELECT private.is_approved_admin()));
CREATE POLICY profiles_admin_write ON public.profiles FOR UPDATE TO authenticated
  USING ((SELECT private.is_approved_admin()))
  WITH CHECK ((SELECT private.is_approved_admin()));

ALTER FUNCTION public.is_approved() SET search_path = public, pg_temp;

-- Restrictive policies combine with (rather than OR around) all permissive
-- policies. Approved staff retain the shared team's existing permissions.
DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'leads','deals','buyers','tasks','comps','outreach_activity','campaigns',
    'campaign_members','ai_agent_log','call_events','sms_events','dnc_registry',
    'raw_vendor_payloads','vendor_sync_logs','land_leads','land_vetting',
    'land_comps','land_import_log','buyer_transactions','buyer_preferences',
    'buyer_outreach_log','buyer_import_log','deal_matches','ad_campaigns',
    'ad_creatives','lead_form_configs','lead_form_submissions','fb_campaigns',
    'fb_ad_sets','fb_custom_audiences','fb_leads','fb_campaign_performance'
  ] LOOP
    EXECUTE format('DROP POLICY IF EXISTS require_approved_operator ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY require_approved_operator ON public.%I AS RESTRICTIVE FOR ALL TO authenticated USING ((SELECT public.is_approved())) WITH CHECK ((SELECT public.is_approved()))',
      table_name
    );
  END LOOP;
END $$;

-- Reports must observe the same RLS as their underlying tables.
ALTER VIEW public.my_profile SET (security_invoker = true);
ALTER VIEW public.funnel_metrics SET (security_invoker = true);
ALTER VIEW public.stack_analytics SET (security_invoker = true);
ALTER VIEW public.precision_targeting_summary SET (security_invoker = true);
ALTER VIEW public.land_funnel SET (security_invoker = true);
ALTER VIEW public.infill_pipeline SET (security_invoker = true);
ALTER VIEW public.buyer_leaderboard SET (security_invoker = true);
ALTER VIEW public.ibie_segment_summary SET (security_invoker = true);

CREATE OR REPLACE FUNCTION public.admin_set_user_role(target_user_id uuid, new_role text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF NOT private.is_approved_admin() THEN
    RAISE EXCEPTION 'Unauthorized: approved admin role required';
  END IF;
  UPDATE public.profiles SET role = new_role WHERE id = target_user_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_set_user_status(target_user_id uuid, new_status text, reason text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF NOT private.is_approved_admin() THEN
    RAISE EXCEPTION 'Unauthorized: approved admin role required';
  END IF;
  UPDATE public.profiles SET
    status = new_status,
    approved_at = CASE WHEN new_status = 'approved' THEN NOW() ELSE approved_at END,
    approved_by = CASE WHEN new_status = 'approved' THEN auth.uid() ELSE approved_by END,
    denied_at = CASE WHEN new_status = 'denied' THEN NOW() ELSE denied_at END,
    denied_by = CASE WHEN new_status = 'denied' THEN auth.uid() ELSE denied_by END,
    denied_reason = COALESCE(reason, denied_reason)
  WHERE id = target_user_id;
  INSERT INTO public.app_notifications (recipient_id, type, title, body, action_url)
  VALUES (
    target_user_id,
    CASE new_status WHEN 'approved' THEN 'access_approved' ELSE 'access_denied' END,
    CASE new_status WHEN 'approved' THEN 'Access Approved' ELSE 'Access Denied' END,
    CASE new_status WHEN 'approved' THEN 'Your account has been approved. You can now access WholesaleOS.'
      ELSE COALESCE('Your access request was denied. ' || reason, 'Your access request was not approved.') END,
    '/login'
  );
END;
$$;
REVOKE EXECUTE ON FUNCTION public.admin_set_user_role(uuid,text) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.admin_set_user_status(uuid,text,text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.admin_set_user_role(uuid,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_set_user_status(uuid,text,text) TO authenticated;

-- Trigger functions are not public RPCs. Triggers continue to call them.
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.notify_hot_lead() FROM PUBLIC, anon, authenticated;

NOTIFY pgrst, 'reload schema';
