-- Service-only transaction: receipt -> lead -> assigned follow-up task.
-- Locking the receipt makes concurrent recovery idempotent without rewriting leads.
CREATE OR REPLACE FUNCTION public.finalize_form_submission(p_submission_id uuid, p_lead jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public, pg_temp
AS $$
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
$$;
REVOKE ALL ON FUNCTION public.finalize_form_submission(uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finalize_form_submission(uuid,jsonb) TO service_role;

-- A pending alert proves that no delivery attempt has yet been claimed.
-- Processing, legacy, reviewed and completed alerts are NEVER automatically reclaimed.
CREATE FUNCTION public.claim_intake_notification(p_lead_id uuid,p_claim_id uuid,p_notification jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE alert_id uuid; saved public.app_notifications%ROWTYPE; owner_id uuid;
BEGIN
 IF p_claim_id IS NULL OR jsonb_typeof(p_notification) IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'A delivery claim and notification are required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=p_lead_id) THEN RAISE EXCEPTION 'Saved lead required'; END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
  WHERE a.key='lead_owner_user_id' AND p.status='approved';
 IF owner_id IS NULL THEN RAISE EXCEPTION 'Approved owner required'; END IF;
 alert_id:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8'::uuid,'wholesaleos:intake-alert:'||p_lead_id::text);
 INSERT INTO public.app_notifications(id,recipient_id,recipient_role,type,title,body,action_url,lead_id,metadata)
 VALUES(alert_id,owner_id,'admin','pipeline_step',p_notification->>'title',p_notification->>'body','/leads',p_lead_id,
   coalesce(p_notification->'metadata','{}'::jsonb)||jsonb_build_object('delivery_state','pending'))
 ON CONFLICT(id) DO NOTHING;
 SELECT * INTO STRICT saved FROM public.app_notifications WHERE id=alert_id FOR UPDATE;
 IF saved.lead_id IS DISTINCT FROM p_lead_id THEN RAISE EXCEPTION 'Notification does not match lead'; END IF;
 IF saved.metadata->>'delivery_state' IS DISTINCT FROM 'pending' THEN
  RETURN jsonb_build_object('claimed',false,'notification_id',alert_id,'delivery_state',coalesce(saved.metadata->>'delivery_state','legacy_review'));
 END IF;
 UPDATE public.app_notifications SET metadata=metadata||jsonb_build_object('delivery_state','processing',
  'delivery_claim',p_claim_id,'claimed_at',clock_timestamp()) WHERE id=alert_id;
 RETURN jsonb_build_object('claimed',true,'notification_id',alert_id,'claim_id',p_claim_id);
END $$;
REVOKE ALL ON FUNCTION public.claim_intake_notification(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_intake_notification(uuid,uuid,jsonb) TO service_role;

CREATE FUNCTION public.finish_intake_notification(p_lead_id uuid,p_claim_id uuid,p_outcomes jsonb,p_body text)
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
  AND p_outcomes->>'seller_sms' IN ('accepted','no_consent_or_phone','suppressed_or_duplicate') THEN 'completed' ELSE 'review' END;
 UPDATE public.app_notifications SET metadata=metadata||
  (p_outcomes-'delivery_claim'-'delivery_state'-'claimed_at'-'completed_at')||
  jsonb_build_object('delivery_state',delivery_state,'completed_at',clock_timestamp()),body=p_body WHERE id=alert_id;
 RETURN jsonb_build_object('finished',true,'notification_id',alert_id,'delivery_state',delivery_state);
END $$;
REVOKE ALL ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.finish_intake_notification(uuid,uuid,jsonb,text) TO service_role;

CREATE OR REPLACE FUNCTION public.launch_monitor_findings()
RETURNS TABLE(category text,reference uuid,lead_id uuid,created_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT 'intake',s.id,s.lead_id,s.created_at FROM public.lead_form_submissions s
 WHERE s.processing_status<>'processed' AND s.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'webhook',j.id,NULL::uuid,j.created_at FROM public.webhook_jobs j
 WHERE j.status IN ('pending','processing','failed') AND j.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'sms',s.id,s.lead_id,s.created_at FROM public.sms_events s
 WHERE s.direction='outbound' AND s.provider='twilio' AND NOT (coalesce(s.raw_payload,'{}') ? 'MessageSid')
 AND ((s.status IN ('submitting','unknown','failed','undelivered') AND s.created_at<now()-interval '15 minutes')
 OR (s.status IN ('accepted','sent','queued') AND s.created_at<now()-interval '24 hours'))
 UNION ALL SELECT 'call',c.id,c.lead_id,c.created_at FROM public.retell_call_requests c
 WHERE c.status<>'completed' AND c.created_at<now()-interval '15 minutes'
 UNION ALL SELECT 'nurture',j.id,j.lead_id,j.created_at FROM public.sms_nurture_jobs j
 WHERE j.status='review' OR (j.status='processing' AND j.claimed_at<now()-interval '15 minutes')
 OR (j.status='queued' AND j.due_at<now()-interval '1 day')
 UNION ALL SELECT 'email',m.id,NULL::uuid,m.created_at FROM public.email_messages m
 WHERE ((m.status IN ('attempting','submitting','unknown','failed') AND m.created_at<now()-interval '15 minutes')
 OR (m.status='accepted' AND m.created_at<now()-interval '24 hours'))
 AND NOT EXISTS(SELECT 1 FROM public.email_delivery_events e WHERE e.message_id=m.id AND e.recipient=m.recipient
 AND e.event IN ('delivered','unsubscribe','group_unsubscribe'))
 OR (m.created_at<now()-interval '15 minutes' AND EXISTS(SELECT 1 FROM public.email_delivery_events e
 WHERE e.message_id=m.id AND e.recipient=m.recipient AND e.event IN ('bounce','dropped','spamreport')))
 UNION ALL SELECT 'intake_alert',n.id,n.lead_id,n.created_at FROM public.app_notifications n
 WHERE n.type='pipeline_step' AND (
  (n.metadata->>'delivery_state'='pending' AND n.created_at<now()-interval '5 minutes')
  OR (n.metadata->>'delivery_state'='processing' AND
    coalesce((n.metadata->>'claimed_at')::timestamptz,n.created_at)<now()-interval '5 minutes')
  OR n.metadata->>'delivery_state'='review'
  OR (NOT (n.metadata ? 'delivery_state') AND n.metadata->>'owner_email'='unresolved'
      AND n.created_at<now()-interval '5 minutes'))
 UNION ALL SELECT 'appointment',a.id,a.lead_id,a.scheduled_at FROM public.appointments a
 WHERE a.status IN ('scheduled','confirmed') AND a.scheduled_at<now()-interval '1 day';
$$;
