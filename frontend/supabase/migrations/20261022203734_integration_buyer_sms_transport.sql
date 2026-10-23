-- Dedicated buyer SMS. No real route is created or activated by this proposal.
CREATE TABLE private.buyer_sms_routes (
 service_sid text PRIMARY KEY CHECK(service_sid ~ '^MG[0-9a-fA-F]{32}$'),
 account_sid text NOT NULL CHECK(account_sid ~ '^AC[0-9a-fA-F]{32}$'),
 campaign_sid text NOT NULL CHECK(campaign_sid ~ '^CM[0-9a-fA-F]{32}$'),
 from_number text NOT NULL UNIQUE CHECK(from_number ~ '^\+1[0-9]{10}$'),
 brand text NOT NULL CHECK(length(brand) BETWEEN 1 AND 100),
 approved_at timestamptz, enabled boolean NOT NULL DEFAULT false,
 scope text NOT NULL CHECK(scope='buyer_deal_alerts'), proof jsonb NOT NULL
);
ALTER TABLE private.buyer_sms_routes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_sms_routes FROM PUBLIC,anon,authenticated;
GRANT SELECT ON private.buyer_sms_routes TO service_role;
CREATE TABLE private.buyer_sms_messages (
 id uuid PRIMARY KEY REFERENCES private.buyer_outreach_attempts(id),
 request_id uuid NOT NULL, buyer_id uuid NOT NULL, phone text NOT NULL,
 consent_id uuid NOT NULL REFERENCES private.buyer_sms_consent_reviews(id),
 route jsonb NOT NULL, body text NOT NULL, status text NOT NULL DEFAULT 'reserved',
 provider_sid text UNIQUE, conflict boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(request_id,phone)
);
ALTER TABLE private.buyer_sms_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_sms_messages FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON private.buyer_sms_messages TO service_role;
CREATE TABLE private.buyer_sms_events (
 id uuid PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('inbound','status')),
 payload jsonb NOT NULL, message_id uuid, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.buyer_sms_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.buyer_sms_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON private.buyer_sms_events TO service_role;
CREATE TRIGGER buyer_sms_event_immutable BEFORE UPDATE OR DELETE ON private.buyer_sms_events
 FOR EACH ROW EXECUTE FUNCTION private.protect_csv_lead_import();
CREATE INDEX buyer_sms_consent_current ON private.buyer_sms_consent_reviews(buyer_id,phone,recorded_at DESC,id DESC);
CREATE INDEX buyer_sms_phone_history ON private.buyer_sms_messages(phone,created_at DESC);
CREATE FUNCTION private.protect_buyer_sms_message() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['status','provider_sid','conflict']) IS DISTINCT FROM
 (to_jsonb(OLD)-ARRAY['status','provider_sid','conflict']) THEN RAISE EXCEPTION 'Buyer SMS identity is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_buyer_sms_message() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER buyer_sms_message_identity BEFORE UPDATE OR DELETE ON private.buyer_sms_messages
 FOR EACH ROW EXECUTE FUNCTION private.protect_buyer_sms_message();

CREATE FUNCTION public.buyer_sms_route_status(p_route jsonb) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT jsonb_build_object('approved',EXISTS(SELECT 1 FROM private.buyer_sms_routes r
 WHERE r.service_sid=p_route->>'service_sid' AND r.account_sid=p_route->>'account_sid'
 AND r.campaign_sid=p_route->>'campaign_sid' AND r.from_number=p_route->>'from_number'
 AND r.brand=p_route->>'brand' AND r.enabled AND r.approved_at IS NOT NULL AND r.approved_at<=now()
 AND r.scope='buyer_deal_alerts' AND jsonb_typeof(r.proof)='object' AND r.proof<>'{}'::jsonb));
$$;
REVOKE ALL ON FUNCTION public.buyer_sms_route_status(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.buyer_sms_route_status(jsonb) TO service_role;

CREATE FUNCTION public.claim_buyer_sms(p_id uuid,p_request uuid,p_operator uuid,p_buyer uuid,p_payload jsonb,p_hold text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a private.buyer_outreach_attempts; b public.buyers; c jsonb; v_phone text; why text:=''; state text;
BEGIN
 IF p_id IS NULL OR p_request IS NULL OR p_buyer IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Approved operator required' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object' OR length(coalesce(p_payload->>'body','')) NOT BETWEEN 1 AND 1600
 THEN RAISE EXCEPTION 'Invalid SMS payload' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-outreach:'||p_id::text,0));
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
   IF a.operator_id<>p_operator THEN RAISE EXCEPTION 'Foreign outreach reference' USING ERRCODE='42501'; END IF;
   IF a.request_id<>p_request OR a.buyer_id<>p_buyer OR a.channel<>'sms' OR a.payload<>p_payload
   THEN RAISE EXCEPTION 'Outreach reference changed' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('id',a.id,'claimed',false,'status',a.status,'reason',a.reason,'provider_message_id',a.provider_message_id);
 END IF;
 v_phone:=private.buyer_phone(p_payload->>'destination');
 IF v_phone IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||v_phone,0)); END IF;
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 IF NOT FOUND THEN why:='buyer_missing';
 ELSIF b.active IS DISTINCT FROM true THEN why:='buyer_inactive';
 ELSIF b.sms_opt_in IS DISTINCT FROM true THEN why:='sms_not_opted_in'; END IF;
 IF why='' AND (v_phone IS NULL OR v_phone IS DISTINCT FROM private.buyer_phone(b.phone) OR v_phone IS DISTINCT FROM p_payload->>'destination')
 THEN why:='buyer_phone_changed_or_invalid'; END IF;
 -- A configured application flag alone cannot authorize a route. No approved rows are seeded.
 IF why='' AND (coalesce(p_hold,'')<>'' OR (public.buyer_sms_route_status(p_payload->'route'))->>'approved'<>'true')
 THEN why:=coalesce(nullif(p_hold,''),'buyer_sms_route_unavailable'); END IF;
 IF why='' THEN
   c:=public.buyer_sms_consent_status(p_buyer,p_operator);
   IF c->>'consent_ready'<>'true' THEN why:=CASE WHEN c->>'suppressed'='true' THEN 'sms_suppressed' ELSE 'written_buyer_consent_missing' END; END IF;
 END IF;
 IF why='' AND EXISTS(SELECT 1 FROM private.buyer_sms_messages WHERE phone=v_phone AND request_id=p_request)
 THEN why:='duplicate_campaign_destination'; END IF;
 IF why='' AND EXISTS(SELECT 1 FROM private.buyer_sms_messages WHERE phone=v_phone AND status IN ('reserved','submitting','unknown'))
 THEN why:='earlier_submission_unconfirmed'; END IF;
 IF why='' AND EXISTS(SELECT 1 FROM private.buyer_sms_messages WHERE phone=v_phone
 AND created_at>=date_trunc('day',now() AT TIME ZONE 'America/Chicago') AT TIME ZONE 'America/Chicago')
 THEN why:='buyer_sms_daily_limit'; END IF;
 state:=CASE WHEN why='earlier_submission_unconfirmed' THEN 'held' WHEN why<>'' THEN 'skipped' ELSE 'submitting' END;
 INSERT INTO private.buyer_outreach_attempts(id,request_id,operator_id,buyer_id,channel,payload,status,reason)
 VALUES(p_id,p_request,p_operator,p_buyer,'sms',p_payload,state,why);
 INSERT INTO public.buyer_outreach_log(id,buyer_id,request_id,buyer_snapshot,deal_id,channel,direction,status,body,to_address,outcome_reason,provider)
 VALUES(p_id,b.id,p_request,jsonb_build_object('id',p_buyer,'first_name',b.first_name,'last_name',b.last_name),
 (p_payload->>'deal_id')::uuid,'sms','outbound',state,p_payload->>'body',coalesce(v_phone,p_payload->>'destination',''),why,'twilio');
 IF why='' THEN
   INSERT INTO private.buyer_sms_messages(id,request_id,buyer_id,phone,consent_id,route,body)
   VALUES(p_id,p_request,p_buyer,v_phone,(c->>'receipt_id')::uuid,p_payload->'route',p_payload->>'body');
 END IF;
 RETURN jsonb_build_object('id',p_id,'claimed',state='submitting','status',state,'reason',why);
END $$;
REVOKE ALL ON FUNCTION public.claim_buyer_sms(uuid,uuid,uuid,uuid,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_buyer_sms(uuid,uuid,uuid,uuid,jsonb,text) TO service_role;

CREATE FUNCTION public.authorize_buyer_sms_submission(p_id uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE a private.buyer_outreach_attempts; m private.buyer_sms_messages; c jsonb; why text:=''; v_phone text;
BEGIN
 SELECT phone INTO v_phone FROM private.buyer_sms_messages WHERE id=p_id;
 IF v_phone IS NOT NULL THEN PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||v_phone,0)); END IF;
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR a.operator_id<>p_operator OR a.channel<>'sms' OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved')
 THEN RAISE EXCEPTION 'Outreach access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO m FROM private.buyer_sms_messages WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR m.status<>'reserved' OR a.status<>'submitting' THEN
   RETURN jsonb_build_object('id',p_id,'authorized',false,'status',a.status,'reason',a.reason); END IF;
 PERFORM 1 FROM public.buyers WHERE id=m.buyer_id FOR UPDATE;
 c:=public.buyer_sms_consent_status(m.buyer_id,p_operator);
 IF c->>'consent_ready'<>'true' OR c->>'phone' IS DISTINCT FROM m.phone OR c->>'receipt_id' IS DISTINCT FROM m.consent_id::text
 THEN why:='consent_or_suppression_changed'; END IF;
 IF (public.buyer_sms_route_status(m.route))->>'approved'<>'true' THEN why:='buyer_sms_route_unavailable'; END IF;
 IF why<>'' THEN
   UPDATE private.buyer_sms_messages SET status='skipped' WHERE id=p_id;
   UPDATE private.buyer_outreach_attempts SET status='skipped',reason=why WHERE id=p_id;
   UPDATE public.buyer_outreach_log SET status='skipped',outcome_reason=why WHERE id=p_id;
 ELSE UPDATE private.buyer_sms_messages SET status='submitting' WHERE id=p_id; END IF;
 RETURN jsonb_build_object('id',p_id,'authorized',why='','status',CASE WHEN why='' THEN 'submitting' ELSE 'skipped' END,'reason',why);
END $$;
REVOKE ALL ON FUNCTION public.authorize_buyer_sms_submission(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.authorize_buyer_sms_submission(uuid,uuid) TO service_role;

CREATE FUNCTION public.record_buyer_sms_outcome(p_id uuid,p_phone text,p_sid text,p_status text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE m private.buyer_sms_messages; a private.buyer_outreach_attempts; clash boolean; state text; old_rank integer; new_rank integer;
BEGIN
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id AND channel='sms' FOR UPDATE;
 SELECT * INTO m FROM private.buyer_sms_messages WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR a.id IS NULL OR m.phone IS DISTINCT FROM p_phone
 THEN RAISE EXCEPTION 'Buyer SMS receipt does not match' USING ERRCODE='22023'; END IF;
 IF p_status NOT IN ('unknown','accepted','scheduled','queued','sending','sent','delivered','read','failed','undelivered','canceled')
 OR (p_status<>'unknown' AND coalesce(p_sid,'') !~ '^SM[0-9a-fA-F]{32}$')
 THEN RAISE EXCEPTION 'Invalid SMS outcome' USING ERRCODE='22023'; END IF;
 IF m.status IN ('reserved','skipped') THEN RAISE EXCEPTION 'SMS has not been authorized for submission' USING ERRCODE='22023'; END IF;
 clash:=m.conflict OR (m.provider_sid IS NOT NULL AND p_sid IS NOT NULL AND m.provider_sid<>p_sid)
 OR (m.status IN ('delivered','read') AND p_status IN ('failed','undelivered','canceled'))
 OR (m.status IN ('failed','undelivered','canceled') AND p_status IN ('delivered','read'));
 old_rank:=array_position(ARRAY['accepted','scheduled','queued','sending','sent','delivered','read'],m.status);
 new_rank:=array_position(ARRAY['accepted','scheduled','queued','sending','sent','delivered','read'],p_status);
 state:=CASE WHEN clash THEN 'unknown'
 WHEN p_status='unknown' AND m.status NOT IN ('submitting','unknown') THEN m.status
 WHEN m.status IN ('failed','undelivered','canceled') THEN m.status
 WHEN old_rank IS NOT NULL AND new_rank IS NOT NULL AND old_rank>=new_rank THEN m.status ELSE p_status END;
 UPDATE private.buyer_sms_messages SET status=state,provider_sid=coalesce(provider_sid,p_sid),conflict=clash WHERE id=p_id RETURNING * INTO m;
 state:=CASE WHEN m.status IN ('delivered','read') THEN 'delivered' WHEN m.status IN ('failed','undelivered','canceled') THEN 'failed'
 WHEN m.status IN ('unknown','submitting') THEN 'unknown' ELSE 'accepted' END;
 UPDATE private.buyer_outreach_attempts SET status=state,reason=CASE WHEN clash THEN 'conflicting_carrier_receipts' ELSE 'carrier_'||m.status END,
 provider_message_id=m.provider_sid,conflict=clash WHERE id=p_id RETURNING * INTO a;
 UPDATE public.buyer_outreach_log SET status=a.status,outcome_reason=a.reason,provider_msg_id=m.provider_sid WHERE id=p_id;
 RETURN jsonb_build_object('id',a.id,'claimed',false,'status',a.status,'reason',a.reason,'provider_message_id',a.provider_message_id);
END $$;
REVOKE ALL ON FUNCTION public.record_buyer_sms_outcome(uuid,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_buyer_sms_outcome(uuid,text,text,text) TO service_role;

-- Native STOP receipts already preserve DNC across imports. Extend that suppression
-- to buyer flags/tasks, without changing native property-inquiry webhook behavior.
CREATE FUNCTION private.suppress_buyer_sms() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 UPDATE public.buyers SET sms_opt_in=false WHERE private.buyer_phone(phone)=private.buyer_phone(NEW.phone_number);
 UPDATE public.tasks SET status='cancelled' WHERE status='pending' AND type='buyer_sms_review'
 AND (buyer_id IN (SELECT id FROM public.buyers WHERE private.buyer_phone(phone)=private.buyer_phone(NEW.phone_number))
 OR id IN (SELECT id FROM private.buyer_sms_events WHERE kind='inbound' AND payload->>'From'=private.buyer_phone(NEW.phone_number)));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.suppress_buyer_sms() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER buyer_sms_global_dnc AFTER INSERT ON public.dnc_registry FOR EACH ROW EXECUTE FUNCTION private.suppress_buyer_sms();

CREATE FUNCTION public.record_buyer_sms_event(p_event uuid,p_kind text,p_id uuid,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE m private.buyer_sms_messages; a private.buyer_outreach_attempts; v_phone text; sender text; result jsonb; prior private.buyer_sms_events;
 v_stop boolean; v_control text; v_buyer uuid; owner_id uuid; count_buyers integer; log_snapshot jsonb; v_body text; notice uuid;
BEGIN
 IF p_event IS NULL OR p_kind NOT IN ('inbound','status') OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
 OR coalesce(p_payload->>'MessageSid','') !~ '^SM[0-9a-fA-F]{32}$' THEN RAISE EXCEPTION 'Invalid buyer SMS event' USING ERRCODE='22023'; END IF;
 v_phone:=CASE WHEN p_kind='status' THEN p_payload->>'To' ELSE p_payload->>'From' END;
 sender:=CASE WHEN p_kind='status' THEN p_payload->>'From' ELSE p_payload->>'To' END;
 IF coalesce(v_phone,'') !~ '^\+1[0-9]{10}$' THEN RAISE EXCEPTION 'Invalid US phone' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-sms-event:'||p_event::text,0));
 SELECT * INTO prior FROM private.buyer_sms_events WHERE id=p_event;
 IF FOUND AND (prior.kind<>p_kind OR prior.message_id IS DISTINCT FROM p_id OR prior.payload<>p_payload)
 THEN RAISE EXCEPTION 'Carrier event reference changed' USING ERRCODE='22023'; END IF;
 IF p_kind='status' THEN
   SELECT * INTO m FROM private.buyer_sms_messages WHERE id=p_id;
   IF NOT FOUND OR m.route->>'account_sid' IS DISTINCT FROM p_payload->>'AccountSid' OR m.route->>'from_number' IS DISTINCT FROM sender
   OR m.phone IS DISTINCT FROM v_phone OR (p_payload->>'MessagingServiceSid' IS NOT NULL AND m.route->>'service_sid'<>p_payload->>'MessagingServiceSid')
   THEN RAISE EXCEPTION 'Carrier event does not match the saved buyer route' USING ERRCODE='22023'; END IF;
   INSERT INTO private.buyer_sms_events(id,kind,payload,message_id) VALUES(p_event,p_kind,p_payload,p_id) ON CONFLICT(id) DO NOTHING;
   RETURN public.record_buyer_sms_outcome(p_id,v_phone,p_payload->>'MessageSid',p_payload->>'MessageStatus');
 END IF;
 -- Known historical routes still accept replies/STOP when outbound is disabled.
 IF NOT EXISTS(SELECT 1 FROM private.buyer_sms_routes WHERE from_number=sender AND account_sid=p_payload->>'AccountSid'
 AND (p_payload->>'MessagingServiceSid' IS NULL OR service_sid=p_payload->>'MessagingServiceSid'))
 THEN RAISE EXCEPTION 'Unknown buyer sender route' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_sms_events(id,kind,payload,message_id) VALUES(p_event,p_kind,p_payload,NULL) ON CONFLICT(id) DO NOTHING;
 v_body:=coalesce(p_payload->>'Body','');
 v_control:=upper(trim(coalesce(p_payload->>'OptOutType',v_body)));
 v_stop:=v_control IN ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT')
 OR coalesce(p_payload->>'crm_opt_out','false')='true';
 IF v_stop THEN PERFORM public.record_twilio_event(p_event,'inbound',p_payload); END IF;
 SELECT count(DISTINCT buyer_id) INTO count_buyers FROM private.buyer_sms_messages
 WHERE phone=v_phone AND route->>'from_number'=sender AND route->>'account_sid'=p_payload->>'AccountSid' AND provider_sid IS NOT NULL;
 SELECT x.* INTO m FROM private.buyer_sms_messages x WHERE x.phone=v_phone AND x.route->>'from_number'=sender
 AND x.route->>'account_sid'=p_payload->>'AccountSid' AND x.provider_sid IS NOT NULL ORDER BY x.created_at DESC,x.id DESC LIMIT 1;
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=m.id;
 IF count_buyers=1 THEN
   SELECT id INTO v_buyer FROM public.buyers WHERE id=m.buyer_id AND private.buyer_phone(phone)=v_phone;
   SELECT buyer_snapshot INTO log_snapshot FROM public.buyer_outreach_log WHERE id=m.id;
 END IF;
 SELECT id INTO owner_id FROM public.profiles WHERE id=a.operator_id AND status='approved';
 IF owner_id IS NULL THEN SELECT p.id INTO owner_id FROM public.app_settings s JOIN public.profiles p ON p.id::text=s.value
 WHERE s.key='lead_owner_user_id' AND p.status='approved'; END IF;
 INSERT INTO public.buyer_outreach_log(id,buyer_id,request_id,buyer_snapshot,channel,direction,status,body,to_address,provider,provider_msg_id,outcome_reason)
 VALUES(p_event,v_buyer,CASE WHEN count_buyers=1 THEN a.request_id ELSE NULL END,coalesce(log_snapshot,'{}'::jsonb),'sms','inbound',
 CASE WHEN v_stop THEN 'opted_out' ELSE 'received' END,v_body,v_phone,'twilio',p_payload->>'MessageSid',
 CASE WHEN count_buyers>1 THEN 'buyer_identity_requires_review' WHEN count_buyers=0 THEN 'unlinked_buyer_reply' ELSE 'buyer_reply' END)
 ON CONFLICT(id) DO NOTHING;
 IF count_buyers=1 THEN UPDATE public.buyer_outreach_log SET replied_at=coalesce(replied_at,now()),reply_body=v_body WHERE id=m.id; END IF;
 IF NOT v_stop AND v_control NOT IN ('START','UNSTOP','YES','HELP','INFO') AND NOT EXISTS(
 SELECT 1 FROM public.dnc_registry WHERE private.buyer_phone(phone_number)=v_phone) THEN
   INSERT INTO public.tasks(id,buyer_id,title,description,priority,status,type,assigned_to,due_date)
   VALUES(p_event,v_buyer,'Buyer SMS reply: review and follow up','Carrier buyer SMS reply (unverified content): '||left(v_body,3000),
   'high','pending','buyer_sms_review',owner_id,now()) ON CONFLICT(id) DO NOTHING;
   UPDATE public.tasks SET assigned_to=owner_id WHERE id=p_event AND assigned_to IS NULL AND status='pending' AND owner_id IS NOT NULL;
 END IF;
 notice:=md5('buyer-sms-notice:'||p_event::text)::uuid;
 INSERT INTO public.app_notifications(id,recipient_id,recipient_role,type,title,body,action_url,metadata)
 VALUES(notice,owner_id,'admin','pipeline_step',CASE WHEN v_stop THEN 'Buyer SMS opt-out' ELSE 'Buyer SMS reply' END,
 left(v_body,500),'/buyer-intel',jsonb_build_object('provider','twilio','buyer_sms_event',p_event,'buyer_id',v_buyer,'identity_ambiguous',count_buyers>1))
 ON CONFLICT(id) DO NOTHING;
 UPDATE public.app_notifications SET recipient_id=owner_id WHERE id=notice AND recipient_id IS NULL AND owner_id IS NOT NULL;
 RETURN jsonb_build_object('saved',true,'duplicate',prior.id IS NOT NULL,'owner_missing',owner_id IS NULL,'opt_out',v_stop,'provider_calls',0);
END $$;
REVOKE ALL ON FUNCTION public.record_buyer_sms_event(uuid,text,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_buyer_sms_event(uuid,text,uuid,jsonb) TO service_role;

CREATE FUNCTION public.record_buyer_sms_optout_rejection(p_id uuid,p_phone text,p_code integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE m private.buyer_sms_messages; a private.buyer_outreach_attempts;
BEGIN
 IF p_code NOT IN (21610,30630) THEN RAISE EXCEPTION 'Not a provider opt-out rejection' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||p_phone,0));
 SELECT * INTO a FROM private.buyer_outreach_attempts WHERE id=p_id AND channel='sms' FOR UPDATE;
 SELECT * INTO m FROM private.buyer_sms_messages WHERE id=p_id FOR UPDATE;
 IF NOT FOUND OR a.id IS NULL OR m.phone IS DISTINCT FROM p_phone OR m.status IN ('reserved','skipped')
 THEN RAISE EXCEPTION 'Provider rejection cannot be bound' USING ERRCODE='22023'; END IF;
 INSERT INTO public.dnc_registry(id,phone_number,reason,source,raw_payload)
 VALUES(p_id,p_phone,'opt_out','buyer_twilio_provider',jsonb_build_object('app_message_id',p_id,'provider_error_code',p_code)) ON CONFLICT(id) DO NOTHING;
 UPDATE public.leads l SET dnc=true,status='dnc',sms_sequence_active=false,email_sequence_active=false,ai_calling_paused=true
 WHERE p_phone IN (private.buyer_phone(l.owner_phone_1),private.buyer_phone(l.owner_phone_2),private.buyer_phone(l.owner_phone_3));
 IF m.provider_sid IS NOT NULL THEN RETURN public.record_buyer_sms_outcome(p_id,p_phone,m.provider_sid,'failed'); END IF;
 UPDATE private.buyer_sms_messages SET status='failed' WHERE id=p_id;
 UPDATE private.buyer_outreach_attempts SET status='failed',reason='provider_opt_out_rejection' WHERE id=p_id RETURNING * INTO a;
 UPDATE public.buyer_outreach_log SET status=a.status,outcome_reason=a.reason WHERE id=p_id;
 RETURN jsonb_build_object('id',p_id,'claimed',false,'status',a.status,'reason',a.reason);
END $$;
REVOKE ALL ON FUNCTION public.record_buyer_sms_optout_rejection(uuid,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_buyer_sms_optout_rejection(uuid,text,integer) TO service_role;

-- Consent review and the final sending latch use the same phone/row lock order.
CREATE OR REPLACE FUNCTION public.review_buyer_sms_consent(p_id uuid,p_buyer uuid,p_operator uuid,p_phone text,p_evidence jsonb,p_accepted boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b public.buyers; prior private.buyer_sms_consent_reviews; v_phone text; suppressed boolean;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
 THEN RAISE EXCEPTION 'Approved administrator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_buyer IS NULL OR p_accepted IS NULL OR jsonb_typeof(p_evidence) IS DISTINCT FROM 'object'
 OR coalesce(p_evidence->>'source_type','') NOT IN ('signed_document','written_web_form')
 OR coalesce(p_evidence->>'source_url','') !~ '^https://[^[:space:]]+$'
 OR coalesce(p_evidence->>'sha256','') !~ '^[0-9a-f]{64}$'
 OR length(coalesce(p_evidence->>'disclosure','')) NOT BETWEEN 40 AND 4000
 OR length(coalesce(p_evidence->>'affirmative_action','')) NOT BETWEEN 3 AND 2000
 OR p_evidence->'reviewed_written_evidence' IS DISTINCT FROM 'true'::jsonb
 OR coalesce(p_evidence->>'consented_at','')=''
 THEN RAISE EXCEPTION 'Written consent evidence required' USING ERRCODE='22023'; END IF;
 IF (p_evidence->>'consented_at')::timestamptz>now()+interval '5 minutes'
 OR (p_evidence->>'consented_at')::timestamptz<'2000-01-01'::timestamptz
 THEN RAISE EXCEPTION 'Invalid consent date' USING ERRCODE='22023'; END IF;
 v_phone:=private.buyer_phone(p_phone);
 IF v_phone IS NULL THEN RAISE EXCEPTION 'Invalid US phone' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('buyer-sms-consent:'||p_id::text,0));
 SELECT * INTO prior FROM private.buyer_sms_consent_reviews WHERE id=p_id;
 IF FOUND THEN
   IF prior.buyer_id<>p_buyer OR prior.operator_id<>p_operator OR prior.phone<>v_phone
   OR prior.evidence<>p_evidence OR prior.accepted<>p_accepted
   THEN RAISE EXCEPTION 'Consent review reference changed' USING ERRCODE='22023'; END IF;
   RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'duplicate',true,'accepted',prior.accepted);
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||v_phone,0));
 SELECT * INTO b FROM public.buyers WHERE id=p_buyer FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Buyer not found' USING ERRCODE='P0002'; END IF;
 IF v_phone IS DISTINCT FROM private.buyer_phone(b.phone)
 THEN RAISE EXCEPTION 'Buyer phone changed; review the current number' USING ERRCODE='22023'; END IF;
 suppressed:=EXISTS(SELECT 1 FROM public.dnc_registry WHERE private.buyer_phone(phone_number)=v_phone)
 OR EXISTS(SELECT 1 FROM public.leads l WHERE l.dnc IS TRUE AND v_phone IN (
 private.buyer_phone(l.owner_phone_1),private.buyer_phone(l.owner_phone_2),private.buyer_phone(l.owner_phone_3)));
 IF p_accepted AND suppressed THEN RAISE EXCEPTION 'Phone is suppressed; review cannot clear suppression' USING ERRCODE='22023'; END IF;
 INSERT INTO private.buyer_sms_consent_reviews(id,buyer_id,operator_id,phone,evidence,accepted)
 VALUES(p_id,p_buyer,p_operator,v_phone,p_evidence,p_accepted);
 UPDATE public.buyers SET sms_opt_in=p_accepted WHERE id=p_buyer;
 RETURN jsonb_build_object('id',p_id,'buyer_id',p_buyer,'saved',true,'duplicate',false,'accepted',p_accepted);
END $$;
REVOKE ALL ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.review_buyer_sms_consent(uuid,uuid,uuid,text,jsonb,boolean) TO service_role;
