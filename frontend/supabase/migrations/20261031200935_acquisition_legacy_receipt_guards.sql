-- Preserve legacy intake behavior while denying scoped receipt reuse.
BEGIN;
CREATE FUNCTION private.require_legacy_form_receipt(p_receipt uuid,p_form uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $guard$
DECLARE saved public.lead_form_submissions%ROWTYPE; form_id uuid; scope uuid; lead uuid;
BEGIN
 IF p_receipt IS NULL THEN RAISE EXCEPTION 'Validated inquiry reference required' USING ERRCODE='22023'; END IF;
 -- The future portal transaction must use this same receipt identity lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('form-submission:'||p_receipt::text,0));
 SELECT * INTO saved FROM public.lead_form_submissions WHERE id=p_receipt FOR UPDATE;
 IF FOUND AND to_jsonb(saved)->>'workspace_id' IS NOT NULL THEN
  RAISE EXCEPTION 'Use acquisition submission workflow' USING ERRCODE='42501'; END IF;
 FOR form_id IN SELECT DISTINCT id FROM unnest(ARRAY[p_form,saved.form_id]) id WHERE id IS NOT NULL ORDER BY id LOOP
  SELECT workspace_id INTO scope FROM public.lead_form_configs WHERE id=form_id FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Form parent unavailable' USING ERRCODE='23503'; END IF;
  IF scope IS NOT NULL THEN RAISE EXCEPTION 'Use acquisition submission workflow' USING ERRCODE='42501'; END IF;
 END LOOP;
 -- A legacy receipt can predate enrollment of its lead into a workspace.
 -- Use the same lock as bind_acquisition_lead before checking that boundary.
 FOR lead IN SELECT id FROM public.leads WHERE id=saved.lead_id OR form_submission_id=p_receipt ORDER BY id LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-lead:'||lead::text,0));
  IF EXISTS(SELECT 1 FROM public.workspace_leads WHERE lead_id=lead) THEN
   RAISE EXCEPTION 'Use acquisition submission workflow' USING ERRCODE='42501'; END IF;
 END LOOP;
END $guard$;
REVOKE ALL ON FUNCTION private.require_legacy_form_receipt(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.require_legacy_form_receipt(uuid,uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.finalize_form_submission(p_submission_id uuid, p_lead jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $function$
DECLARE
  receipt public.lead_form_submissions%ROWTYPE;
  candidate public.leads%ROWTYPE;
  saved_id uuid;
  owner_id uuid;
  created boolean := false;
  alert_id uuid;
  intake_source text;
  recovery_only boolean := coalesce((p_lead->>'_intake_recovery_only')::boolean,false);
BEGIN
  PERFORM private.require_legacy_form_receipt(p_submission_id,NULL);
  SELECT * INTO STRICT receipt FROM public.lead_form_submissions
    WHERE id = p_submission_id FOR UPDATE;
  SELECT value::uuid INTO owner_id FROM public.app_settings WHERE key = 'lead_owner_user_id';
  IF owner_id IS NULL OR NOT EXISTS (
    SELECT 1 FROM public.profiles WHERE id=owner_id AND status='approved'
  ) THEN RAISE EXCEPTION 'An approved intake owner is required'; END IF;

  saved_id := receipt.lead_id;
  IF saved_id IS NULL THEN
    SELECT id INTO saved_id FROM public.leads WHERE form_submission_id=p_submission_id
      ORDER BY created_at LIMIT 1;
  END IF;
  IF saved_id IS NULL THEN
    candidate := jsonb_populate_record(NULL::public.leads, p_lead);
    INSERT INTO public.leads (
      property_address,city,state,zip_code,owner_first_name,owner_last_name,owner_phone_1,owner_email,
      source,inbound_channel,status,precision_tier,ai_qualification_summary,
      score_motivation,score_timeline,score_equity,score_condition,score_flexibility,
      priority_tier,motivation_tag,asking_price,form_submission_id,ad_campaign_id,assigned_to,internal_notes,ai_calling_paused
    ) VALUES (
      candidate.property_address,candidate.city,candidate.state,candidate.zip_code,
      candidate.owner_first_name,candidate.owner_last_name,candidate.owner_phone_1,candidate.owner_email,
      candidate.source,candidate.inbound_channel,candidate.status,candidate.precision_tier,
      candidate.ai_qualification_summary,candidate.score_motivation,candidate.score_timeline,
      candidate.score_equity,candidate.score_condition,candidate.score_flexibility,
      candidate.priority_tier,candidate.motivation_tag,candidate.asking_price,p_submission_id,
      candidate.ad_campaign_id,owner_id,candidate.internal_notes,coalesce(candidate.ai_calling_paused,true)
    ) RETURNING id INTO saved_id;
    created := true;
  END IF;
  -- Same task id on every recovery; completed tasks and operator changes survive.
  INSERT INTO public.tasks(id,title,description,priority,status,type,lead_id,assigned_to,due_date)
    VALUES (p_submission_id,'Follow up on new website inquiry',
      'Review the saved inquiry and consent before contacting the inquirer.',
      'high','pending','follow_up',saved_id,owner_id,now())
    ON CONFLICT(id) DO NOTHING;
  -- Commit the operator alert with the receipt, lead and assigned task.
  alert_id := extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,
    'wholesaleos:intake-alert:'||saved_id::text);
  SELECT coalesce(slug,'web_form') INTO intake_source FROM public.lead_form_configs WHERE id=receipt.form_id;
  INSERT INTO public.app_notifications(id,recipient_id,recipient_role,type,title,body,action_url,lead_id,metadata)
  VALUES(alert_id,owner_id,'admin','pipeline_step','New inquiry — follow-up required',
    coalesce(p_lead->>'property_address','Saved website inquiry')||' — source: '||coalesce(intake_source,'web_form')||
    '. Saved inquiry requires owner follow-up. Provider delivery has not been confirmed.',
    '/leads',saved_id,jsonb_build_object('source',coalesce(intake_source,'web_form'),
      'delivery_state',CASE WHEN recovery_only THEN 'review' ELSE 'pending' END,
      'owner_email','not_attempted','seller_sms','not_attempted',
      'owner_sms','not_supported_for_registered_campaign','submission_id',p_submission_id))
  ON CONFLICT(id) DO NOTHING;
  IF recovery_only THEN
    UPDATE public.app_notifications SET metadata=metadata||jsonb_build_object('delivery_state','review','recovery_only',true)
    WHERE id=alert_id AND metadata->>'delivery_state'='pending';
  END IF;
  UPDATE public.lead_form_submissions SET lead_id=saved_id,processing_status='processed'
    WHERE id=p_submission_id;
  RETURN jsonb_build_object('lead_id',saved_id,'created',created,'notification_id',alert_id);
END;
$function$;

CREATE OR REPLACE FUNCTION public.reserve_form_submission(p_request_id uuid, p_submission jsonb, p_manifest jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $function$
DECLARE receipt public.lead_form_submissions%ROWTYPE; inserted integer;
BEGIN
 PERFORM private.require_legacy_form_receipt(p_request_id,(p_submission->>'form_id')::uuid);
 IF p_request_id IS NULL OR jsonb_typeof(p_manifest) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_submission->'raw_answers') IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Validated inquiry reference and manifest are required';
 END IF;
 INSERT INTO public.lead_form_submissions(
   id,form_id,ip_address,user_agent,utm_source,utm_medium,utm_campaign,raw_answers,
   computed_motivation_tag,computed_timeline,computed_condition,processing_status,request_manifest
 ) VALUES(
   p_request_id,(p_submission->>'form_id')::uuid,p_submission->>'ip_address',
   p_submission->>'user_agent',p_submission->>'utm_source',p_submission->>'utm_medium',
   p_submission->>'utm_campaign',p_submission->'raw_answers',
   p_submission->>'computed_motivation_tag',p_submission->>'computed_timeline',
   p_submission->>'computed_condition','pending',p_manifest
 ) ON CONFLICT(id) DO NOTHING;
 GET DIAGNOSTICS inserted=ROW_COUNT;
 SELECT * INTO STRICT receipt FROM public.lead_form_submissions WHERE id=p_request_id;
 IF receipt.form_id IS DISTINCT FROM (p_submission->>'form_id')::uuid
    OR receipt.request_manifest IS DISTINCT FROM p_manifest THEN
   RETURN jsonb_build_object('status','conflict');
 END IF;
 RETURN jsonb_build_object('status',CASE WHEN inserted=1 THEN 'created' ELSE 'replayed' END,
    'submission_id',receipt.id,'processing_status',receipt.processing_status);
END;
$function$;

REVOKE ALL ON FUNCTION public.reserve_form_submission(uuid,jsonb,jsonb),public.finalize_form_submission(uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_form_submission(uuid,jsonb,jsonb),public.finalize_form_submission(uuid,jsonb) TO service_role;
COMMIT;
