-- Recovery only reconciles saved evidence or parks stale work. Never send/requeue.
CREATE FUNCTION public.recover_retell_app_ack(p_job uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j public.retell_form_sms_jobs; receipt jsonb;
BEGIN
 SELECT * INTO j FROM public.retell_form_sms_jobs WHERE id=p_job;
 IF NOT FOUND OR j.delivery_transport<>'app_twilio' THEN
  RETURN jsonb_build_object('recovered',false,'reason','unrelated_job','dispatch_authorized',false); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||j.phone_number,0));
 SELECT * INTO j FROM public.retell_form_sms_jobs WHERE id=p_job FOR UPDATE;
 IF j.status<>'processing' OR coalesce(j.claimed_at,j.created_at)>now()-interval '5 minutes' THEN
  RETURN jsonb_build_object('recovered',false,'reason','not_stale_processing','dispatch_authorized',false); END IF;
 receipt:=public.sync_retell_app_outcome(j.id);
 SELECT * INTO j FROM public.retell_form_sms_jobs WHERE id=p_job;
 IF receipt->>'synced'='true' AND j.status<>'processing' THEN
  RETURN jsonb_build_object('recovered',true,'status',j.status,'dispatch_authorized',false); END IF;
 IF receipt->>'synced'='true' THEN
  PERFORM public.review_retell_app_dispatch(j.id,'Stale acknowledgment outcome unconfirmed; reconcile carrier evidence; never resend automatically');
 ELSE
  UPDATE public.retell_form_sms_jobs SET status='review',reason='Stale acknowledgment ledger missing; never resend automatically' WHERE id=j.id;
 END IF;
 RETURN jsonb_build_object('recovered',true,'status','review','dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.recover_retell_app_ack(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.recover_retell_app_ack(uuid) TO service_role;

CREATE FUNCTION public.recover_retell_api_turn(p_turn uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions; e public.sms_events; receipt jsonb;
BEGIN
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RETURN jsonb_build_object('recovered',false,'reason','missing_turn','dispatch_authorized',false); END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||s.phone_number,0));
 -- Use the same lock order as callback synchronization: phone, job, session, turn, receipt.
 PERFORM 1 FROM public.retell_form_sms_jobs WHERE id=s.id FOR UPDATE;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF t.status='queued' AND t.expires_at<=now() THEN
  UPDATE public.retell_api_turns SET status='stopped',reason='Reply expired before generation; human follow-up retained' WHERE id=t.id;
  RETURN jsonb_build_object('recovered',true,'status','stopped','dispatch_authorized',false);
 ELSIF (t.status IN ('creating_session','generating') AND coalesce(t.claimed_at,t.created_at)<=now()-interval '5 minutes')
   OR (t.status='generated' AND t.expires_at<=now()) THEN
  PERFORM public.hold_retell_api_turn(t.id,t.status,'Interrupted or expired generation; verify provider history; never regenerate automatically');
  RETURN jsonb_build_object('recovered',true,'status','review','dispatch_authorized',false);
 ELSIF t.status='submitting' THEN
  SELECT * INTO e FROM public.sms_events WHERE id=t.outbound_id FOR UPDATE;
  IF coalesce(e.created_at,t.claimed_at,t.created_at)>now()-interval '5 minutes' THEN
   RETURN jsonb_build_object('recovered',false,'reason','dispatch_still_fresh','dispatch_authorized',false); END IF;
  receipt:=public.sync_retell_app_outcome(t.outbound_id);
  SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
  IF receipt->>'synced'='true' AND t.status<>'submitting' THEN
   RETURN jsonb_build_object('recovered',true,'status',t.status,'dispatch_authorized',false); END IF;
  IF receipt->>'synced'='true' THEN
   PERFORM public.review_retell_app_dispatch(t.outbound_id,'Stale reply dispatch outcome unconfirmed; reconcile carrier evidence; never resend automatically');
  ELSE
   PERFORM public.hold_retell_api_turn(t.id,'submitting','Stale reply ledger missing; never resend automatically');
  END IF;
  RETURN jsonb_build_object('recovered',true,'status','review','dispatch_authorized',false);
 END IF;
 RETURN jsonb_build_object('recovered',false,'reason','not_stale_actionable','dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.recover_retell_api_turn(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.recover_retell_api_turn(uuid) TO service_role;

CREATE FUNCTION public.retell_app_monitor_findings()
RETURNS TABLE(category text,reference uuid,lead_id uuid,created_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT 'retell_api_turn',t.id,s.lead_id,t.created_at
 FROM public.retell_api_turns t JOIN public.retell_api_sessions s ON s.id=t.session_id
 LEFT JOIN public.sms_events e ON e.id=t.outbound_id
 WHERE t.status='review'
 OR (t.status IN ('queued','generated') AND t.expires_at<=now())
 OR (t.status IN ('creating_session','generating') AND coalesce(t.claimed_at,t.created_at)<=now()-interval '5 minutes')
 OR (t.status='submitting' AND coalesce(e.created_at,t.claimed_at,t.created_at)<=now()-interval '5 minutes')
 UNION ALL SELECT 'retell_api_session',s.id,s.lead_id,s.created_at FROM public.retell_api_sessions s
 WHERE s.status='review' OR (s.status='creating' AND coalesce(s.claimed_at,s.created_at)<=now()-interval '5 minutes');
$$;
REVOKE ALL ON FUNCTION public.retell_app_monitor_findings() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.retell_app_monitor_findings() TO service_role;

-- Include Retell attempts and queue exceptions; monitoring never dispatches messages.
CREATE OR REPLACE FUNCTION public.launch_monitor_findings()
RETURNS TABLE(category text,reference uuid,lead_id uuid,created_at timestamptz)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT 'intake',s.id,s.lead_id,s.created_at FROM public.lead_form_submissions s
 WHERE s.processing_status<>'processed' AND s.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'webhook',j.id,NULL::uuid,j.created_at FROM public.webhook_jobs j
 WHERE j.status IN ('pending','processing','failed') AND j.created_at<now()-interval '5 minutes'
 UNION ALL SELECT 'sms',s.id,s.lead_id,s.created_at FROM public.sms_events s
 WHERE s.direction='outbound' AND s.provider IN ('twilio','retell') AND NOT (coalesce(s.raw_payload,'{}') ? 'MessageSid')
 AND ((s.status IN ('submitting','unknown','failed','undelivered') AND s.created_at<now()-interval '15 minutes')
 OR (s.status IN ('accepted','sent','queued') AND s.created_at<now()-interval '24 hours'))
 UNION ALL SELECT 'form_sms',j.id,j.lead_id,j.created_at FROM public.retell_form_sms_jobs j
 WHERE j.status='review'
 OR (j.status='processing' AND coalesce(j.claimed_at,j.created_at)<now()-CASE WHEN j.delivery_transport='app_twilio' THEN interval '5 minutes' ELSE interval '15 minutes' END)
 OR (j.status='scheduled' AND j.due_at<now()-interval '15 minutes')
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
 WHERE a.status IN ('scheduled','confirmed') AND a.scheduled_at<now()-interval '1 day'
 UNION ALL SELECT * FROM public.retell_app_monitor_findings();
$$;
