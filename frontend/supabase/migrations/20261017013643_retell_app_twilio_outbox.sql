-- App-owned conversational replies require a generated, carrier-bound turn.
-- This does not weaken initial outreach limits or send/provider/scheduler gates.
CREATE FUNCTION public.claim_retell_app_reply(p_turn uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions; message uuid; v_body text; earliest uuid;
BEGIN
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RETURN jsonb_build_object('claimed',false,'reason','missing_turn'); END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||s.phone_number,0));
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF t.status<>'generated' OR t.outbound_id IS NOT NULL OR s.status<>'ready' THEN
  RETURN jsonb_build_object('claimed',false,'reason','already_claimed_or_held'); END IF;
 SELECT id INTO earliest FROM public.retell_api_turns WHERE session_id=s.id AND status NOT IN ('accepted','stopped') ORDER BY created_at,id LIMIT 1;
 IF earliest IS DISTINCT FROM t.id THEN RETURN jsonb_build_object('claimed',false,'reason','previous_turn_unfinished'); END IF;
 IF t.expires_at<=now() OR coalesce((public.intake_phone_status(s.phone_number,s.lead_id,''))->>'suppressed','true')<>'false'
  OR NOT EXISTS(SELECT 1 FROM public.leads WHERE id=s.lead_id AND dnc IS FALSE AND status NOT IN ('dnc','dead','closed','sold','under_contract'))
  OR NOT EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE id=s.id AND delivery_transport='app_twilio' AND status='accepted')
  OR NOT EXISTS(SELECT 1 FROM public.sms_events WHERE id=t.id AND provider='twilio' AND direction='inbound'
   AND lead_id=s.lead_id AND phone_number=s.phone_number AND body=t.recipient_text AND opt_out IS FALSE
   AND raw_payload->>'MessageSid'=t.inbound_sid AND raw_payload->>'From'=s.phone_number AND raw_payload->>'To'=s.sender_number
   AND raw_payload->>'crm_opt_out'='false' AND raw_payload->>'Body'=t.recipient_text
   AND coalesce(raw_payload->>'OptOutType','')='') THEN
  UPDATE public.retell_api_turns SET status='stopped',reason='Expired, suppressed, or inbound binding changed before dispatch' WHERE id=t.id;
  RETURN jsonb_build_object('claimed',false,'reason','expired_suppressed_or_unbound'); END IF;
 -- A real reply permits a conversational response, not a second prospecting
 -- attempt. Uncertain activity in any channel still stops this response.
 IF EXISTS(SELECT 1 FROM public.sms_events WHERE phone_number=s.phone_number AND direction='outbound'
    AND status IN ('submitting','unknown') AND NOT(coalesce(raw_payload,'{}') ? 'MessageSid'))
  OR EXISTS(SELECT 1 FROM public.retell_call_requests WHERE phone_number=s.phone_number AND status<>'completed')
  OR EXISTS(SELECT 1 FROM public.retell_api_turns x JOIN public.sms_events e ON e.id=x.outbound_id
    WHERE x.session_id=s.id AND e.status IN ('failed','undelivered','canceled','unknown'))
  OR EXISTS(SELECT 1 FROM public.sms_events WHERE id=s.id AND status IN ('failed','undelivered','canceled','unknown')) THEN
  UPDATE public.retell_api_turns SET status='review',reason='Earlier provider outcome requires review' WHERE id=t.id;
  UPDATE public.retell_api_sessions SET status='review',reason='Earlier provider outcome requires review' WHERE id=s.id;
  RETURN jsonb_build_object('claimed',false,'reason','unresolved_provider_outcome'); END IF;
 SELECT string_agg(value->>'content',E'\n' ORDER BY ordinal) INTO v_body FROM jsonb_array_elements(t.generated_messages) WITH ORDINALITY a(value,ordinal);
 IF length(trim(coalesce(v_body,''))) NOT BETWEEN 1 AND 1600 THEN RAISE EXCEPTION 'Missing generated reply'; END IF;
 message:=gen_random_uuid();
 INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status,raw_payload)
  VALUES(message,s.lead_id,'twilio','outbound',s.phone_number,v_body,'submitting',
   jsonb_build_object('transport','app_twilio','api_turn_id',t.id,'form_job_id',s.id,'sender_number',s.sender_number,'inbound_sid',t.inbound_sid));
 UPDATE public.retell_api_turns SET status='submitting',outbound_id=message WHERE id=t.id;
 RETURN jsonb_build_object('claimed',true,'message_id',message,'turn_id',t.id,'session_id',s.id,'lead_id',s.lead_id,
   'phone_number',s.phone_number,'sender_number',s.sender_number,'body',v_body,'expires_at',t.expires_at);
END $$;
REVOKE ALL ON FUNCTION public.claim_retell_app_reply(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_app_reply(uuid) TO service_role;

-- Reconcile job/turn state only from the exact already-verified carrier ledger.
-- This function never rewrites a SID, message body, delivery status or raw receipt.
CREATE FUNCTION public.sync_retell_app_outcome(p_message uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE e public.sms_events; j public.retell_form_sms_jobs; t public.retell_api_turns; s public.retell_api_sessions; accepted boolean; issue boolean;
BEGIN
 SELECT * INTO e FROM public.sms_events WHERE id=p_message;
 IF NOT FOUND OR e.provider<>'twilio' OR e.direction<>'outbound' OR e.raw_payload->>'transport' IS DISTINCT FROM 'app_twilio' THEN
  RETURN jsonb_build_object('synced',false,'reason','unrelated_receipt'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||e.phone_number,0));
 -- Lock parent before receipt so callbacks and dispatch completion use one order.
 SELECT * INTO j FROM public.retell_form_sms_jobs WHERE id=(e.raw_payload->>'form_job_id')::uuid FOR UPDATE;
 IF NOT FOUND OR j.delivery_transport<>'app_twilio' OR j.lead_id IS DISTINCT FROM e.lead_id
  OR j.phone_number IS DISTINCT FROM e.phone_number OR j.delivery_sender IS DISTINCT FROM e.raw_payload->>'sender_number' THEN RAISE EXCEPTION 'App delivery identity mismatch'; END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=j.id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE outbound_id=p_message FOR UPDATE;
 SELECT * INTO e FROM public.sms_events WHERE id=p_message FOR UPDATE;
 accepted:=e.status IN ('accepted','scheduled','queued','sending','sent','delivered','read')
  AND coalesce(e.raw_payload->>'provider_sid','') ~ '^SM[0-9a-fA-F]{32}$' AND coalesce(e.raw_payload->>'delivery_conflict','false')<>'true';
 issue:=e.status IN ('failed','undelivered','canceled','unknown','blocked');
 IF p_message=j.id THEN
  IF e.body IS DISTINCT FROM j.delivery_body OR e.raw_payload ? 'api_turn_id' THEN RAISE EXCEPTION 'Acknowledgment receipt mismatch'; END IF;
  IF accepted AND j.status='processing' THEN
   UPDATE public.retell_form_sms_jobs SET status='accepted',reason='Twilio accepted app acknowledgment; see exact carrier receipt' WHERE id=j.id;
  ELSIF issue AND j.status IN ('processing','accepted','review') THEN
   UPDATE public.retell_form_sms_jobs SET status=CASE WHEN e.status='blocked' AND j.status='processing' THEN 'stopped' ELSE 'review' END,
    reason='App acknowledgment outcome: '||e.status||'; do not resend automatically' WHERE id=j.id;
   UPDATE public.retell_api_sessions SET status='review',reason='Acknowledgment delivery needs review' WHERE id=j.id AND status IN ('pending','creating','ready');
  END IF;
 ELSE
  IF t.id IS NULL OR t.session_id<>j.id OR e.raw_payload->>'api_turn_id' IS DISTINCT FROM t.id::text
   OR e.raw_payload->>'inbound_sid' IS DISTINCT FROM t.inbound_sid THEN RAISE EXCEPTION 'Reply receipt mismatch'; END IF;
  IF accepted AND t.status='submitting' THEN
   UPDATE public.retell_api_turns SET status='accepted',reason='Twilio accepted; see exact carrier receipt' WHERE id=t.id;
  ELSIF issue AND t.status IN ('submitting','accepted') THEN
   UPDATE public.retell_api_turns SET status='review',reason='Carrier outcome: '||e.status||'; do not resend automatically' WHERE id=t.id;
   UPDATE public.retell_api_sessions SET status='review',reason='Reply delivery needs review' WHERE id=j.id AND status IN ('creating','ready');
  END IF;
 END IF;
 -- Review holds survive later receipt updates until explicit operator resolution.
 RETURN jsonb_build_object('synced',true,'carrier_status',e.status,'carrier_accepted',coalesce(accepted,false),'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.sync_retell_app_outcome(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sync_retell_app_outcome(uuid) TO service_role;

-- A conflicting API response or failed local persistence still requires review
-- even when a valid callback has already recorded delivery. Preserve that receipt.
CREATE FUNCTION public.review_retell_app_dispatch(p_message uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE result jsonb; e public.sms_events; job_id uuid;
BEGIN
 IF length(trim(coalesce(p_reason,''))) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Review reason required'; END IF;
 result:=public.sync_retell_app_outcome(p_message);
 IF result->>'synced' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'App receipt required'; END IF;
 SELECT * INTO e FROM public.sms_events WHERE id=p_message;
 job_id:=(e.raw_payload->>'form_job_id')::uuid;
 IF p_message=job_id THEN
  UPDATE public.retell_form_sms_jobs SET status='review',reason=p_reason WHERE id=job_id AND status IN ('processing','accepted','review');
 ELSE
  UPDATE public.retell_api_turns SET status='review',reason=p_reason WHERE outbound_id=p_message AND status IN ('submitting','accepted','review');
 END IF;
 UPDATE public.retell_api_sessions SET status='review',reason=p_reason WHERE id=job_id AND status IN ('pending','creating','ready','review');
 RETURN jsonb_build_object('held',true,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.review_retell_app_dispatch(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_retell_app_dispatch(uuid,text) TO service_role;
