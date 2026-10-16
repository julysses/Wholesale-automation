-- Completion here acknowledges the intake handoff, never SMS or email delivery.
-- Retell queue exceptions and carrier outcomes remain independently monitored.
-- Do not classify consent_or_suppression_hold as completed: it may hide a failed
-- suppression lookup. Unknown schedules and missing persisted jobs remain review.
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
      'no_consent_or_form_confirmation_disabled')
    OR (p_outcomes->>'seller_sms'='scheduled_retell_60_seconds' AND EXISTS(
      SELECT 1 FROM public.retell_form_sms_jobs j WHERE j.lead_id=p_lead_id)))
  THEN 'completed' ELSE 'review' END;
 UPDATE public.app_notifications SET metadata=metadata||
  (p_outcomes-'delivery_claim'-'delivery_state'-'claimed_at'-'completed_at')||
  jsonb_build_object('delivery_state',delivery_state,'completed_at',clock_timestamp()),body=p_body WHERE id=alert_id;
 RETURN jsonb_build_object('finished',true,'notification_id',alert_id,'delivery_state',delivery_state);
END $$;
REVOKE ALL ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) TO service_role;

-- Reconcile only the two newly recognized outcomes. Preserve original claims,
-- timestamps, channel receipts and suppression history. Never replay providers.
UPDATE public.app_notifications n
SET metadata=n.metadata||jsonb_build_object('delivery_state','completed',
  'handoff_reconciled_at',clock_timestamp(),
  'handoff_reconciliation','recognized_retell_intake_outcome')
WHERE n.type='pipeline_step' AND n.metadata->>'delivery_state'='review'
  AND n.metadata->>'owner_email'='accepted'
  AND (n.metadata->>'seller_sms'='no_consent_or_form_confirmation_disabled'
    OR (n.metadata->>'seller_sms'='scheduled_retell_60_seconds' AND EXISTS(
      SELECT 1 FROM public.retell_form_sms_jobs j WHERE j.lead_id=n.lead_id)));
