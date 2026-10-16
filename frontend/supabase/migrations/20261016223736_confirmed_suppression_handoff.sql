-- Explicit, successfully checked suppression completes intake without SMS.
-- Unknown lookups and old ambiguous holds remain review; no historical rewrites.
CREATE OR REPLACE FUNCTION public.finish_intake_notification(p_lead_id uuid,p_claim_id uuid,p_outcomes jsonb,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE alert_id uuid; saved public.app_notifications%ROWTYPE; delivery_state text;
BEGIN
 IF jsonb_typeof(p_outcomes) IS DISTINCT FROM 'object' OR p_outcomes->>'owner_email' IS NULL
   OR p_outcomes->>'seller_sms' IS NULL THEN RAISE EXCEPTION 'Delivery outcomes required'; END IF;
 alert_id:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,'wholesaleos:intake-alert:'||p_lead_id::text);
 SELECT * INTO STRICT saved FROM public.app_notifications WHERE id=alert_id FOR UPDATE;
 IF saved.lead_id IS DISTINCT FROM p_lead_id OR saved.metadata->>'delivery_state' IS DISTINCT FROM 'processing'
   OR saved.metadata->>'delivery_claim' IS DISTINCT FROM p_claim_id::text THEN
  RETURN jsonb_build_object('finished',false,'notification_id',alert_id); END IF;
 delivery_state:=CASE WHEN p_outcomes->>'owner_email'='accepted'
  AND (p_outcomes->>'seller_sms' IN ('accepted','no_consent_or_phone','suppressed_or_duplicate',
      'no_consent_or_form_confirmation_disabled','confirmed_suppression')
    OR (p_outcomes->>'seller_sms' IN ('scheduled_retell_60_seconds','scheduled_retell_next_contact_window') AND EXISTS(
      SELECT 1 FROM public.retell_form_sms_jobs j WHERE j.lead_id=p_lead_id)))
  THEN 'completed' ELSE 'review' END;
 UPDATE public.app_notifications SET metadata=metadata||
  (p_outcomes-'delivery_claim'-'delivery_state'-'claimed_at'-'completed_at')||
  jsonb_build_object('delivery_state',delivery_state,'completed_at',clock_timestamp()),body=p_body WHERE id=alert_id;
 RETURN jsonb_build_object('finished',true,'notification_id',alert_id,'delivery_state',delivery_state);
END $$;
REVOKE ALL ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) TO service_role;

